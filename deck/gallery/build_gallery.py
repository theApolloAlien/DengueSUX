"""Builds the Devpost gallery mock-ups (HTML -> PNG via headless Chrome).

Real inputs: URA 2025 planning-area boundaries, NEA active dengue clusters (as saved by
the Phase 1 audit), MOH weekly bulletin counts. The area priority levels are an
illustrative heuristic from live cluster data only (no weather term yet), and the
explanation bars are an illustrative example -- both are labelled as such on the images.
"""
import gzip
import json
import math
import subprocess
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

RED, NAVY, BODY, MUTED, TINT, LINE = "#FF3621", "#1B3139", "#3D4A52", "#6B7780", "#F4F6F7", "#DDE2E6"
LEVEL_FILL = {"High": "#C8260E", "Medium": "#F2826B", "Low": "#FBE1DB"}

# ---------- geography ----------
pa = json.load(gzip.open(ROOT / "data/raw/boundaries/planning_areas_2025.geojson.gz"))
cl = json.load(gzip.open(ROOT / "data/raw/dengue/active_clusters.geojson.gz"))
areas = [(f["properties"]["PLN_AREA_N"].title(), shape(f["geometry"])) for f in pa["features"]]
clusters = [
    (f["properties"]["LOCALITY"].strip(), int(f["properties"]["CASE_SIZE"]), shape(f["geometry"]),
     f["properties"]["FMEL_UPD_D"])
    for f in cl["features"]
]
cluster_asof = max(c[3] for c in clusters)
cluster_asof = f"{cluster_asof[6:8]} Sep {cluster_asof[:4]}" if cluster_asof[4:6] == "09" else cluster_asof[:8]

LAT0 = math.cos(math.radians(1.35))
KM_PER_DEG = 111.0

def km_xy(x, y, z=None):
    return (x * LAT0 * KM_PER_DEG, y * KM_PER_DEG)

areas_km = [(n, transform(km_xy, g)) for n, g in areas]
clusters_km = [(loc, n, transform(km_xy, g)) for loc, n, g, _ in clusters]

# Illustrative priority heuristic: cases inside the area + 0.15 x cases in clusters within 2 km.
scores = {}
for name, g in areas_km:
    inside = sum(n * (c.intersection(g).area / c.area) for _, n, c in clusters_km if c.intersects(g))
    near = sum(n for _, n, c in clusters_km if not c.intersects(g) and c.distance(g) < 2.0)
    scores[name] = inside + 0.15 * near

def level(s):
    return "High" if s >= 12 else "Medium" if s >= 2 else "Low"

levels = {n: level(s) for n, s in scores.items()}
ranked = sorted(scores.items(), key=lambda kv: -kv[1])

def svg_map(w, h, pad=10):
    minx = min(g.bounds[0] for _, g in areas_km); miny = min(g.bounds[1] for _, g in areas_km)
    maxx = max(g.bounds[2] for _, g in areas_km); maxy = max(g.bounds[3] for _, g in areas_km)
    s = min((w - 2 * pad) / (maxx - minx), (h - 2 * pad) / (maxy - miny))
    ox = pad + ((w - 2 * pad) - (maxx - minx) * s) / 2
    oy = pad + ((h - 2 * pad) - (maxy - miny) * s) / 2

    def path(geom):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        d = []
        for p in polys:
            for ring in [p.exterior, *p.interiors]:
                pts = [(ox + (x - minx) * s, oy + (maxy - y) * s) for x, y in ring.coords]
                d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        return "".join(d)

    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
    for name, g in areas_km:
        simp = g.simplify(0.05, preserve_topology=True)
        parts.append(f'<path d="{path(simp)}" fill="{LEVEL_FILL[levels[name]]}" stroke="#FFFFFF" stroke-width="1.2"/>')
    for loc, n, c in clusters_km:
        ct = c.centroid
        x, y = ox + (ct.x - minx) * s, oy + (maxy - ct.y) * s
        r = 5 + 2.2 * math.sqrt(n)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{NAVY}" fill-opacity="0.85" stroke="#FFFFFF" stroke-width="2"/>')
        if n >= 5:
            parts.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" font-weight="700" fill="#FFFFFF" text-anchor="middle">{n}</text>')
    # labels for High/Medium, drawn last with a halo so clusters never hide them
    for name, g in areas_km:
        if levels[name] != "Low":
            c = g.representative_point()
            x, y = ox + (c.x - minx) * s, oy + (maxy - c.y) * s
            parts.append(f'<text x="{x:.0f}" y="{y - 16:.0f}" font-size="12" font-weight="700" fill="{NAVY}" text-anchor="middle" paint-order="stroke" stroke="#FFFFFF" stroke-width="3.5" stroke-linejoin="round">{name}</text>')
    parts.append("</svg>")
    return "".join(parts)

# ---------- national weekly series (real) ----------
weekly = json.load(open(OUT.parent / "weekly_dengue.json"))
weeks = sorted(weekly)
series = [(w, weekly[w]) for w in weeks if "2019-W01" <= w <= "2022-W52"]
vals = [v for _, v in series]
# baseline: mean of the 4 weeks ending 2 weeks before the target week (a 2-week-ahead naive forecast)
base = [None if i < 5 else sum(vals[i - 5:i - 1]) / 4 for i in range(len(vals))]

errs = [abs(v - b) for v, b in zip(vals, base) if b is not None]
base_mae = sum(errs) / len(errs)

def svg_chart(w, h):
    L, R, T, B = 64, 20, 20, 44
    ymax = 2000
    n = len(vals)
    X = lambda i: L + i * (w - L - R) / (n - 1)
    Y = lambda v: T + (1 - v / ymax) * (h - T - B)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" font-family="Inter, Arial, sans-serif">']
    for v in range(0, ymax + 1, 500):
        parts.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{L - 10}" y="{Y(v) + 4:.1f}" font-size="12" fill="{MUTED}" text-anchor="end">{v:,}</text>')
    for i, (wk, _) in enumerate(series):
        if wk.endswith("-W01"):
            parts.append(f'<text x="{X(i):.1f}" y="{h - 16}" font-size="12" fill="{MUTED}">{wk[:4]}</text>')
            parts.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{h - B}" y2="{h - B + 6}" stroke="{LINE}"/>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    bpts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(base) if v is not None)
    parts.append(f'<polyline points="{bpts}" fill="none" stroke="#9AA5B1" stroke-width="2" stroke-dasharray="6 4"/>')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{NAVY}" stroke-width="2.2" stroke-linejoin="round"/>')
    pk = max(range(len(vals)), key=lambda i: vals[i])
    parts.append(f'<circle cx="{X(pk):.1f}" cy="{Y(vals[pk]):.1f}" r="5" fill="{RED}" stroke="#fff" stroke-width="2"/>')
    parts.append(f'<text x="{X(pk) + 10:.1f}" y="{Y(vals[pk]) + 4:.1f}" font-size="13" font-weight="700" fill="{NAVY}">{int(vals[pk]):,} cases · {series[pk][0]}</text>')
    parts.append("</svg>")
    return "".join(parts)

# ---------- pages ----------
CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1500px;height:1000px;font-family:Inter,Arial,sans-serif;background:#FFFFFF;color:{BODY};overflow:hidden}}
.top{{height:64px;background:{NAVY};display:flex;align-items:center;padding:0 36px;gap:14px;color:#fff}}
.logo{{font-size:22px;font-weight:800;letter-spacing:-.3px}} .logo b{{color:{RED}}}
.sub{{font-size:13px;color:#AFC0CA}}
.pill{{margin-left:auto;font-size:12px;background:rgba(255,255,255,.1);padding:6px 12px;border-radius:99px;color:#D5DCE1}}
.mock{{position:absolute;bottom:14px;right:24px;font-size:11px;color:{MUTED};background:#fff;padding:4px 10px;border-radius:6px;border:1px solid {LINE}}}
.wrap{{padding:26px 36px;display:grid;gap:22px}}
.card{{background:{TINT};border-radius:14px;padding:22px}}
h2{{font-size:13px;letter-spacing:1px;color:{RED};font-weight:800;text-transform:uppercase;margin-bottom:6px}}
h1{{font-size:28px;color:{NAVY};font-weight:800;letter-spacing:-.4px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.kpi{{background:{TINT};border-radius:12px;padding:16px 18px}}
.kpi .v{{font-size:34px;font-weight:800;color:{NAVY}}} .kpi .l{{font-size:13px;color:{MUTED};margin-top:2px}}
.legend{{display:flex;gap:16px;font-size:13px;color:{BODY};align-items:center;flex-wrap:wrap}}
.sw{{display:inline-block;width:14px;height:14px;border-radius:4px;vertical-align:-2px;margin-right:6px}}
.dot{{display:inline-block;width:14px;height:14px;border-radius:50%;background:{NAVY};vertical-align:-2px;margin-right:6px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
td{{padding:9px 4px;border-bottom:1px solid {LINE}}}
.badge{{font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px;letter-spacing:.5px}}
"""

def badge(lv):
    fg = "#FFFFFF" if lv == "High" else NAVY
    return f'<span class="badge" style="background:{LEVEL_FILL[lv]};color:{fg}">{lv.upper()}</span>'

def page(body):
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"

TOP = f"""<div class="top"><div class="logo">Dengue<b>SUX</b></div>
<div class="sub">Surveillance Using eXplainable AI · Singapore</div>
<div class="pill">Databricks AI/BI · data.gov.sg</div></div>"""

n_clusters = len(clusters); n_cases = sum(c[1] for c in clusters)
n_high = sum(1 for v in levels.values() if v == "High"); n_med = sum(1 for v in levels.values() if v == "Medium")
top_rows = "".join(
    f"<tr><td style='color:{MUTED};width:26px'>{i+1}</td><td style='font-weight:700;color:{NAVY}'>{n}</td><td style='text-align:right'>{badge(levels[n])}</td></tr>"
    for i, (n, s) in enumerate(ranked[:8])
)

# 1. Risk map dashboard
p1 = page(TOP + f"""
<div class="wrap" style="grid-template-columns:1fr 380px">
  <div style="display:grid;gap:18px;grid-template-rows:auto 1fr">
    <div class="kpis">
      <div class="kpi"><div class="v">{n_clusters}</div><div class="l">Active NEA clusters</div></div>
      <div class="kpi"><div class="v">{n_cases}</div><div class="l">Cases in active clusters</div></div>
      <div class="kpi"><div class="v" style="color:{RED}">{n_high}</div><div class="l">High-priority areas</div></div>
      <div class="kpi"><div class="v">{n_med}</div><div class="l">Medium-priority areas</div></div>
    </div>
    <div class="card" style="position:relative;padding:18px 22px">
      <h2>Planning-area priority index · current signals</h2>
      <div class="legend" style="margin-bottom:6px">
        <span><span class="sw" style="background:{LEVEL_FILL['High']}"></span>High</span>
        <span><span class="sw" style="background:{LEVEL_FILL['Medium']}"></span>Medium</span>
        <span><span class="sw" style="background:{LEVEL_FILL['Low']};border:1px solid #F2B8AB"></span>Low</span>
        <span><span class="dot"></span>Active cluster (size = cases)</span>
      </div>
      {svg_map(1000, 650)}
    </div>
  </div>
  <div style="display:grid;gap:18px;align-content:start">
    <div class="card"><h2>Inspect first</h2>
      <div style="font-size:13px;color:{MUTED};margin-bottom:8px">Ranked by leading-signal index</div>
      <table>{top_rows}</table></div>
    <div class="card" style="background:{NAVY};color:#D5DCE1;align-self:start">
      <h2>Why Jurong West?</h2>
      <div style="font-size:15px;line-height:1.5;color:#fff">A 74-case active cluster straddles Jurong West and Jurong East; lagged weather and other leading signals are shown alongside it.</div>
      <div style="font-size:12px;margin-top:12px;color:#AFC0CA">This index guides attention; it is not a local case forecast.</div>
    </div>
    <div class="card" style="align-self:start"><h2>Data freshness</h2>
      <table style="font-size:13px">
      <tr><td>NEA dengue clusters</td><td style="text-align:right;color:{NAVY};font-weight:700">{cluster_asof}</td></tr>
      <tr><td>Rainfall · temperature · humidity</td><td style="text-align:right;color:{NAVY};font-weight:700">Live, every 5 min</td></tr>
      <tr><td>National case labels</td><td style="text-align:right;color:{NAVY};font-weight:700">2012–2022</td></tr>
      </table></div>
  </div>
</div>
<div class="mock">Illustrative mock-up · real NEA clusters (updated {cluster_asof}) + URA 2025 boundaries · priority levels are a draft heuristic</div>
""")

# 2. Forecast + explanation
drivers = [("Rainfall, 3–5 weeks ago", 0.42, "+"), ("Mean temperature, 2–4 weeks ago", 0.31, "+"),
           ("Cases trend, last 4 weeks", 0.27, "+"), ("Relative humidity, 2 weeks ago", 0.12, "+"),
           ("Dry spell, 6 weeks ago", 0.08, "−")]
bars = "".join(
    f"""<div style="display:grid;grid-template-columns:260px 1fr 40px;align-items:center;gap:12px;margin:12px 0">
    <div style="font-size:14px;color:{NAVY};font-weight:600">{name}</div>
    <div style="height:14px;background:#fff;border-radius:4px"><div style="height:14px;width:{v/0.42*100:.0f}%;background:{RED if sign=='+' else '#9AA5B1'};border-radius:0 4px 4px 0"></div></div>
    <div style="font-size:13px;color:{MUTED};text-align:right">{sign}{v:.2f}</div></div>"""
    for name, v, sign in drivers)
p2 = page(TOP + f"""
<div class="wrap" style="grid-template-columns:1fr 470px">
  <div class="card" style="padding:24px 26px">
    <h2>National weekly dengue cases</h2>
    <h1>2020's outbreak built for weeks before it peaked</h1>
    <div class="legend" style="margin:14px 0 6px">
      <span><span class="sw" style="background:{NAVY}"></span>Actual cases (MOH bulletin)</span>
      <span><span class="sw" style="background:#9AA5B1"></span>Baseline: 4-week average, 2 weeks ahead (dashed)</span>
      <span><span class="sw" style="background:{RED}"></span>DengueSUX selected forecast (freshness-gated)</span>
    </div>
    {svg_chart(900, 700)}
    <div style="font-size:13px;color:{MUTED};margin-top:6px">Historical target: compare selected, candidate and baseline error over 2017–2022 with rolling-origin evaluation. A current forecast appears only after recent labels pass the freshness gate.</div>
  </div>
  <div style="display:grid;gap:18px;align-content:start">
    <div class="card"><h2>Why this forecast?</h2>
      <div style="font-size:14px;color:{MUTED};margin-bottom:4px">Grouped attributions, example week</div>
      {bars}
      <div style="font-size:12px;color:{MUTED};margin-top:10px">Illustrative example. Real values come from the trained model.</div>
    </div>
    <div class="card" style="background:{NAVY};align-self:start">
      <h2>In plain English</h2>
      <div style="font-size:17px;line-height:1.55;color:#fff">“Rainfall in weeks 3–5 and recent case trend are associated with this estimate. These are model signals, not proof of cause.”</div>
    </div>
    <div class="card" style="align-self:start"><h2>The number to beat</h2>
      <div style="font-size:40px;font-weight:800;color:{NAVY}">{base_mae:.0f} <span style="font-size:16px;color:{MUTED};font-weight:600">cases / week</span></div>
      <div style="font-size:13px;color:{MUTED};margin-top:4px">Baseline error (MAE), 2-week-ahead historical replay. Computed from the MOH bulletin; results are reported even when the baseline is selected.</div></div>
  </div>
</div>
<div class="mock">Illustrative mock-up · actual cases and baseline computed from MOH Weekly Infectious Disease Bulletin (data.gov.sg), 2019–2022</div>
""")

# 3. Genie Q&A
def reason(area):
    g = dict(areas_km)[area]
    inside = [(loc, n) for loc, n, c in clusters_km if c.intersects(g)]
    near = [(loc, n) for loc, n, c in clusters_km if not c.intersects(g) and c.distance(g) < 2.0]
    bits = []
    if inside:
        loc, n = max(inside, key=lambda t: t[1])
        bits.append(f"{n}-case cluster at {loc.split('(')[0].split('/')[0].strip()}")
    if near:
        tot = sum(n for _, n in near)
        bits.append(f"{tot} cases in {len(near)} cluster{'s' if len(near) > 1 else ''} within 2 km")
    txt = "; ".join(bits) if bits else "No nearby clusters"
    return txt[0].upper() + txt[1:]

gen_rows = "".join(
    f"<tr><td style='font-weight:700;color:{NAVY}'>{n}</td><td>{badge(levels[n])}</td><td style='color:{BODY}'>{reason(n)}</td></tr>"
    for n, _ in ranked[:4])
p3 = page(TOP + f"""
<div class="wrap" style="grid-template-columns:320px 1fr">
  <div class="card" style="display:grid;align-content:start;gap:14px">
    <h2>Genie space</h2>
    <div style="font-size:15px;color:{NAVY};font-weight:700">DengueSUX: Ask the data</div>
    <div style="font-size:13px;color:{MUTED};line-height:1.5">Built on governed Unity Catalog tables: weekly features, forecasts, priority scores and active clusters.</div>
    <div style="font-size:13px;color:{BODY};line-height:1.9">Try asking:<br>· Which areas are high priority this week?<br>· Why is Bishan flagged?<br>· How did rainfall change last month?<br>· Show clusters near my block</div>
  </div>
  <div style="display:grid;gap:18px;align-content:start">
    <div style="justify-self:end;background:{NAVY};color:#fff;border-radius:16px 16px 4px 16px;padding:16px 20px;font-size:17px;max-width:720px">Which areas should we inspect first this week, and why?</div>
    <div class="card" style="border-radius:16px 16px 16px 4px;padding:24px 26px">
      <div style="font-size:16px;color:{NAVY};line-height:1.55;margin-bottom:14px">Start with the <b>West</b>. The largest active cluster (74 cases) straddles Jurong West and Jurong East, alongside leading weather signals. These four areas carry the highest planning priority indices right now:</div>
      <table><tr><td style="font-size:12px;color:{MUTED};font-weight:700">AREA</td><td style="font-size:12px;color:{MUTED};font-weight:700">PRIORITY</td><td style="font-size:12px;color:{MUTED};font-weight:700">MAIN REASON</td></tr>{gen_rows}</table>
      <div style="font-size:13px;color:{MUTED};margin-top:14px">Source tables: gold.area_priority, gold.active_clusters (as of {cluster_asof}) · Show SQL</div>
    </div>
    <div style="justify-self:end;background:{NAVY};color:#fff;border-radius:16px 16px 4px 16px;padding:16px 20px;font-size:17px;max-width:720px">Why is Bukit Batok high when it only has 2 cases?</div>
    <div class="card" style="border-radius:16px 16px 16px 4px;padding:24px 26px;font-size:16px;color:{NAVY};line-height:1.6">
      Bukit Batok has its own 2-case cluster at Bt Batok St 21, and it lies within 2 km of the 74-case Ho Ching Rd cluster. Nearby clusters are one bounded component of the index; weather and completeness remain visible separately.
      <div style="font-size:13px;color:{MUTED};margin-top:10px">Priority = leading weather signals + construction context when available + bounded cluster trajectory · no local case forecast is implied</div>
    </div>
    <div style="background:#fff;border:1px solid {LINE};border-radius:12px;padding:16px 20px;font-size:15px;color:{MUTED}">Ask a follow-up…</div>
  </div>
</div>
<div class="mock">Illustrative mock-up of a Databricks Genie space · answers use real NEA cluster data; wording is illustrative</div>
""")

for i, html in enumerate([p1, p2, p3], 1):
    f = OUT / f"gallery_{i}.html"
    f.write_text(html, encoding="utf-8")
    png = OUT / f"DengueSUX_gallery_{i}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=1500,1000",
                    f"--screenshot={png}", f.as_uri()], check=True, capture_output=True)
    print(png, png.stat().st_size)
print("ranked:", ranked[:6])

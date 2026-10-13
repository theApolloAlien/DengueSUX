"""Build the public resident site (static HTML, no login) from the published web data.

Databricks Apps require a workspace sign-in, so residents who scan a poster or follow a Telegram link land here
instead: one page per planning area with this week's numbers, the resident notice in four languages, what to check,
and the Telegram bot. Nothing interactive, nothing personal, every number dated.

  .venv-prototype/bin/python scripts/build_public_site.py [--out public] [--app-url URL]
Publish the folder with GitHub Pages (branch gh-pages) or any static host; set DENGUE_RESIDENT_URL in the app so posters
and Telegram deep links point here.
"""
import argparse
import datetime as dt
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "output/web"
LANGS = [("en", "English"), ("zh", "中文"), ("ms", "Bahasa Melayu"), ("ta", "தமிழ்")]
STEPS = {
    "en": ["Turn over pails and wipe their rims", "Empty flowerpot plates and trays", "Change vase water every other day", "Clear roof gutters and drains", "Loosen hardened soil"],
    "zh": ["翻转水桶并擦干边缘", "倒掉花盆底盘和托盘的积水", "隔天更换花瓶的水", "清理屋顶排水槽和沟渠", "松动板结的泥土"],
    "ms": ["Terbalikkan baldi dan lap bibirnya", "Kosongkan piring dan dulang pasu bunga", "Tukar air pasu selang sehari", "Bersihkan saluran bumbung dan longkang", "Gemburkan tanah yang keras"],
    "ta": ["வாளிகளைத் தலைகீழாகக் கவிழ்த்து விளிம்புகளைத் துடைக்கவும்", "பூந்தொட்டித் தட்டுகளில் உள்ள நீரை ஊற்றவும்", "பூஜாடி நீரை இரு நாட்களுக்கு ஒருமுறை மாற்றவும்", "கூரை வடிகால்களையும் சாக்கடைகளையும் சுத்தம் செய்யவும்", "இறுகிய மண்ணைத் தளர்த்தவும்"],
}
HEAD = {"en": "Dengue is in our neighbourhood", "zh": "骨痛热症就在我们的社区", "ms": "Denggi ada di kejiranan kita", "ta": "டெங்கு நம் அக்கம்பக்கத்தில் உள்ளது"}
LEAD = {"en": "Ten minutes this week can stop the next case.", "zh": "本周花十分钟，就能阻止下一个病例。", "ms": "Sepuluh minit minggu ini boleh menghalang kes seterusnya.", "ta": "இந்த வாரம் பத்து நிமிடங்கள் அடுத்த நோயைத் தடுக்கலாம்."}
PEOPLE = {"en": "people in active dengue clusters around", "zh": "人在活跃骨痛热症感染群中，位于", "ms": "orang dalam kluster denggi aktif di sekitar", "ta": "பேர் செயலில் உள்ள டெங்கு கொத்துகளில்,"}


def slug(name):
    return re.sub(r"-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def esc(v):
    return html.escape(str(v if v is not None else ""))


CSS = """:root{--forest:#163f35;--ivory:#f7f8f4;--ink:#193e33;--muted:#5f7259;--red:#c2523c;--amber:#c9921f}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--ivory);color:var(--ink)}
header{background:var(--forest);color:#fff;padding:18px 20px}header a{color:#dfe8de;text-decoration:none}header strong{font-size:18px}
main{max-width:760px;margin:0 auto;padding:20px}h1{font-size:34px;line-height:1.1;margin:8px 0 6px}.lead{font-size:18px;color:var(--muted);margin:0 0 16px}
.figure{display:flex;align-items:baseline;gap:12px;border-top:3px solid var(--red);padding-top:14px;margin:14px 0}.figure b{font-size:52px;line-height:1;color:var(--red)}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600;background:#e6ece3}.badge.high{background:#fde3dc;color:#8f2f1e}.badge.medium{background:#fbeccb;color:#7a5a12}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:18px 0 8px}.tabs label{padding:8px 14px;border:1px solid #d7deca;border-radius:999px;cursor:pointer;background:#fff;font-weight:600}
input[name=lang]{display:none}.pane{display:none;background:#fff;border:1px solid #e0e5d6;border-radius:12px;padding:16px 18px}
#l-en:checked~.pane.en,#l-zh:checked~.pane.zh,#l-ms:checked~.pane.ms,#l-ta:checked~.pane.ta{display:block}
#l-en:checked~.tabs label[for=l-en],#l-zh:checked~.tabs label[for=l-zh],#l-ms:checked~.tabs label[for=l-ms],#l-ta:checked~.tabs label[for=l-ta]{background:var(--forest);color:#fff;border-color:var(--forest)}
ul.steps{padding-left:20px}ul.steps li{margin:6px 0}.places{background:#fff;border:1px solid #e0e5d6;border-radius:12px;padding:14px 18px;margin:16px 0}.places li{margin:4px 0}
.cta{display:inline-block;background:#229ED9;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600;margin:6px 8px 6px 0}.cta.app{background:var(--forest)}
footer{color:var(--muted);font-size:13px;padding:24px 20px;text-align:center}.areas{list-style:none;padding:0;margin:0;display:grid;gap:8px}.areas a{display:flex;justify-content:space-between;align-items:center;background:#fff;border:1px solid #e0e5d6;border-radius:10px;padding:12px 14px;text-decoration:none;color:inherit}
.note{font-size:13px;color:var(--muted)}"""


def page(title, body, app_url, base):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · DengueSUX</title>
<meta name="description" content="Dengue clusters, what to check and a resident notice in four languages. Open data from NEA, MOH and URA via data.gov.sg."><style>{CSS}</style></head>
<body><header><a href="{base}/"><strong>DengueSUX</strong> · Places to check, not confirmed breeding sites</a></header><main>{body}</main>
<footer>Data: NEA, MOH and URA via data.gov.sg · A DAISI Challenge prototype · <a href="{esc(app_url)}">Full app (workspace sign-in)</a></footer></body></html>"""


def build(out, app_url, base):
    current = json.loads((WEB / "current.json").read_text())
    notices = json.loads((WEB / "notices.json").read_text())["notices"]
    inspection = json.loads((WEB / "inspection.json").read_text()).get("areas", {})
    outlook = {a["code"]: a for a in json.loads((WEB / "area_forecast.json").read_text()).get("areas", [])} if (WEB / "area_forecast.json").exists() else {}
    walks = json.loads((WEB / "walks/index.json").read_text()).get("areas", {}) if (WEB / "walks/index.json").exists() else {}
    as_of = dt.datetime.fromisoformat(current["as_of"].replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=8)))
    date = as_of.strftime("%-d %B %Y")
    if out.exists():
        shutil.rmtree(out)
    (out / "areas").mkdir(parents=True)
    areas = sorted(current["areas"], key=lambda a: (-a["cluster_cases"], a["name"]))
    for a in areas:
        code, s = a["code"], slug(a["name"])
        band = a["risk"]
        o = outlook.get(code)
        stops = (inspection.get(code) or {}).get("stops") or []
        walk = walks.get(code) or {}
        panes = []
        for lang, label in LANGS:
            n = (notices.get(code) or {}).get(lang) or {}
            panes.append(f"""<section class="pane {lang}" lang="{lang}"><p>{esc(n.get('text') or '')}</p><ul class="steps">{''.join(f'<li>{esc(x)}</li>' for x in STEPS[lang])}</ul><p class="note">{esc(notices.get(code, {}).get(lang, {}).get('label') or 'Draft: review before sending')}</p></section>""")
        tabs = "".join(f'<label for="l-{lang}">{label}</label>' for lang, label in LANGS)
        inputs = "".join(f'<input type="radio" name="lang" id="l-{lang}"{" checked" if lang == "en" else ""}>' for lang, _ in LANGS)
        places = ""
        if stops:
            places = f"""<div class="places"><strong>Places volunteers check this week</strong><ol>{''.join(f'<li>{esc(st["name"])}</li>' for st in stops[:8])}</ol><p class="note">Publicly accessible places near the cluster; never enter homes or climb to gutters.</p></div>"""
        elif walk.get("stops"):
            places = f"""<div class="places"><strong>A routine walk is saved for this area</strong><p class="note">{walk['stops']} official places (HDB blocks, hawker centres, parks) within a short walk.</p></div>"""
        body = f"""<p class="note">{esc(a['name'])} · {esc(date)} · <span class="badge {band.lower()}">{esc(band)} priority</span></p>
<h1 lang="en">{esc(HEAD['en'])}</h1><p class="lead">{esc(LEAD['en'])}</p>
<div class="figure"><b>{a['cluster_cases']}</b><span>{esc(PEOPLE['en'])} {esc(a['name'])} ({a['cluster_count']} active {'cluster' if a['cluster_count'] == 1 else 'clusters'}, NEA {esc(date)})</span></div>
{f'<p class="note">In about two weeks: {round(o["p_high"] * 100)}% chance of 10 or more people in clusters here (DengueSUX outlook, chances not certainties).</p>' if o else ''}
{inputs}<div class="tabs">{tabs}</div>{''.join(panes)}
{places}
<p><a class="cta" href="https://t.me/DengueSUXbot?start={esc(code)}">Follow {esc(a['name'])} on Telegram</a><a class="cta app" href="{esc(app_url)}/#plan/{s}">Open the full plan (sign-in)</a></p>
<p class="note">Places to check, not confirmed breeding sites. If you have fever with a rash, severe headache or joint pain, see a doctor.</p>"""
        (out / "areas" / f"{s}.html").write_text(page(a["name"], body, app_url, base))
    rows = "".join(f'<li><a href="{base}/areas/{slug(a["name"])}.html"><span>{esc(a["name"])}</span><span class="badge {a["risk"].lower()}">{a["cluster_cases"]} {"person" if a["cluster_cases"] == 1 else "people"} · {esc(a["risk"])}</span></a></li>' for a in areas)
    totals = current.get("totals", {})
    index = f"""<h1>Where to check first this week</h1><p class="lead">{totals.get('clusters', 0)} active dengue clusters, {totals.get('cluster_cases', 0)} people in them · NEA {esc(date)}</p>
<ul class="areas">{rows}</ul><p class="note">One page per planning area: this week's numbers, a resident notice in English, 中文, Bahasa Melayu and தமிழ், and what to check. Rebuilt from the daily data; no sign-in, no tracking.</p>"""
    (out / "index.html").write_text(page("Where to check first", index, app_url, base))
    (out / ".nojekyll").write_text("")
    return len(areas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "public"))
    ap.add_argument("--app-url", default="https://denguesux-7474658048209156.aws.databricksapps.com")
    ap.add_argument("--base", default="/DengueSUX", help="Path prefix on the static host (GitHub Pages project site)")
    args = ap.parse_args()
    n = build(Path(args.out), args.app_url, args.base.rstrip("/"))
    print(f"Built {n} area pages in {args.out}")

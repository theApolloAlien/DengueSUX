// Builds the DAISI Round 1 3-slide deck (editable .pptx) in the official template's style.
// Source for dengue numbers: MOH Weekly Infectious Disease Bulletin via data.gov.sg
// (resource d_ca168b2cb763640d72c4600a68f9909e), Dengue Fever + DHF, 2012-W01 to 2022-W52.
const pptxgen = require("pptxgenjs");

const RED = "FF3621";
const NAVY = "1B3139";
const BODY = "3D4A52";
const MUTED = "6B7780";
const BAR = "B8C2CA";
const TINT = "F4F6F7";
const PENDING = "FFF4F2";
const FONT = "Arial";

const annual = {
  2012: 4632, 2013: 22194, 2014: 18326, 2015: 11303, 2016: 13179, 2017: 2776,
  2018: 3285, 2019: 15998, 2020: 35315, 2021: 5264, 2022: 32175,
};
const PEAKS = new Set(["2020", "2022"]);

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in, matches template
pres.title = "DengueSUX — DAISI Challenge Round 1";

function frame(slide, n, title) {
  slide.background = { color: "FFFFFF" };
  // The official template's red top band
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 13.33, h: 0.16, fill: { color: RED }, line: { color: RED } });
  slide.addText(`SLIDE ${n}`, { isTextBox: true, x: 0.9, y: 0.55, w: 3, h: 0.3, margin: 0, fontFace: FONT, fontSize: 13, bold: true, color: RED });
  slide.addText(title, { isTextBox: true, x: 0.9, y: 0.9, w: 11.5, h: 0.75, margin: 0, fontFace: FONT, fontSize: 36, bold: true, color: NAVY });
  slide.addText("DAISI Challenge Singapore 2026 · Round 1 · A2 — DengueRadar: Real-time outbreak forecasting", {
    isTextBox: true, x: 0.9, y: 7.05, w: 11.5, h: 0.25, margin: 0, fontFace: FONT, fontSize: 10, color: MUTED,
  });
}

// label + answer block; returns nothing, caller controls y
function field(slide, label, answer, x, y, w, h, opts = {}) {
  slide.addText(
    [
      { text: label, options: { bold: true, color: RED, fontSize: 11, charSpacing: 1, breakLine: true } },
      ...(Array.isArray(answer) ? answer : [{ text: answer, options: { color: BODY, fontSize: opts.size || 14 } }]),
    ],
    { isTextBox: true, x, y, w, h, margin: 0, fontFace: FONT, valign: "top", paraSpaceAfter: 3 }
  );
}

function pendingBox(slide, label, hint, x, y, w, h) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08, fill: { color: PENDING }, line: { color: "F5B7AD", width: 1, dashType: "dash" },
  });
  slide.addText(
    [
      { text: label, options: { bold: true, color: RED, fontSize: 11, charSpacing: 1, breakLine: true } },
      { text: hint, options: { color: MUTED, fontSize: 12, italic: true } },
    ],
    { isTextBox: true, x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h - 0.3, margin: 0, fontFace: FONT, valign: "top", paraSpaceAfter: 4 }
  );
}

// ---------------- Slide 1: Problem & why it matters ----------------
{
  const s = pres.addSlide();
  frame(s, 1, "Problem & why it matters");

  // Team + problem statement row
  s.addText(
    [
      { text: "TEAM  ", options: { bold: true, color: RED, fontSize: 11, charSpacing: 1 } },
      { text: "DengueSUX", options: { bold: true, color: NAVY, fontSize: 14 } },
      { text: "      PROBLEM STATEMENT  ", options: { bold: true, color: RED, fontSize: 11, charSpacing: 1 } },
      { text: "A2 — DengueRadar: Real-time outbreak forecasting", options: { bold: true, color: NAVY, fontSize: 14 } },
    ],
    { isTextBox: true, x: 0.9, y: 1.8, w: 11.5, h: 0.35, margin: 0, fontFace: FONT, valign: "middle" }
  );

  const LX = 0.9, LW = 6.1;
  field(s, "THE PROBLEM IN ONE SENTENCE",
    "Singapore's public view is strongest after cases are reported. DengueSUX makes earlier weather and cluster context visible while stating exactly when a current national forecast is unavailable.",
    LX, 2.4, LW, 1.05);

  field(s, "WHO IS AFFECTED, AND HOW BADLY", [
    { text: "164,447 ", options: { bold: true, color: NAVY, fontSize: 14 } },
    { text: "dengue cases in Singapore from 2012–2022, including a record ", options: { color: BODY, fontSize: 14 } },
    { text: "35,315 in 2020", options: { bold: true, color: NAVY, fontSize: 14 } },
    { text: " — 1,792 in a single week at the peak. Repeat infections carry a higher risk of severe dengue.", options: { color: BODY, fontSize: 14 } },
  ], LX, 3.55, LW, 1.15);

  field(s, "WHY IT MATTERS NOW", [
    { text: "Outbreaks swing more than 10× between years (2,776 cases in 2017 vs 35,315 in 2020). Weather can provide leading context, but strain changes and reporting delays matter too. We therefore show a two-week backtest, a freshness-gated live mode, and dated local signals.", options: { color: BODY, fontSize: 14 } },
  ], LX, 4.8, LW, 1.3);

  // Right: chart card
  const CX = 7.4, CY = 2.4, CW = 5.05, CH = 3.05;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: CX, y: CY, w: CW, h: CH, rectRadius: 0.08, fill: { color: TINT }, line: { color: TINT } });
  s.addText(
    [
      { text: "Annual dengue cases, Singapore", options: { bold: true, color: NAVY, fontSize: 13, breakLine: true } },
      { text: "Outbreak years highlighted", options: { color: MUTED, fontSize: 10 } },
    ],
    { isTextBox: true, x: CX + 0.25, y: CY + 0.15, w: CW - 0.5, h: 0.5, margin: 0, fontFace: FONT }
  );
  const years = Object.keys(annual);
  s.addChart(pres.charts.BAR, [
    { name: "Cases", labels: years, values: years.map((y) => (PEAKS.has(y) ? 0 : annual[y])) },
    { name: "Outbreak year", labels: years, values: years.map((y) => (PEAKS.has(y) ? annual[y] : 0)) },
  ], {
    x: CX + 0.1, y: CY + 0.7, w: CW - 0.2, h: CH - 0.95,
    barDir: "col", barGrouping: "stacked", barGapWidthPct: 45,
    chartColors: [BAR, RED],
    showLegend: false, showValue: false,
    catAxisLabelColor: MUTED, catAxisLabelFontSize: 9, catAxisLabelFontFace: FONT,
    catAxisLineShow: false,
    valAxisLabelColor: MUTED, valAxisLabelFontSize: 9, valAxisLabelFontFace: FONT,
    valAxisLabelFormatCode: "#,##0", valAxisMaxVal: 40000, valAxisMajorUnit: 10000,
    valAxisLineShow: false,
    valGridLine: { color: "DDE2E6", size: 0.5 }, catGridLine: { style: "none" },
  });
  s.addText("Source: MOH Weekly Infectious Disease Bulletin, data.gov.sg (Dengue Fever + DHF)", {
    isTextBox: true, x: CX, y: CY + CH + 0.08, w: CW, h: 0.25, margin: 0, fontFace: FONT, fontSize: 9, color: MUTED,
  });

  // Personal quote
  s.addText(
    [
      { text: "“I've had dengue three times. The third time, I almost died.”", options: { italic: true, color: NAVY, fontSize: 14, breakLine: true } },
      { text: "— why we're building this", options: { color: MUTED, fontSize: 10 } },
    ],
    { isTextBox: true, x: CX, y: 5.9, w: CW, h: 0.7, margin: 0, fontFace: FONT, valign: "top" }
  );

  // Team details (required by the organisers)
  s.addText(
    [
      { text: "TEAM MEMBERS  ", options: { bold: true, color: RED, fontSize: 9, charSpacing: 1 } },
      { text: "[Full name] · [Institution] · [Course] · Year [X] · [email]      [Full name] · [Institution] · [Course] · Year [X] · [email]", options: { color: BODY, fontSize: 9 } },
    ],
    { isTextBox: true, x: 0.9, y: 6.72, w: 11.5, h: 0.25, margin: 0, fontFace: FONT, valign: "middle" }
  );
}

// ---------------- Slide 2: Solution & data ----------------
{
  const s = pres.addSlide();
  frame(s, 2, "Solution & data");

  const LX = 0.9, LW = 6.0;
  field(s, "OUR SOLUTION IN ONE SENTENCE", [
    { text: "DengueSUX turns open data into a weekly plan: ", options: { color: BODY, fontSize: 14 } },
    { text: "which areas to check first, which blocks to walk, and what to tell residents", options: { bold: true, color: NAVY, fontSize: 14 } },
    { text: ", backed by a 2-week national forecast tested on the 2022 outbreak.", options: { color: BODY, fontSize: 14 } },
  ], LX, 1.85, LW, 1.0);

  field(s, "WHO USES IT, AND WHAT DECISION IT CHANGES", [
    { text: "Town council officers and grassroots volunteers decide ", options: { color: BODY, fontSize: 13 } },
    { text: "where to inspect this week and in what order", options: { bold: true, color: NAVY, fontSize: 13 } },
    { text: ", starting from 8 ranked stops instead of a whole estate. Residents get a notice in their own language.", options: { color: BODY, fontSize: 13 } },
  ], LX, 2.95, LW, 1.15);

  s.addText("WHAT MAKES IT DIFFERENT FROM A GENERIC DASHBOARD", {
    isTextBox: true, x: LX, y: 4.2, w: LW, h: 0.25, margin: 0, fontFace: FONT, fontSize: 11, bold: true, color: RED, charSpacing: 1,
  });
  const diffs = [
    ["Street-level inspection plan", "Real cluster blocks → 8 places to check on a 1.2 km OneMap walking route."],
    ["Tested on a real outbreak", "About 2× more accurate than a simple average on 2022; turned High 11 weeks before the peak."],
    ["Explains every number", "Top drivers and a dated source on every figure. Places to check, never “breeding sites found”."],
    ["Speaks residents' languages", "Notices in English, 中文, Melayu and தமிழ், each passing 5 automatic fact checks."],
  ];
  diffs.forEach(([h, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = LX + col * 3.05, y = 4.55 + row * 1.05;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.9, h: 0.95, rectRadius: 0.06, fill: { color: TINT }, line: { color: TINT } });
    s.addText([
      { text: h, options: { bold: true, color: NAVY, fontSize: 11.5, breakLine: true } },
      { text: d, options: { color: BODY, fontSize: 9.5 } },
    ], { isTextBox: true, x: x + 0.12, y: y + 0.08, w: 2.66, h: 0.8, margin: 0, fontFace: FONT, valign: "top", paraSpaceAfter: 2 });
  });

  // Right: datasets card
  const CX = 7.3, CY = 1.85, CW = 5.15, CH = 4.75;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: CX, y: CY, w: CW, h: CH, rectRadius: 0.08, fill: { color: TINT }, line: { color: TINT } });
  s.addText("DATASETS (ALL OPEN AND PUBLIC)", {
    isTextBox: true, x: CX + 0.25, y: CY + 0.18, w: CW - 0.5, h: 0.25, margin: 0, fontFace: FONT, fontSize: 11, bold: true, color: RED, charSpacing: 1,
  });
  const ds = [
    ["Weekly Infectious Disease Bulletin", "MOH · 574 weeks of dengue cases, 2012–2022"],
    ["Rainfall, temperature & humidity archives", "NEA · 125M station readings, 2017–2022"],
    ["Real-time weather APIs (V2)", "NEA · live station readings"],
    ["Dengue Clusters (GeoJSON)", "NEA · live; archived daily since 24 Sep 2026"],
    ["Master Plan 2025 Planning Areas", "URA · 55 areas"],
    ["HDB Property Information", "HDB · matches cluster block addresses"],
    ["Parks · Hawker Centres", "NParks, NEA · candidate places to check"],
    ["OneMap Search & Routing", "SLA · block locations and walking routes"],
  ];
  ds.forEach(([n, d], i) => {
    const y = CY + 0.55 + i * 0.44;
    s.addShape(pres.shapes.OVAL, { x: CX + 0.25, y: y + 0.03, w: 0.28, h: 0.28, fill: { color: RED }, line: { color: RED } });
    s.addText(String(i + 1), { isTextBox: true, x: CX + 0.25, y: y + 0.03, w: 0.28, h: 0.28, margin: 0, align: "center", valign: "middle", fontFace: FONT, fontSize: 9.5, bold: true, color: "FFFFFF" });
    s.addText([
      { text: n, options: { bold: true, color: NAVY, fontSize: 11, breakLine: true } },
      { text: d, options: { color: MUTED, fontSize: 9 } },
    ], { isTextBox: true, x: CX + 0.68, y, w: CW - 0.9, h: 0.42, margin: 0, fontFace: FONT, valign: "top" });
  });
  s.addText([
    { text: "Honest limits: ", options: { bold: true, color: NAVY, fontSize: 9.5 } },
    { text: "public case data ends in 2022, so the forecast replays 2022 until recent weekly counts are approved. Area ranks are priorities, not local case predictions.", options: { color: BODY, fontSize: 9.5 } },
  ], { isTextBox: true, x: CX + 0.25, y: CY + 4.12, w: CW - 0.5, h: 0.55, margin: 0, fontFace: FONT, valign: "top" });
}

// ---------------- Slide 3: Databricks architecture & impact ----------------
{
  const s = pres.addSlide();
  frame(s, 3, "Databricks architecture & impact");

  const steps = [
    ["SOURCE", "data.gov.sg + OneMap", "Bulletin, weather, clusters, URA, HDB, parks, hawkers"],
    ["INGEST", "Bronze Delta", "Checksummed raw files; daily cluster snapshot job"],
    ["TRANSFORM", "PySpark → Delta", "Sun–Sat epi-weeks, 55-area panel, cluster → block → place joins"],
    ["MODEL", "MLflow", "3 models, 39 folds (2019–21); gradient boosting won; SHAP drivers"],
    ["OUTPUT", "App + Genie", "Map, inspection routes, 4-language notices via Foundation Model API"],
  ];
  const BX = 0.9, BW = 2.13, GAP = 0.225, BY = 1.8, BH = 1.4;
  steps.forEach(([k, h, d], i) => {
    const x = BX + i * (BW + GAP);
    const dark = i >= 3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: BY, w: BW, h: BH, rectRadius: 0.08, fill: { color: dark ? NAVY : TINT }, line: { color: dark ? NAVY : TINT } });
    s.addText([
      { text: k, options: { bold: true, color: RED, fontSize: 9.5, charSpacing: 1, breakLine: true } },
      { text: h, options: { bold: true, color: dark ? "FFFFFF" : NAVY, fontSize: 13, breakLine: true } },
      { text: d, options: { color: dark ? "D5DCE1" : BODY, fontSize: 9.5 } },
    ], { isTextBox: true, x: x + 0.13, y: BY + 0.12, w: BW - 0.26, h: BH - 0.2, margin: 0, fontFace: FONT, valign: "top", paraSpaceAfter: 3 });
    if (i < steps.length - 1) {
      s.addText("→", { isTextBox: true, x: x + BW - 0.02, y: BY + BH / 2 - 0.2, w: GAP + 0.04, h: 0.4, margin: 0, align: "center", valign: "middle", fontFace: FONT, fontSize: 16, bold: true, color: RED });
    }
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: BX, y: BY + BH + 0.1, w: 11.55, h: 0.4, rectRadius: 0.06, fill: { color: PENDING }, line: { color: PENDING } });
  s.addText([
    { text: "UNITY CATALOG  ", options: { bold: true, color: RED, fontSize: 10, charSpacing: 1 } },
    { text: "governs every table: source receipts and checksums, lineage from raw file to forecast and route, access controls", options: { color: NAVY, fontSize: 11 } },
  ], { isTextBox: true, x: BX + 0.2, y: BY + BH + 0.1, w: 11.15, h: 0.4, margin: 0, fontFace: FONT, valign: "middle" });

  const CY = 3.9, CW = 3.7, CGAP = 0.225;
  // Column 1: screenshot of the working prototype
  s.addText("WHAT WE WILL DEMO", { isTextBox: true, x: BX, y: CY, w: CW, h: 0.25, margin: 0, fontFace: FONT, fontSize: 11, bold: true, color: RED, charSpacing: 1 });
  s.addImage({ path: "slide3_inspection.png", x: BX, y: CY + 0.35, w: CW, h: CW * 900 / 1620 });
  s.addText("Already working: 8 places to check on a 1.2 km walking route around the largest cluster (real NEA, HDB, OneMap data).", {
    isTextBox: true, x: BX, y: CY + 0.42 + CW * 900 / 1620, w: CW, h: 0.5, margin: 0, fontFace: FONT, fontSize: 9.5, color: MUTED, valign: "top",
  });

  const cols = [
    ["MEASURABLE IMPACT", [
      "Forecast off by ~83 people a week vs ~172 for a simple average: 52% lower error on the 2022 outbreak",
      "Turned High 11 weeks before the 2022 peak, 1 week earlier than the simple average",
      "Teams start with 8 ranked stops instead of a whole estate",
      "220 ready-to-review resident notices: 55 areas × 4 languages",
    ]],
    ["WHAT WE CAN FINISH IN TWO WEEKS", [
      "Deploy the 6 notebooks and daily job on Databricks Free Edition (serverless), with Unity Catalog tables and MLflow",
      "Replace the scripted prototype assistant with a Genie space",
      "Run the forecast live once recent weekly case counts are approved",
      "Switch on cluster-growth ranking after 7+ days of snapshots",
    ]],
  ];
  cols.forEach(([h, items], i) => {
    const x = BX + (i + 1) * (CW + CGAP);
    s.addText(h, { isTextBox: true, x, y: CY, w: CW, h: 0.25, margin: 0, fontFace: FONT, fontSize: 11, bold: true, color: RED, charSpacing: 1 });
    s.addText(items.map((t, j) => ({ text: t, options: { bullet: { indent: 14 }, color: BODY, fontSize: 11, breakLine: j < items.length - 1 } })), {
      isTextBox: true, x, y: CY + 0.35, w: CW, h: 2.7, margin: 0, fontFace: FONT, valign: "top", paraSpaceAfter: 5,
    });
  });
}

pres.writeFile({ fileName: "DengueSUX_Round1.pptx" }).then((f) => console.log("wrote " + f));

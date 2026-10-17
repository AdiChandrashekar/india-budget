// Wiring. Reads data/union.json, renders the page, keeps controls in sync.
// House style and the reasoning behind it are locked in DESIGN.md.

import {
  load, pointsFor, valueAt, shareOfTotal, crore, lakhCrore, pct, csv, download,
  fyStart,
} from "./data.js";
import { lineChart, dumbbell, stackedBarH, treemap, legend, cssVar } from "./charts.js";

const state = {
  measure: "cr",
  basis: "best",
  wholeMeasure: "cr",
  headFilter: "edu",
  search: "",
  deptSort: { key: "latest", dir: -1 },
  headSort: { key: "latest", dir: -1 },
};

let DATA = null;

const EDU_DEFS = [
  { key: "moe", slot: "--s1", short: "Ministry" },
  { key: "functional", slot: "--s2", short: "Functional" },
  { key: "functional_narrow", slot: "--s3", short: "Functional, narrow" },
];

const $ = (id) => document.getElementById(id);

// Years with data, plus the years the pipeline could not parse, so a gap in
// coverage reads as a gap rather than as a shorter axis.
function axisYears() {
  return [...DATA.meta.years, ...(DATA.meta.gap_years || [])]
    .sort((a, b) => fyStart(a) - fyStart(b));
}

function latestYear() {
  return DATA.meta.years[DATA.meta.years.length - 1];
}

function fmtValue() {
  return state.measure === "share"
    ? (v) => (Number.isFinite(v) ? `${v.toFixed(1)}%` : "—")
    : (v) => (Number.isFinite(v)
      ? (Math.abs(v) >= 100000 ? `${(v / 100000).toFixed(2)}L cr` : `${crore(v)} cr`)
      : "—");
}

// Axis ticks keep one unit for the whole axis — "50,000" sitting under "1.0L"
// makes the reader convert in their head on every second tick.
function axisFormatter(max) {
  // Indian budgets are read in lakh crore, so switch at a lakh, not a million.
  if (max >= 100000) return (v) => (v === 0 ? "0" : `${(v / 100000).toFixed(1)}L`);
  if (max >= 10000) return (v) => (v === 0 ? "0" : `${Math.round(v / 1000)}k`);
  return (v) => crore(v);
}

function seriesPoints(series) {
  const years = DATA.meta.years;
  if (state.measure !== "share") return pointsFor(series, state.basis, years);
  const out = [];
  for (const year of years) {
    const value = shareOfTotal(series, DATA.totals, year, state.basis);
    if (value == null) continue;
    const byType = series[year] || {};
    const used = state.basis === "best"
      ? ["A", "RE", "BE"].find((t) => byType[t] != null)
      : state.basis;
    out.push({ year, value, basis: used });
  }
  return out;
}

// ---------------------------------------------------------------- utilities

function segmented(host, options, current, onPick) {
  host.textContent = "";
  for (const opt of options) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = opt.label;
    if (opt.title) b.title = opt.title;
    b.setAttribute("aria-pressed", String(opt.value === current));
    b.addEventListener("click", () => onPick(opt.value));
    host.appendChild(b);
  }
}

function buildTable(host, head, rows) {
  const table = host.querySelector("table") || host;
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.textContent = "";
  tbody.textContent = "";

  const hr = document.createElement("tr");
  for (const h of head) {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  }
  thead.appendChild(hr);

  for (const row of rows) {
    const tr = document.createElement("tr");
    if (row.cls) tr.className = row.cls;
    row.cells.forEach((cell, i) => {
      const td = document.createElement("td");
      if (i > 0) td.className = "num";
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
}

function wireTableToggles() {
  for (const btn of document.querySelectorAll("[data-table]")) {
    btn.addEventListener("click", () => {
      const target = $(btn.dataset.table);
      const show = target.hidden;
      target.hidden = !show;
      btn.textContent = show
        ? btn.textContent.replace(/^Show/, "Hide")
        : btn.textContent.replace(/^Hide/, "Show");
    });
  }
}

// ------------------------------------------------------- 1. the disagreement

function renderDefinitions() {
  const latest = latestYear();
  const vals = EDU_DEFS.map(({ key }) => valueAt(DATA.education[key].series, latest, "BE"));
  const spread = Math.max(...vals) - Math.min(...vals);

  $("hero-spread").textContent = lakhCrore(spread).replace(/ cr$/, "");
  $("hero-spread-note").textContent =
    `crore apart — the gap between the widest and narrowest definition of the `
    + `Union education budget in ${latest}`;

  const stats = $("definition-stats");
  stats.textContent = "";
  for (const { key, slot } of EDU_DEFS) {
    const block = DATA.education[key];
    const v = valueAt(block.series, latest, "BE");
    const share = shareOfTotal(block.series, DATA.totals, latest, "BE");

    const wrap = document.createElement("div");
    wrap.className = "stat";
    const dt = document.createElement("dt");
    const k = document.createElement("i");
    k.className = "key";
    k.style.background = cssVar(slot, "#2a78d6");
    const name = document.createElement("span");
    name.textContent = block.label;
    dt.append(k, name);
    const dd = document.createElement("dd");
    dd.textContent = lakhCrore(v);
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = `${pct(share)} of Union spending · ${latest} BE`;
    dd.appendChild(sub);
    wrap.append(dt, dd);
    stats.appendChild(wrap);
  }

  const series = EDU_DEFS.map(({ key, slot, short }) => ({
    label: DATA.education[key].label,
    short,
    color: cssVar(slot, "#2a78d6"),
    points: seriesPoints(DATA.education[key].series),
  }));
  const peak = Math.max(...series.flatMap((s) => s.points.map((p) => p.value)));

  // Annotate the spread where it is widest, which is the figure's whole point.
  const wideYear = latest;
  const hi = Math.max(...vals);
  const lo = Math.min(...vals);
  const annotations = state.measure === "share" ? [] : [{
    year: wideYear,
    value: hi,
    from: hi,
    to: lo,
    headline: `${crore(spread)} cr apart`,
    detail: "same year, same government",
    dx: -14,
    dy: -34,
    anchor: "end",
  }];

  // A reader meeting a cliff in a published chart should be told whether it is
  // the data or the parser. This one is the data: the ministry's budget fell
  // about 17% in 2015-16 while total Union spending barely moved. The timing
  // is that of the 14th Finance Commission award, which raised the states'
  // share of central taxes from 32% to 42% and restructured centrally
  // sponsored schemes - stated here as the coincidence it is, not as a
  // proven cause, because this tool reads budget documents and nothing more.
  const drop = "2015-16";
  const before = valueAt(DATA.education.moe.series, "2014-15", "BE");
  const after = valueAt(DATA.education.moe.series, drop, "BE");
  if (state.measure !== "share" && before && after && after < before * 0.92) {
    annotations.push({
      year: drop,
      value: after,
      headline: `${(100 * (before - after) / before).toFixed(0)}% fall in 2015-16`,
      detail: "the year the 14th Finance Commission award began",
      dx: 10,
      dy: 46,
      anchor: "start",
    });
  }

  lineChart($("edu-plot"), {
    series,
    years: axisYears(),
    format: state.measure === "share" ? (v) => `${v.toFixed(1)}%` : axisFormatter(peak),
    tipFormat: fmtValue(),
    band: true,
    annotation: annotations,
    height: 440,
  });

  legend($("edu-legend"), [
    ...series.map((s) => ({ label: s.label, color: s.color })),
    {
      label: "dashed line, hollow dot = estimate, not an outturn",
      color: cssVar("--ink-muted", "#8a9099"),
      dash: true,
    },
  ]);

  $("edu-caption").textContent = state.measure === "share"
    ? "Each definition as a share of total Union expenditure, numerator and "
      + "denominator read on the same basis. The shaded band is the spread "
      + "between definitions."
    : "Rupees crore, nominal, so later years are flattered by inflation. The "
      + "shaded band is the spread between the widest and narrowest definition.";

  const years = DATA.meta.years;
  buildTable($("edu-table"),
    ["Year", ...EDU_DEFS.map(({ key }) => DATA.education[key].label), "Total Union"],
    years.map((year) => ({
      cells: [
        year,
        ...EDU_DEFS.map(({ key }) => crore(valueAt(DATA.education[key].series, year, state.basis))),
        crore(valueAt(DATA.totals, year, state.basis)),
      ],
    })));

  const note = $("definitions-note");
  note.textContent = "";
  const intro = document.createElement("p");
  intro.style.margin = "0 0 10px";
  const b = document.createElement("strong");
  b.textContent = "Why they differ. ";
  intro.appendChild(b);
  intro.appendChild(document.createTextNode(
    "All three are the government's own numbers; the choice between them is "
    + "a choice about what counts as education."));
  note.appendChild(intro);
  for (const { key } of EDU_DEFS) {
    const p = document.createElement("p");
    p.style.margin = "0 0 6px";
    const em = document.createElement("em");
    em.textContent = DATA.education[key].label;
    p.append(em, document.createTextNode(" — " + DATA.education[key].note));
    note.appendChild(p);
  }
}

// --------------------------------------------------- 2. promise and outturn

function renderUtilisation() {
  const series = DATA.education.moe.series;
  // Only the years where the comparison can actually be made. Before the
  // pipeline reaches the Plan-era actuals there is nothing to compare a
  // budget estimate against, and a column of lone dots is not a dumbbell.
  const all = DATA.meta.years.map((year) => ({
    year,
    be: valueAt(series, year, "BE"),
    re: valueAt(series, year, "RE"),
    a: valueAt(series, year, "A"),
  }));
  const rows = all.filter((r) => r.be != null && r.a != null);
  const omitted = all.length - rows.length;

  const utilPeak = Math.max(...rows.flatMap((r) => [r.be, r.re, r.a].filter((v) => v != null)));
  dumbbell($("util-plot"), {
    rows,
    format: axisFormatter(utilPeak),
    height: Math.max(260, rows.length * 44 + 70),
    // Only say what we actually know: a missing figure here means the
    // edition that carries it has not been parsed, not that the government
    // failed to publish it.
    labelOf: () => "",
  });

  legend($("util-legend"), [
    { label: "Budget estimate", color: cssVar("--seq-estimate", "#86b6ef"), hollow: true },
    { label: "Revised estimate (tick)", color: cssVar("--ink-muted", "#8a9099") },
    { label: "Actuals", color: cssVar("--seq-outturn", "#2a78d6"), shape: "rect" },
  ]);

  const settled = rows.filter((r) => r.be != null && r.a != null);
  const ratios = settled.map((r) => (100 * r.a) / r.be);
  $("util-caption").textContent =
    "Ministry of Education, Rs crore. "
    + (ratios.length
      ? `Where the audited figure is known, spending has landed between `
        + `${Math.min(...ratios).toFixed(0)}% and ${Math.max(...ratios).toFixed(0)}% `
        + `of the opening budget estimate. `
      : "")
    + (omitted
      ? `${omitted} earlier years are left out: the Demands for Grants of the `
        + `Plan era print no actuals column, so there is nothing to compare `
        + `their estimates against. The table below carries them.`
      : "");

  // Every year, including the ones the chart leaves out: the table view is
  // the figure's complete twin, so nothing is reachable only by hovering.
  buildTable($("util-table"),
    ["Year", "Budget estimate", "Revised", "Actuals", "Actuals as % of BE"],
    all.map((r) => ({
      cells: [
        r.year, crore(r.be), crore(r.re), crore(r.a),
        r.be && r.a ? pct((100 * r.a) / r.be, 1) : "—",
      ],
    })));
}

// ------------------------------------------------------- 3. classification

function renderClassification() {
  const latest = latestYear();
  const years = axisYears();
  const accent = cssVar("--s1", "#2a78d6");
  const grants = cssVar("--s2", "#eb6834");
  const dim = cssVar("--dim", "#d9d2c6");

  // Emphasis, not categorical: education heads, the grants that leave the
  // Union, and everything else. Three classes, because that is the argument.
  const classOf = (h) => {
    if (h.education) return { cls: "edu", color: accent, onFill: "#fff" };
    if (h.code === "3601" || h.code === "3602") {
      return { cls: "grant", color: grants, onFill: "#fff" };
    }
    return { cls: "other", color: dim, onFill: cssVar("--ink", "#15181c") };
  };

  const layers = DATA.moe_heads.map((h) => {
    const k = classOf(h);
    const values = {};
    for (const year of DATA.meta.years) {
      const v = valueAt(h.series, year, state.basis);
      if (v != null && v > 0) values[year] = v;
    }
    return {
      code: h.code,
      label: `${h.code} ${h.name}`,
      short: h.code,
      color: k.color,
      onFill: k.onFill,
      education: h.education,
      values,
    };
  }).filter((l) => Object.keys(l.values).length);

  // grants first, so the point of the chart is the first thing read
  layers.sort((a, b) => {
    const rank = (l) => (l.code === "3601" ? 0 : l.education ? 1 : 2);
    return rank(a) - rank(b) || (b.values[latest] ?? 0) - (a.values[latest] ?? 0);
  });

  const g3601 = layers.find((l) => l.code === "3601");
  const classPeak = Math.max(...DATA.meta.years.map(
    (y) => layers.reduce((a, l) => a + (l.values[y] ?? 0), 0)));
  stackedBarH($("class-plot"), {
    years,
    layers,
    format: axisFormatter(classPeak),
    height: Math.max(280, DATA.meta.years.length * 40 + 110),
    annotation: g3601 ? {
      year: DATA.meta.years[0],
      index: 0,
      headline: "Grants-in-aid to states",
      detail: "spent, and booked as education, by the states",
    } : null,
  });

  legend($("class-legend"), [
    { label: "Grants-in-aid to states and UTs", color: grants, shape: "rect" },
    { label: "Education heads (2202, 2203, 4202)", color: accent, shape: "rect" },
    { label: "Everything else", color: dim, shape: "rect" },
  ]);

  $("class-caption").textContent =
    "Ministry of Education gross provision by major head, Rs crore. Gross "
    + "rather than net, because receipts are netted against the head they came "
    + "from. Segments are labelled by head code; hover or open the table for "
    + "the full name.";

  buildTable($("class-table"),
    ["Major head", ...DATA.meta.years],
    layers.map((l) => ({
      cls: l.education ? "is-edu" : "",
      cells: [l.label, ...DATA.meta.years.map((y) => crore(l.values[y] ?? null))],
    })));

  const g = g3601 ? g3601.values[latest] ?? null : null;
  const edu2202 = layers.find((l) => l.code === "2202");
  const e = edu2202 ? edu2202.values[latest] ?? null : null;

  const note = $("double-count-note");
  note.textContent = "";
  const strong = document.createElement("strong");
  strong.textContent = "The double-counting trap. ";
  note.appendChild(strong);
  note.appendChild(document.createTextNode(
    `In ${latest} the ministry books ${g != null ? lakhCrore(g) : "its largest sum"} `
    + `under head 3601, grants-in-aid to state governments, against `
    + `${e != null ? lakhCrore(e) : "a smaller sum"} under 2202, general `
    + `education. Those grants reappear as education spending in state `
    + `budgets. Add the two governments' education totals together and you `
    + `count the same rupee twice; for a genuine combined figure use the `
    + `ministry's Analysis of Budgeted Expenditure or the CAG's combined accounts.`));
}

// ------------------------------------------------------------- 4. the scale

function isEduDept(name) {
  return /school education|higher education|elementary education|secondary education/i
    .test(name);
}

function renderScale() {
  const latest = latestYear();
  const accent = cssVar("--s1", "#2a78d6");
  const dim = cssVar("--dim", "#d9d2c6");

  const items = DATA.demands
    .map((d) => ({
      name: d.name,
      value: valueAt(d.series, latest, "BE") ?? 0,
      highlight: isEduDept(d.name),
    }))
    .filter((d) => d.value > 0);

  const total = items.reduce((a, d) => a + d.value, 0);
  const edu = items.filter((d) => d.highlight).reduce((a, d) => a + d.value, 0);
  const biggest = items.slice().sort((a, b) => b.value - a.value)[0];

  const stats = $("scale-stats");
  stats.textContent = "";
  const tiles = [
    {
      label: "Education's share",
      value: pct((100 * edu) / total),
      sub: `${lakhCrore(edu)} of ${lakhCrore(total)} · ${latest} BE`,
      colour: accent,
    },
    {
      label: "Largest single demand",
      value: lakhCrore(biggest.value),
      sub: biggest.name,
      colour: dim,
    },
    {
      label: "Demands for grants",
      value: String(items.length),
      sub: "every ministry and department",
      colour: dim,
    },
  ];
  for (const t of tiles) {
    const wrap = document.createElement("div");
    wrap.className = "stat";
    const dt = document.createElement("dt");
    const k = document.createElement("i");
    k.className = "key";
    k.style.background = t.colour;
    const nm = document.createElement("span");
    nm.textContent = t.label;
    dt.append(k, nm);
    const dd = document.createElement("dd");
    dd.textContent = t.value;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = t.sub;
    dd.appendChild(sub);
    wrap.append(dt, dd);
    stats.appendChild(wrap);
  }

  treemap($("treemap-plot"), {
    items,
    format: (v) => `${crore(v)} cr`,
    height: 470,
    accent,
    dim,
    onFillAccent: "#fff",
  });

  legend($("treemap-legend"), [
    { label: "Education departments", color: accent, shape: "rect" },
    { label: "Every other demand", color: dim, shape: "rect" },
  ]);

  $("treemap-caption").textContent =
    `Every demand for grants, ${latest} budget estimate, area proportional to `
    + `provision net of receipts. Tiles too small to label carry their name on `
    + `hover; the full table has every figure.`;

  renderDepartments();
}

function deptValue(d, year) {
  return state.wholeMeasure === "share"
    ? shareOfTotal(d.series, DATA.totals, year, state.basis)
    : valueAt(d.series, year, state.basis);
}

function renderDepartments() {
  const years = DATA.meta.years;
  const latest = latestYear();
  const needle = state.search.trim().toLowerCase();

  let rows = DATA.demands.map((d) => ({
    d,
    latest: deptValue(d, latest),
    values: years.map((y) => deptValue(d, y)),
  }));
  if (needle) {
    rows = rows.filter((r) => r.d.name.toLowerCase().includes(needle)
      || (r.d.ministry || "").toLowerCase().includes(needle));
  }

  const { key, dir } = state.deptSort;
  rows.sort((a, b) => {
    if (key === "name") return dir * a.d.name.localeCompare(b.d.name);
    const ai = key === "latest" ? a.latest : a.values[years.indexOf(key)];
    const bi = key === "latest" ? b.latest : b.values[years.indexOf(key)];
    return dir * ((ai ?? -Infinity) - (bi ?? -Infinity));
  });

  const fmt = state.wholeMeasure === "share" ? (v) => pct(v, 2) : (v) => crore(v);
  const table = $("dept-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.textContent = "";
  tbody.textContent = "";

  const hr = document.createElement("tr");
  for (const [k, label] of [["name", "Department"], ...years.map((y) => [y, y])]) {
    const th = document.createElement("th");
    th.textContent = label;
    th.dataset.sort = k;
    th.tabIndex = 0;
    if (k === key) th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    const go = () => {
      state.deptSort = {
        key: k,
        dir: state.deptSort.key === k ? -state.deptSort.dir : (k === "name" ? 1 : -1),
      };
      renderDepartments();
    };
    th.addEventListener("click", go);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    hr.appendChild(th);
  }
  thead.appendChild(hr);

  for (const r of rows) {
    const tr = document.createElement("tr");
    const edu = isEduDept(r.d.name);
    if (edu) tr.className = "is-edu";
    const td = document.createElement("td");
    td.textContent = r.d.name;
    if (edu) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "education";
      td.appendChild(tag);
    }
    tr.appendChild(td);
    for (const v of r.values) {
      const cell = document.createElement("td");
      cell.className = "num";
      cell.textContent = v == null ? "—" : fmt(v);
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }

  if (!needle) {
    const tr = document.createElement("tr");
    tr.className = "total";
    const td = document.createElement("td");
    td.textContent = "Total Union expenditure";
    tr.appendChild(td);
    for (const y of years) {
      const cell = document.createElement("td");
      cell.className = "num";
      const v = state.wholeMeasure === "share" ? 100 : valueAt(DATA.totals, y, state.basis);
      cell.textContent = v == null ? "—" : fmt(v);
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }

  $("dept-caption").textContent =
    `${rows.length} of ${DATA.demands.length} departments. `
    + (state.wholeMeasure === "share"
      ? "Share of total Union expenditure, per cent."
      : "Rs crore, net of receipts netted against the demand.");
}

// -------------------------------------------------------- 5. account heads

function renderHeads() {
  const years = DATA.meta.years;
  const latest = latestYear();
  let heads = DATA.heads;
  if (state.headFilter === "edu") heads = heads.filter((h) => h.education);

  const rows = heads.map((h) => ({
    h,
    latest: valueAt(h.series, latest, state.basis),
    values: years.map((y) => valueAt(h.series, y, state.basis)),
  }));

  const { key, dir } = state.headSort;
  rows.sort((a, b) => {
    if (key === "name") return dir * a.h.code.localeCompare(b.h.code);
    const ai = key === "latest" ? a.latest : a.values[years.indexOf(key)];
    const bi = key === "latest" ? b.latest : b.values[years.indexOf(key)];
    return dir * ((ai ?? -Infinity) - (bi ?? -Infinity));
  });

  const table = $("head-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.textContent = "";
  tbody.textContent = "";

  const hr = document.createElement("tr");
  for (const [k, label] of [["name", "Major head"], ...years.map((y) => [y, y])]) {
    const th = document.createElement("th");
    th.textContent = label;
    th.dataset.sort = k;
    th.tabIndex = 0;
    if (k === key) th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    const go = () => {
      state.headSort = {
        key: k,
        dir: state.headSort.key === k ? -state.headSort.dir : (k === "name" ? 1 : -1),
      };
      renderHeads();
    };
    th.addEventListener("click", go);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    hr.appendChild(th);
  }
  thead.appendChild(hr);

  for (const r of rows) {
    const tr = document.createElement("tr");
    if (r.h.education) tr.className = "is-edu";
    const td = document.createElement("td");
    td.textContent = `${r.h.code} · ${r.h.name}`;
    if (r.h.education) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "education";
      td.appendChild(tag);
    }
    tr.appendChild(td);
    for (const v of r.values) {
      const cell = document.createElement("td");
      cell.className = "num";
      cell.textContent = v == null ? "—" : crore(v);
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }

  $("head-caption").textContent =
    `${rows.length} major heads, gross provision in Rs crore, summed across `
    + `every demand that books to the head.`;
}

// ------------------------------------------------------------------ chrome

function renderChrome() {
  const m = DATA.meta;
  const byline = $("byline");
  byline.textContent = "";
  for (const t of [
    `${m.years[0]} to ${m.years[m.years.length - 1]}`,
    `${m.editions.length} budget editions`,
    `${m.rows_in_long_table.toLocaleString("en-IN")} published figures`,
    `source: indiabudget.gov.in`,
    `built ${m.generated}`,
  ]) {
    const s = document.createElement("span");
    s.textContent = t;
    byline.appendChild(s);
  }

  const cov = $("coverage");
  cov.textContent = "";
  const ul = document.createElement("ul");
  const bits = [
    `Editions parsed: ${m.editions.join(", ")}. Each publishes four years at `
    + `once — actuals two years back, a revised and a budget estimate for last `
    + `year, a budget estimate for the year ahead — so a few editions cover a decade.`,
  ];
  if ((m.gap_years || []).length) {
    bits.push(`Gap: ${m.gap_years.join(", ")}. The editions covering these `
      + `years ship PDF only. That is a parser still to be written, not a `
      + `missing source.`);
  }
  bits.push(`Education departments seen across editions: ${m.moe_departments.join("; ")}.`);
  for (const b of bits) {
    const li = document.createElement("li");
    li.textContent = b;
    ul.appendChild(li);
  }
  cov.appendChild(ul);
}

function renderAll() {
  renderDefinitions();
  renderUtilisation();
  renderClassification();
  renderScale();
  renderHeads();
}

function wireControls() {
  segmented($("measure-toggle"), [
    { value: "cr", label: "Rs crore" },
    { value: "share", label: "% of Union spending" },
  ], state.measure, (v) => { state.measure = v; wireControls(); renderDefinitions(); });

  segmented($("basis-toggle"), [
    { value: "best", label: "Best available", title: "Actuals, else revised, else budget estimate" },
    { value: "A", label: "Actuals" },
    { value: "RE", label: "Revised" },
    { value: "BE", label: "Budget" },
  ], state.basis, (v) => {
    state.basis = v;
    wireControls();
    renderDefinitions();
    renderClassification();
    renderScale();
    renderHeads();
  });

  segmented($("whole-measure"), [
    { value: "cr", label: "Rs crore" },
    { value: "share", label: "% of total" },
  ], state.wholeMeasure, (v) => { state.wholeMeasure = v; wireControls(); renderDepartments(); });

  segmented($("head-filter"), [
    { value: "edu", label: "Education heads" },
    { value: "all", label: "All heads" },
  ], state.headFilter, (v) => { state.headFilter = v; wireControls(); renderHeads(); });
}

function wireOnce() {
  wireTableToggles();

  const search = $("dept-search");
  search.addEventListener("input", () => {
    state.search = search.value;
    renderDepartments();
  });

  $("export-depts").addEventListener("click", () => {
    const years = DATA.meta.years;
    const rows = [["department", "ministry", ...years]];
    for (const d of DATA.demands) {
      rows.push([d.name, d.ministry, ...years.map((y) => deptValue(d, y) ?? "")]);
    }
    download(`union-departments-${state.basis}.csv`, csv(rows));
  });

  $("export-heads").addEventListener("click", () => {
    const years = DATA.meta.years;
    const rows = [["major_head", "name", "is_education", ...years]];
    for (const h of DATA.heads) {
      rows.push([h.code, h.name, h.education,
        ...years.map((y) => valueAt(h.series, y, state.basis) ?? "")]);
    }
    download(`union-major-heads-${state.basis}.csv`, csv(rows));
  });

  let timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(renderAll, 200);
  });

  window.matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => setTimeout(renderAll, 60));
}

load()
  .then((data) => {
    DATA = data;
    $("loading").remove();
    $("content").hidden = false;
    renderChrome();
    wireControls();
    wireOnce();
    renderAll();
  })
  .catch((err) => {
    const el = $("loading");
    if (el) {
      el.textContent = `Could not load the data: ${err.message}. If you opened `
        + `this file directly, serve it over http instead: python -m http.server 8124`;
    }
    console.error(err);
  });

// Wiring. Reads data/union.json, renders the page, keeps controls in sync.
// House style and the reasoning behind it are locked in DESIGN.md.

import {
  load, loadStates, loadMap, loadOptional, pointsFor, valueAt, shareOfTotal,
  crore, lakhCrore, pct, csv, download, fyStart,
} from "./data.js";
import {
  lineChart, dumbbell, stackedBarH, rankedBars, animateIn, onFirstView,
  legend, cssVar,
} from "./charts.js";
import { scrolly, progressBar } from "./scrolly.js";
import { gauge, tierBars, treemapStory, mapChart } from "./story.js";

const state = {
  measure: "cr",
  basis: "best",
  wholeMeasure: "cr",
  headFilter: "edu",
  search: "",
  deptSort: { key: "latest", dir: -1 },
  headSort: { key: "latest", dir: -1 },
  rankMeasure: "share",
};

// The 6% of GDP target. Its history is attributed in the page footer.
const TARGET = { value: 6, label: "6% target", short: "the target" };

let DATA = null;
let STATES = null;
let MAP = null;
let ABE = null;            // centre and states together, counted once
let SCHEMES = null;        // schemes followed across their renames
let UNION_ACTUALS = null;  // audited Union spending before 2015-16

// The three scroll-driven graphics. Each is rebuilt on every render (a
// resize, a theme change) and then put back on whichever step the reader had
// reached, so re-rendering never yanks the story back to the start.
const STORY = {
  promise: { graphic: null, step: 0 },
  whopays: { graphic: null, step: 0 },
  scale: { graphic: null, step: 0 },
};

function mountStory(key, graphic) {
  STORY[key].graphic = graphic;
  if (graphic) graphic.step(STORY[key].step);
}

function wireStories() {
  const pairs = [
    ["promise", "promise-scrolly"],
    ["whopays", "whopays-scrolly"],
    ["scale", "scale-scrolly"],
  ];
  for (const [key, id] of pairs) {
    scrolly($(id), (i) => {
      STORY[key].step = i;
      if (STORY[key].graphic) STORY[key].graphic.step(i);
    });
  }
}

// The three definitions of the Union's education budget, in plain words.
const EDU_DEFS = [
  {
    key: "moe",
    slot: "--union",
    label: "Ministry of Education",
    short: "Ministry",
    note: "What the ministry's two departments are given. It is the figure in "
      + "the budget speech and in the next morning's headlines. It includes the "
      + "money the ministry passes on to state governments, but nothing that "
      + "other ministries spend on education.",
  },
  {
    key: "functional",
    slot: "--def-functional",
    label: "Education, sports and culture",
    short: "All ministries",
    note: "Everything the Union records under the education account heads, "
      + "whichever ministry spends it. Every state uses the same heads, which "
      + "makes this the only one of the three that compares across "
      + "governments. It leaves out the ministry's grants to the states, which "
      + "are recorded as transfers. Until 2014-15 most of that money was "
      + "recorded here as education, which is why this line falls by more than "
      + "half that year without a rupee less being spent.",
  },
  {
    key: "functional_narrow",
    slot: "--def-narrow",
    label: "Education alone",
    short: "Without sports",
    note: "The same, without sports and youth services and art and culture, "
      + "which the account heads group with education.",
  },
];

const BASIS_WORD = { A: "actual", RE: "revised", BE: "budget" };

function setAll(selector, text) {
  for (const el of document.querySelectorAll(selector)) el.textContent = text;
}

function byFy(a, b) { return fyStart(a) - fyStart(b); }

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

  // How many whole ministries and departments are smaller than the gap
  // between definitions - a sense of scale for a number that is otherwise
  // just large.
  const demandSizes = DATA.demands
    .map((d) => valueAt(d.series, latest, "BE"))
    .filter((v) => v != null && v > 0);
  const smaller = demandSizes.filter((v) => v < spread).length;

  $("hero-spread").textContent = crore(spread);
  $("hero-spread-note").textContent =
    `crore separates the largest and smallest of the three in ${latest}: more `
    + `than the entire budget of ${smaller} of the Union's ${demandSizes.length} `
    + `ministries and departments.`;

  const stats = $("definition-stats");
  stats.textContent = "";
  for (const def of EDU_DEFS) {
    const series = DATA.education[def.key].series;
    const v = valueAt(series, latest, "BE");
    const share = shareOfTotal(series, DATA.totals, latest, "BE");
    const wrap = document.createElement("div");
    wrap.className = "stat";
    const dt = document.createElement("dt");
    const k = document.createElement("i");
    k.className = "key";
    k.style.background = cssVar(def.slot, "#e65d31");
    const name = document.createElement("span");
    name.textContent = def.label;
    dt.append(k, name);
    const dd = document.createElement("dd");
    dd.textContent = lakhCrore(v);
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = `${pct(share)} of all Union spending · ${latest} budget`;
    dd.appendChild(sub);
    wrap.append(dt, dd);
    stats.appendChild(wrap);
  }

  const series = EDU_DEFS.map((def) => ({
    label: def.label,
    short: def.short,
    color: cssVar(def.slot, "#e65d31"),
    points: seriesPoints(DATA.education[def.key].series),
  }));
  const peak = Math.max(...series.flatMap((s) => s.points.map((p) => p.value)));

  const hi = Math.max(...vals);
  const lo = Math.min(...vals);
  const annotations = state.measure === "share" ? [] : [{
    year: latest,
    value: hi,
    from: hi,
    to: lo,
    headline: `${crore(spread)} cr apart`,
    detail: "same year, same government",
    dx: -14,
    dy: -34,
    anchor: "end",
  }];

  // The ministry's budget fell sharply in 2015-16 while total Union spending
  // barely moved. That was the first year of the larger tax devolution to the
  // states, which the note states as timing, not as a proven cause.
  const drop = "2015-16";
  const before = valueAt(DATA.education.moe.series, "2014-15", "BE");
  const after = valueAt(DATA.education.moe.series, drop, "BE");
  if (state.measure !== "share" && before && after && after < before * 0.92) {
    annotations.push({
      year: drop,
      value: after,
      headline: `${(100 * (before - after) / before).toFixed(0)}% fall in 2015-16`,
      detail: "the year the states' share of central taxes rose to 42%",
      dx: 10,
      dy: -95,
      anchor: "start",
    });
  }

  // The two account-head lines fall by more than half in 2014-15. Nothing was
  // cut: from that year the Union's money for schemes the states run was
  // routed through state budgets and recorded as grants, not as education.
  const reroute = "2014-15";
  const fBefore = valueAt(DATA.education.functional.series, "2013-14", "BE");
  const fAfter = valueAt(DATA.education.functional.series, reroute, "BE");
  if (state.measure !== "share" && fBefore && fAfter && fAfter < fBefore * 0.6) {
    annotations.push({
      year: reroute,
      value: fAfter,
      headline: "2014-15: the money was re-booked",
      detail: "grants to states moved off the education heads",
      dx: -14,
      dy: 40,
      anchor: "end",
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
      label: "dashed line, hollow dot: an estimate, not audited spending",
      color: cssVar("--ink-muted", "#8a9099"),
      dash: true,
    },
  ]);

  $("edu-caption").textContent = state.measure === "share"
    ? "Each definition as a share of all Union spending in the same year. The "
      + "shaded band is the gap between the widest and narrowest."
    : "Rupees crore at current prices. The shaded band is the gap between the "
      + "widest and narrowest definition each year.";

  const years = DATA.meta.years;
  buildTable($("edu-table"),
    ["Year", ...EDU_DEFS.map((d) => d.label), "All Union spending"],
    years.map((year) => ({
      cells: [
        year,
        ...EDU_DEFS.map((d) => crore(valueAt(DATA.education[d.key].series, year, state.basis))),
        crore(valueAt(DATA.totals, year, state.basis)),
      ],
    })));

  const note = $("definitions-note");
  note.textContent = "";
  const para = (head, body) => {
    const p = document.createElement("p");
    const b = document.createElement("strong");
    b.textContent = head + " ";
    p.append(b, document.createTextNode(body));
    note.appendChild(p);
  };
  for (const def of EDU_DEFS) para(def.label + ".", def.note);
  para("Why the ministry's figure is the largest.",
    "Its biggest single line is a grant to the states, recorded as a transfer "
    + "rather than as education. Chapter six follows that money.");
}

// ------------------------------------------------- 2. the 6% of GDP promise

function abeYears() {
  return ABE ? Object.keys(ABE.national).sort(byFy) : [];
}

function renderPromise() {
  if (!ABE) return;
  const nat = ABE.national;
  const years = abeYears();
  const actual = years.filter((y) => nat[y].estimate_type === "A");
  const y = actual[actual.length - 1];
  const narrow = nat[y].education_departments.pct_gdp.total;
  const broad = nat[y].education_and_other_departments.pct_gdp.total;
  const two = (v) => `${v.toFixed(2)}%`;

  // "Never passed X": round the highest value up, so the claim stays strictly
  // true rather than true-after-rounding.
  const highest = Math.max(...years.map(
    (k) => nat[k].education_and_other_departments.pct_gdp.total));
  $("sf-max").textContent = `${(Math.ceil(highest * 10) / 10).toFixed(1)}%`;

  $("g-narrow").textContent = two(narrow);
  $("g-broad").textContent = two(broad);
  setAll(".g-year", y);
  $("g-gap").textContent = `${(broad - narrow).toFixed(1)} points`;
  $("g-short").textContent = `${(TARGET.value - broad).toFixed(1)} points`;

  mountStory("promise", gauge($("gauge-plot"), {
    marks: [
      {
        value: narrow,
        label: `Education departments, ${y}`,
        short: "Education departments",
        detail: "education departments only",
      },
      {
        value: broad,
        label: `All departments, ${y}`,
        short: "All departments",
        detail: "with other departments",
      },
    ],
    target: TARGET,
    max: 7,
    format: (v) => (Number.isInteger(v) ? `${v}%` : two(v)),
    ariaLabel:
      `Public spending on education by the centre and states together in ${y}: `
      + `${two(narrow)} of GDP through education departments, ${two(broad)} `
      + `counting other departments too, against a target of 6%.`,
  }));

  // Two decades of the same answer.
  const ink = cssVar("--ink", "#111418");
  const muted = cssVar("--ink-muted", "#7c838c");
  const target = cssVar("--target", "#b77d06");
  const pointsOf = (key) => years.map((k) => ({
    year: k,
    value: nat[k][key].pct_gdp.total,
    basis: nat[k].estimate_type,
  }));

  // The ministry's figures before 2011-12 divide by an older GDP series than
  // those after, so the line is broken there rather than joined across it.
  const rebased = years.find((k) => fyStart(k) === 2011);
  lineChart($("abe-plot"), {
    series: [
      { label: "All departments", short: "All departments", color: ink,
        points: pointsOf("education_and_other_departments") },
      { label: "Education departments only", short: "Education depts", color: muted,
        points: pointsOf("education_departments") },
    ],
    years,
    format: (v) => `${v}%`,
    tipFormat: (v) => `${v.toFixed(2)}% of GDP`,
    reference: { value: TARGET.value, label: "6% target", color: target },
    breakBefore: rebased ? [rebased] : [],
    height: 400,
  });

  legend($("abe-legend"), [
    { label: "All departments, centre and states", color: ink },
    { label: "Education departments only", color: muted },
    { label: "The 6% target", color: target },
    {
      label: "dashed line, hollow dot: an estimate, not audited spending",
      color: muted,
      dash: true,
    },
  ]);

  // Say that 2020-21 is flattered by the fall in GDP only if GDP did fall.
  const covid = nat["2020-21"];
  const pre = nat["2019-20"];
  const gdpFell = covid && pre && covid.gdp && pre.gdp && covid.gdp < pre.gdp;
  $("abe-caption").textContent =
    "Public spending on education by the centre and the states together, as "
    + "a share of GDP, counting each rupee once, by the government that spends "
    + "it. The Ministry of Education's own figures."
    + (rebased ? ` The line breaks at ${rebased}, where GDP was rebased.` : "")
    + (gdpFell ? " 2020-21, a revised estimate, is lifted by that year's fall in GDP." : "");

  buildTable($("abe-table"),
    ["Year", "Education departments", "All departments", "Basis"],
    years.map((k) => ({
      cells: [
        k,
        two(nat[k].education_departments.pct_gdp.total),
        two(nat[k].education_and_other_departments.pct_gdp.total),
        BASIS_WORD[nat[k].estimate_type] || nat[k].estimate_type,
      ],
    })));
}

// ------------------------------------------------------------- 3. who pays

function stateAll(measure) {
  return STATES && STATES.series.ALL ? STATES.series.ALL[measure] : null;
}

function bestPoint(byYear, year) {
  const byType = byYear[year] || {};
  const basis = ["A", "RE", "BE"].find((t) => byType[t] != null);
  return basis ? { year, value: byType[basis], basis } : null;
}

function statTiles(host, tiles) {
  host.textContent = "";
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
    host.appendChild(wrap);
  }
}

function renderWhoPays() {
  if (!STATES) return;
  const edu = stateAll("education_spend");
  const unionF = DATA.education.functional.series;

  // Both tiers must be read on the same estimate type in any given year.
  // Comparing the Union's revised estimate with the states' budget estimate
  // would put a ratio on screen that compares two different kinds of number.
  const years = STATES.meta.years
    .filter((y) => edu[y] && unionF[y])
    .filter((y) => fyStart(y) >= 2002)
    .filter((y) => ["A", "RE", "BE"].some(
      (t) => edu[y][t] != null && unionF[y][t] != null));

  const sharedBasis = (y) => ["A", "RE", "BE"].find(
    (t) => edu[y][t] != null && unionF[y][t] != null);

  const statePts = years.map((y) => {
    const t = sharedBasis(y);
    return { year: y, value: edu[y][t], basis: t };
  });
  const unionPts = years.map((y) => {
    const t = sharedBasis(y);
    return { year: y, value: unionF[y][t], basis: t };
  });
  if (!statePts.length || !unionPts.length) return;

  const sLast = statePts[statePts.length - 1];
  const uLast = unionPts[unionPts.length - 1];
  const ratio = sLast.value / uLast.value;

  // The same comparison, counted the other honest way: every rupee once, by
  // the government that spends it. Shown beside the account-heads ratio so
  // the reader can see the two agree on the point, if not the size.
  let abeShare = null;
  let abeYear = null;
  if (ABE) {
    const ys = abeYears().filter((k) => ABE.national[k].estimate_type === "A");
    abeYear = ys[ys.length - 1];
    const wide = ABE.national[abeYear].education_and_other_departments;
    abeShare = (100 * wide.states) / wide.total;
  }
  setAll(".t-year", uLast.year);

  statTiles($("whopays-stats"), [
    {
      label: "States and union territories",
      value: lakhCrore(sLast.value),
      sub: `${sLast.year} ${BASIS_WORD[sLast.basis]}, education, sports and culture`,
      colour: cssVar("--states", "#3d8bff"),
    },
    {
      label: "The Union",
      value: lakhCrore(uLast.value),
      sub: "the same account heads, the same year",
      colour: cssVar("--union", "#e65d31"),
    },
    abeShare != null ? {
      label: "Counted once, by who spends it",
      value: pct(abeShare, 0),
      sub: `of all public spending on education is the states', ${abeYear}`,
      colour: cssVar("--states", "#3d8bff"),
    } : {
      label: "Ratio",
      value: `${ratio.toFixed(1)} : 1`,
      sub: "states to the Union",
      colour: cssVar("--ink", "#15181c"),
    },
  ]);

  // The scroll-driven version: the two tiers on one scale, counted.
  const uColour = cssVar("--union", "#e65d31");
  const sColour = cssVar("--states", "#3d8bff");
  $("tier-union").textContent = lakhCrore(uLast.value);
  $("tier-states").textContent = lakhCrore(sLast.value);
  $("tier-ratio").textContent = `${ratio.toFixed(1)} to 1`;
  // The same comparison in the last year before 2014-15, read on one basis.
  const pre = statePts.filter((p) => fyStart(p.year) < 2014);
  if (pre.length) {
    const sp = pre[pre.length - 1];
    const up = unionPts.find((p) => p.year === sp.year);
    if (up) $("tier-before").textContent = `${(sp.value / up.value).toFixed(1)} to 1 in ${sp.year}`;
  }
  mountStory("whopays", tierBars($("tier-plot"), {
    rows: [
      { label: `Union, ${uLast.year}`, value: uLast.value, color: uColour },
      { label: `States and union territories, ${sLast.year}`, value: sLast.value, color: sColour },
    ],
    format: (v) => lakhCrore(v),
    ariaLabel:
      `Education, sports, art and culture, ${sLast.year} ${sLast.basis}: `
      + `the Union ${lakhCrore(uLast.value)}, the states and union territories `
      + `${lakhCrore(sLast.value)}, a ratio of ${ratio.toFixed(1)} to 1.`,
  }));

  const peak = Math.max(...statePts.map((p) => p.value));
  lineChart($("whopays-plot"), {
    series: [
      {
        label: "States and union territories",
        short: "States",
        color: cssVar("--states", "#3d8bff"),
        points: statePts,
      },
      {
        label: "Union government",
        short: "Union",
        color: cssVar("--union", "#e65d31"),
        points: unionPts,
      },
    ],
    years,
    format: axisFormatter(peak),
    tipFormat: (v) => `${crore(v)} cr`,
    annotation: (() => {
      const after = unionPts.find((p) => p.year === "2014-15");
      return after ? [{
        year: "2014-15",
        value: after.value,
        headline: "2014-15",
        detail: "Union scheme money starts passing through state budgets",
        dx: 12,
        dy: -40,
        anchor: "start",
      }] : [];
    })(),
    height: 400,
  });

  legend($("whopays-legend"), [
    { label: "States and union territories", color: cssVar("--states", "#3d8bff") },
    { label: "The Union", color: cssVar("--union", "#e65d31") },
    {
      label: "dashed line, hollow dot: an estimate, not audited spending",
      color: cssVar("--ink-muted", "#8a9099"),
      dash: true,
    },
  ]);

  $("whopays-caption").textContent =
    "Rupees crore at current prices, on the education, sports and culture "
    + "account heads that the Union and every state share. In 2014-15 the "
    + "Union's line falls and the states' rises by about the same amount: the "
    + "Union's money for jointly run schemes began passing through state "
    + "budgets that year, so the books changed, not the spending.";

  buildTable($("whopays-table"),
    ["Year", "States and UTs", "Union", "Ratio"],
    years.map((y) => {
      const sp = statePts.find((p) => p.year === y);
      const up = unionPts.find((p) => p.year === y);
      return {
        cells: [
          y,
          sp ? crore(sp.value) : "—",
          up ? crore(up.value) : "—",
          sp && up ? `${(sp.value / up.value).toFixed(1)} : 1` : "—",
        ],
      };
    }));

  const grants = DATA.moe_heads.find((h) => h.code === "3601");
  const g = grants ? valueAt(grants.series, latestYear(), "BE") : null;
  const note = $("whopays-note");
  note.textContent = "";
  const b = document.createElement("strong");
  b.textContent = "Why the two budgets can't simply be added. ";
  note.appendChild(b);
  note.appendChild(document.createTextNode(
    (g != null
      ? `The Ministry of Education passes ${lakhCrore(g)} of its ${latestYear()} `
        + `budget to state governments as grants. `
      : "The Ministry of Education passes much of its budget to state "
        + "governments as grants. ")
    + "The states spend that money and record it as their own education "
    + "spending, so adding the ministry's budget to theirs counts it twice."
    + (abeShare != null
      ? ` Counted once, by the government that actually spends it, the states `
        + `account for ${pct(abeShare, 0)} of public spending on education.`
      : "")));
}

// -------------------------------------- 4. education's share of own budgets

function renderStateShare() {
  if (!STATES) return;
  const edu = stateAll("education_spend");
  const agg = stateAll("aggregate_expenditure");
  const soc = stateAll("social_services");
  const years = STATES.meta.years.filter((y) => edu[y] && agg[y]);

  // Every share reads numerator and denominator on the same estimate basis.
  const shareOf = (num) => years.map((y) => {
    const basis = ["A", "RE", "BE"].find(
      (t) => num[y] && num[y][t] != null && agg[y][t] != null);
    return basis
      ? { year: y, value: (100 * num[y][basis]) / agg[y][basis], basis }
      : null;
  }).filter(Boolean);
  const eduPts = shareOf(edu);
  const socPts = soc ? shareOf(soc) : [];
  if (!eduPts.length) return;

  const within = (y) => {
    const t = ["A", "RE", "BE"].find(
      (k) => edu[y] && soc && soc[y] && edu[y][k] != null && soc[y][k] != null);
    return t ? (100 * edu[y][t]) / soc[y][t] : null;
  };

  const fromYear = "2010-11";
  const from = eduPts.find((p) => p.year === fromYear);
  const to = eduPts[eduPts.length - 1];
  const socFrom = socPts.find((p) => p.year === fromYear);
  const socTo = socPts[socPts.length - 1];
  setAll(".ss-from", fromYear);
  if (socFrom) $("ss-social-from").textContent = pct(socFrom.value, 1);
  if (socTo) $("ss-social").textContent = pct(socTo.value, 1);
  const wFrom = within(fromYear);
  const wTo = within(to.year);
  if (wFrom != null) $("ss-within-from").textContent = pct(wFrom, 1);
  if (wTo != null) $("ss-within-to").textContent = pct(wTo, 1);

  const annotations = [];
  if (from && to) {
    annotations.push({
      year: to.year,
      value: to.value,
      headline: `${to.value.toFixed(1)}% in ${to.year}`,
      detail: `down from ${from.value.toFixed(1)}% in ${from.year}`,
      dx: -12,
      dy: 44,
      anchor: "end",
    });
  }
  const odd = eduPts.find((p) => p.year === "2004-05");
  if (odd) {
    annotations.push({
      year: "2004-05",
      value: odd.value,
      headline: "2004-05",
      detail: "total spending jumped; education did not fall",
      dx: 12,
      dy: 40,
      anchor: "start",
    });
  }

  const blue = cssVar("--states", "#3d8bff");
  const grey = cssVar("--ink-muted", "#7c838c");
  lineChart($("stateshare-plot"), {
    series: [
      { label: "Social sector", short: "Social sector", color: grey, points: socPts },
      { label: "Education", short: "Education", color: blue, points: eduPts },
    ],
    years,
    format: (v) => `${v.toFixed(0)}%`,
    tipFormat: (v) => `${v.toFixed(1)}% of state spending`,
    annotation: annotations,
    height: 420,
  });

  legend($("stateshare-legend"), [
    { label: "Education, sports and culture", color: blue },
    { label: "The whole social sector: education, health, welfare, housing and more", color: grey },
    {
      label: "dashed line, hollow dot: an estimate, not audited spending",
      color: grey,
      dash: true,
    },
  ]);

  $("stateshare-caption").textContent =
    "Share of total state spending, all states and union territories together. "
    + "In 2004-05 total spending jumped by half while education did not fall, "
    + "so that year's dip is in the total, not in education.";

  buildTable($("stateshare-table"),
    ["Year", "Education", "Social sector", "Education's share of social", "Basis"],
    eduPts.map((p) => {
      const sp = socPts.find((q) => q.year === p.year);
      const w = within(p.year);
      return {
        cells: [
          p.year,
          pct(p.value, 1),
          sp ? pct(sp.value, 1) : "—",
          w != null ? pct(w, 1) : "—",
          BASIS_WORD[p.basis] || p.basis,
        ],
      };
    }));

  renderRanking();
}

function renderRanking() {
  if (!STATES) return;
  const byShare = state.rankMeasure === "share";
  const entities = STATES.states.filter((s) => s.kind !== "aggregate");

  const items = [];
  for (const e of entities) {
    const ser = STATES.series[e.code];
    if (!ser) continue;
    const edu = ser.education_spend || {};
    const den = byShare ? (ser.aggregate_expenditure || {}) : (ser.gsdp || {});
    let year = null;
    let value = null;
    for (const y of [...STATES.meta.years].reverse()) {
      const basis = edu[y]
        ? ["BE", "RE", "A"].find((t) => edu[y][t] != null)
        : null;
      if (!basis) continue;
      const d = byShare
        ? (den[y] && den[y][basis] != null ? den[y][basis] : null)
        : (typeof den[y] === "number" ? den[y] : null);
      if (d == null || d === 0) continue;
      year = y;
      value = (100 * edu[y][basis]) / d;
      break;
    }
    if (value == null) continue;
    items.push({
      code: e.code,
      name: e.name,
      value,
      detail: byShare ? "share of its own budget" : "share of GSDP",
      extra: { label: "year", value: year },
    });
  }
  if (!items.length) return;
  items.sort((a, b) => b.value - a.value);

  let refValue = null;
  const allSer = STATES.series.ALL;
  if (byShare && allSer) {
    for (const y of [...STATES.meta.years].reverse()) {
      const e = allSer.education_spend[y];
      const a = allSer.aggregate_expenditure[y];
      const basis = e && a
        ? ["BE", "RE", "A"].find((t) => e[t] != null && a[t] != null)
        : null;
      if (basis) { refValue = (100 * e[basis]) / a[basis]; break; }
    }
  }

  renderMap();

  rankedBars($("rank-plot"), {
    items,
    format: (v) => `${v.toFixed(1)}%`,
    highlight: [items[0].name, items[items.length - 1].name],
    reference: refValue
      ? { value: refValue, label: `all states, ${refValue.toFixed(1)}%` }
      : null,
  });

  const top = items[0];
  const bottom = items[items.length - 1];
  const spread = top.value - bottom.value;
  $("rank-heading").textContent = byShare
    ? `${top.name} gives education ${pct(top.value, 1)} of its budget; `
      + `${bottom.name}, ${pct(bottom.value, 1)}`
    : `${top.name} spends ${pct(top.value, 1)} of its economy on education; `
      + `${bottom.name}, ${pct(bottom.value, 1)}`;

  // Compare the spread between states with how far the all-states average
  // has moved over the whole period.
  let trend = "";
  if (byShare && allSer) {
    const ys = STATES.meta.years.filter((y) => {
      const e = allSer.education_spend[y];
      const a = allSer.aggregate_expenditure[y];
      return e && a && ["A", "RE", "BE"].some((t) => e[t] != null && a[t] != null);
    });
    const at = (y) => {
      const e = allSer.education_spend[y];
      const a = allSer.aggregate_expenditure[y];
      const t = ["A", "RE", "BE"].find((k) => e[k] != null && a[k] != null);
      return (100 * e[t]) / a[t];
    };
    if (ys.length > 1) {
      const change = Math.abs(at(ys[0]) - at(ys[ys.length - 1]));
      if (change > 0) {
        trend = ` That ${spread.toFixed(1)}-point gap is ${(spread / change).toFixed(1)} `
          + `times the ${change.toFixed(1)}-point fall in the all-states average `
          + `since ${ys[0]}: where a state sits on this list is a bigger `
          + `difference than the national trend.`;
      }
    }
  }
  $("rank-caption").textContent = byShare
    ? `Education as a share of each state's own spending, latest year.${trend}`
    : `Education spending as a share of each state's economy, latest year. A `
      + `larger share of a smaller economy can still mean less per child, so `
      + `this ranking and the one by budget share answer different questions.`;
}

// ------------------------------------------------- the map, through time

const MAPSTATE = { years: [], index: -1, timer: null, chart: null, measure: null };

// Each state's figure for one year. Numerator and denominator are always read
// on the same estimate basis, so a share never mixes a budget estimate with an
// audited outturn.
function stateValuesFor(year, byShare) {
  const out = new Map();
  for (const e of STATES.states) {
    if (e.kind === "aggregate") continue;
    const ser = STATES.series[e.code];
    if (!ser) continue;
    const edu = (ser.education_spend || {})[year];
    if (!edu) continue;
    if (byShare) {
      const agg = (ser.aggregate_expenditure || {})[year];
      if (!agg) continue;
      const t = ["A", "RE", "BE"].find((k) => edu[k] != null && agg[k] != null);
      if (t && agg[t]) out.set(e.code, (100 * edu[t]) / agg[t]);
    } else {
      const gsdp = (ser.gsdp || {})[year];
      const t = ["A", "RE", "BE"].find((k) => edu[k] != null);
      if (t && typeof gsdp === "number" && gsdp) out.set(e.code, (100 * edu[t]) / gsdp);
    }
  }
  return out;
}

function stopPlay() {
  if (MAPSTATE.timer) clearInterval(MAPSTATE.timer);
  MAPSTATE.timer = null;
  const btn = $("map-play");
  if (btn) {
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", "Play through the years");
    btn.querySelector("path").setAttribute("d", "M3 1.5v11l9-5.5z");
  }
}

function showYear(i) {
  const years = MAPSTATE.years;
  if (!years.length || !MAPSTATE.chart) return;
  MAPSTATE.index = Math.max(0, Math.min(years.length - 1, i));
  const year = years[MAPSTATE.index];
  $("map-year").textContent = year;
  $("map-range").value = String(MAPSTATE.index);
  MAPSTATE.chart.update(stateValuesFor(year, state.rankMeasure === "share"), year);
}

function togglePlay() {
  if (MAPSTATE.timer) { stopPlay(); return; }
  const last = MAPSTATE.years.length - 1;
  if (MAPSTATE.index >= last) showYear(0);
  const btn = $("map-play");
  btn.setAttribute("aria-pressed", "true");
  btn.setAttribute("aria-label", "Pause");
  btn.querySelector("path").setAttribute("d", "M3 1.5h3v11H3zM8 1.5h3v11H8z");
  MAPSTATE.timer = setInterval(() => {
    if (MAPSTATE.index >= MAPSTATE.years.length - 1) { stopPlay(); return; }
    showYear(MAPSTATE.index + 1);
  }, 650);
}

function renderMap() {
  if (!STATES || !MAP) return;
  stopPlay();
  const byShare = state.rankMeasure === "share";
  const years = STATES.meta.years.filter((y) => stateValuesFor(y, byShare).size > 0);
  if (!years.length) return;

  // One colour scale for every year, which is what makes the animation
  // honest. Its ends are the 2nd and 98th percentiles across all states and
  // years, so a handful of small entities cannot wash out everyone else;
  // values beyond them take the end colours, and the key says so.
  const all = years.flatMap((y) => [...stateValuesFor(y, byShare).values()])
    .sort((a, b) => a - b);
  const q = (p) => all[Math.round(p * (all.length - 1))];
  const domain = [q(0.02), q(0.98)];
  const fmt = (v) => `${v.toFixed(1)}%`;

  MAPSTATE.chart = mapChart($("map-plot"), {
    features: MAP.features,
    format: fmt,
    legendFormat: (v, end) => (end === 0 ? "\u2264 " : "\u2265 ") + fmt(v),
    label: byShare ? "share of own budget" : "share of GSDP",
    domain,
    noDataLabel: "no figure this year",
    ariaLabel: byShare
      ? "Map of India: education as a share of each state's own budget, by year."
      : "Map of India: education spending as a share of each state's GSDP, by year.",
  });

  const changed = MAPSTATE.measure !== state.rankMeasure;
  MAPSTATE.measure = state.rankMeasure;
  MAPSTATE.years = years;
  const range = $("map-range");
  range.max = String(years.length - 1);
  if (changed || MAPSTATE.index < 0 || MAPSTATE.index > years.length - 1) {
    MAPSTATE.index = years.length - 1;
  }
  showYear(MAPSTATE.index);

  $("map-caption").textContent = byShare
    ? `Darker blue is a larger share of the state's own budget, on one scale `
      + `for every year, so a change of colour is a change in the share. `
      + `Chhattisgarh, Jharkhand and Uttarakhand were created in 2000 and `
      + `Telangana in 2014, so they join the map then. Union territories without `
      + `a legislature have no budget of their own and stay grey.`
    : `Darker blue is a larger share of the state's economy. These figures `
      + `start in ${years[0]}.`;
}

// --------------------------------------------------- 5. promise and outturn

// The ministry's audited spending for a year: from the budget documents where
// they carry it (2015-16 on), otherwise from the separate statement of
// ministries' actual expenditure that earlier editions printed.
function moeActual(year) {
  const direct = valueAt(DATA.education.moe.series, year, "A");
  if (direct != null) return direct;
  const rec = UNION_ACTUALS && UNION_ACTUALS.years[year];
  if (!rec || !rec.departments) return null;
  const parts = rec.departments.filter((d) => /school education|higher education|elementary education|secondary/i.test(d.key || d.name));
  if (!parts.length) return null;
  return parts.reduce((a, d) => a + (d.total || 0), 0);
}

function renderUtilisation() {
  const series = DATA.education.moe.series;
  const all = DATA.meta.years.map((year) => ({
    year,
    be: valueAt(series, year, "BE"),
    re: valueAt(series, year, "RE"),
    a: moeActual(year),
  }));
  const rows = all.filter((r) => r.be != null && r.a != null);
  if (!rows.length) return;
  const ratio = (r) => (100 * r.a) / r.be;
  const mean = (rs) => rs.reduce((acc, r) => acc + ratio(r), 0) / rs.length;

  const split = 2010;
  const early = rows.filter((r) => fyStart(r.year) < split);
  const late = rows.filter((r) => fyStart(r.year) >= split);
  if (early.length) {
    $("u-early-span").textContent = `${early[0].year} to ${early[early.length - 1].year}`;
    $("u-early").textContent = pct(mean(early), 0);
  }
  if (late.length) {
    $("u-late-from").textContent = late[0].year;
    $("u-late").textContent = pct(mean(late), 0);
  }

  const utilPeak = Math.max(...rows.flatMap((r) => [r.be, r.re, r.a].filter((v) => v != null)));
  dumbbell($("util-plot"), {
    rows,
    format: axisFormatter(utilPeak),
    height: Math.max(260, rows.length * 32 + 80),
    labelOf: () => "",
  });

  legend($("util-legend"), [
    { label: "Budget estimate, February", color: cssVar("--union", "#e65d31"), hollow: true },
    { label: "Revised estimate (tick)", color: cssVar("--ink-muted", "#8a9099") },
    { label: "Audited spending", color: cssVar("--union", "#e65d31"), shape: "rect" },
  ]);

  $("util-caption").textContent =
    "Ministry of Education, Rs crore. Before 2015-16 the audited figures are "
    + "the provisional ones the budget documents first published.";

  buildTable($("util-table"),
    ["Year", "Budget estimate", "Revised", "Audited", "Audited as % of budget"],
    all.map((r) => ({
      cells: [
        r.year, crore(r.be), crore(r.re), crore(r.a),
        r.be && r.a ? pct(ratio(r), 1) : "—",
      ],
    })));

  // The ministry's largest scheme, since the 2018-19 merger that created it.
  const note = $("util-note");
  note.textContent = "";
  const ss = SCHEMES && SCHEMES.schemes.find((x) => x.id === "samagra_shiksha");
  if (!ss) { note.hidden = true; return; }
  const yrs = Object.keys(ss.total)
    .filter((y) => fyStart(y) >= 2018 && ss.total[y].BE && ss.total[y].A)
    .sort(byFy);
  const ministry = rows.filter((r) => yrs.includes(r.year));
  if (!yrs.length || !ministry.length) { note.hidden = true; return; }
  const ssRatio = (y) => (100 * ss.total[y].A) / ss.total[y].BE;
  const ssMean = yrs.reduce((acc, y) => acc + ssRatio(y), 0) / yrs.length;
  const worst = yrs.reduce((w, y) => (ssRatio(y) < ssRatio(w) ? y : w), yrs[0]);
  const lower = ssMean < mean(ministry);
  const b = document.createElement("strong");
  b.textContent = lower
    ? "The ministry's largest scheme falls further short. "
    : "The ministry's largest scheme. ";
  note.hidden = false;
  note.append(b, document.createTextNode(
    `Samagra Shiksha, the school programme the Union runs jointly with the `
    + `states, has spent ${pct(ssMean, 1)} of its budget estimate on average `
    + `since it was created in ${yrs[0]}, against ${pct(mean(ministry), 1)} `
    + `for the ministry as a whole over the same years. Its worst year was `
    + `${worst}, at ${pct(ssRatio(worst), 1)}.`));
}

// ------------------------------------------------------- 3. classification

function renderClassification() {
  const latest = latestYear();
  const years = axisYears();
  const accent = cssVar("--union", "#e65d31");
  const grants = cssVar("--states", "#3d8bff");
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
      detail: "spent, and recorded as education, by the states",
    } : null,
  });

  legend($("class-legend"), [
    { label: "Grants to states and union territories", color: grants, shape: "rect" },
    { label: "Education, recorded by the Union itself", color: accent, shape: "rect" },
    { label: "Everything else", color: dim, shape: "rect" },
  ]);

  $("class-caption").textContent =
    "Ministry of Education spending by account head, Rs crore, before "
    + "receipts are netted off. The switch in 2014-15 is a change in how the "
    + "money is recorded, not where it went: from that year the Union's money "
    + "for jointly run schemes has been routed through state budgets and "
    + "recorded as grants to them. Hover a segment for its name.";

  buildTable($("class-table"),
    ["Major head", ...DATA.meta.years],
    layers.map((l) => ({
      cls: l.education ? "is-edu" : "",
      cells: [l.label, ...DATA.meta.years.map((y) => crore(l.values[y] ?? null))],
    })));

  const g = g3601 ? g3601.values[latest] ?? null : null;
  const edu2202 = layers.find((l) => l.code === "2202");
  const e = edu2202 ? edu2202.values[latest] ?? null : null;

  if (g != null) $("c-grants").textContent = lakhCrore(g);
  if (e != null) $("c-general").textContent = lakhCrore(e);
  setAll(".c-year", latest);

  let combined = "";
  if (ABE) {
    const ys = abeYears().filter((k) => ABE.national[k].estimate_type === "A");
    const y = ys[ys.length - 1];
    combined = ` The only sound combined figure counts each rupee by the `
      + `government that spends it: ${pct(ABE.national[y].education_and_other_departments.pct_gdp.total, 2)} `
      + `of GDP in ${y}.`;
  }
  const note = $("double-count-note");
  note.textContent = "";
  const strong = document.createElement("strong");
  strong.textContent = "The double-counting trap. ";
  note.appendChild(strong);
  note.appendChild(document.createTextNode(
    "The grants are spent once, by the states, but they appear in both "
    + "governments' budgets: in the Union's as a transfer and in the states' "
    + "as education. That is why the Union's own education figure understates "
    + "what the centre pays for, and why adding the two budgets overstates the "
    + "total." + combined));
}

// ------------------------------------------------------------- 4. the scale

function isEduDept(name) {
  return /school education|higher education|elementary education|secondary education/i
    .test(name);
}

function renderScale() {
  const latest = latestYear();
  const accent = cssVar("--union", "#e65d31");
  const dim = cssVar("--dim", "#262c35");
  const ink = cssVar("--ink", "#f1eee8");

  const items = DATA.demands
    .map((d) => {
      const edu = isEduDept(d.name);
      const interest = /^interest payments$/i.test(d.name.trim());
      return {
        name: d.name,
        shortName: edu ? d.name.replace(/^Department of /i, "") : d.name,
        value: valueAt(d.series, latest, "BE") ?? 0,
        group: edu ? "education" : (interest ? "interest" : null),
      };
    })
    .filter((d) => d.value > 0);

  const total = items.reduce((a, d) => a + d.value, 0);
  const edu = items.filter((d) => d.group === "education").reduce((a, d) => a + d.value, 0);
  const interest = items.filter((d) => d.group === "interest").reduce((a, d) => a + d.value, 0);

  $("scale-total").textContent = lakhCrore(total);
  $("scale-interest").textContent = pct((100 * interest) / total, 1);
  $("scale-education").textContent = pct((100 * edu) / total, 1);
  $("scale-ratio").textContent = `${(interest / edu).toFixed(1)} rupees`;
  setAll(".sc-year", latest);

  mountStory("scale", treemapStory($("treemap-plot"), {
    items,
    format: (v) => `${crore(v)} cr`,
    ariaLabel:
      `The Union budget for ${latest}, every demand for grants drawn to scale. `
      + `Interest payments are ${pct((100 * interest) / total, 1)} of it; the `
      + `Ministry of Education's two departments are ${pct((100 * edu) / total, 1)}.`,
  }));

  statTiles($("scale-stats"), [
    {
      label: "Education's share",
      value: pct((100 * edu) / total),
      sub: `${lakhCrore(edu)} of ${lakhCrore(total)} · ${latest} budget`,
      colour: accent,
    },
    {
      label: "Interest payments",
      value: pct((100 * interest) / total),
      sub: `${(interest / edu).toFixed(1)} times the education ministry`,
      colour: ink,
    },
    {
      label: "Ministries and departments",
      value: String(items.length),
      sub: "each with its own demand for grants",
      colour: dim,
    },
  ]);

  legend($("treemap-legend"), [
    { label: "Ministry of Education", color: accent, shape: "rect" },
    { label: "Interest payments", color: ink, shape: "rect" },
    { label: "Every other demand", color: dim, shape: "rect" },
  ]);

  $("treemap-caption").textContent =
    `Every ministry and department in the ${latest} budget, sized by what it `
    + `is given. Hover a tile for its figure.`;

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
    `${rows.length} of ${DATA.demands.length} ministries and departments. `
    + (state.wholeMeasure === "share"
      ? "Per cent of all Union spending."
      : "Rupees crore, after receipts are netted off.");
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
    `${rows.length} account heads, Rs crore before receipts are netted off, `
    + `across every ministry that records spending under them.`;
}

// ------------------------------------------------------------------ chrome

function renderChrome() {
  const m = DATA.meta;
  const u0 = m.years[0];
  const uN = m.years[m.years.length - 1];
  const byline = $("byline");
  byline.textContent = "";
  const items = [`The Union, ${u0} to ${uN}`];
  if (STATES) {
    const sy = STATES.meta.years;
    items.push(`The states, ${sy[0]} to ${sy[sy.length - 1]}`);
  }
  if (ABE) {
    const ay = abeYears();
    items.push(`Centre and states together, ${ay[0]} to ${ay[ay.length - 1]}`);
  }
  for (const t of items) {
    const sEl = document.createElement("span");
    sEl.textContent = t;
    byline.appendChild(sEl);
  }

  const lastAudited = [...m.years].reverse().find(
    (y) => valueAt(DATA.totals, y, "A") != null);
  const cov = $("coverage");
  cov.textContent = "";
  const ul = document.createElement("ul");
  const bits = [
    `The Union: budget estimates from ${u0} to ${uN}, audited spending to `
    + `${lastAudited}.`,
  ];
  if (STATES) {
    const sy = STATES.meta.years;
    bits.push(`The states: ${sy[0]} to ${sy[sy.length - 1]}, every state and `
      + `union territory with a legislature.`);
  }
  if (ABE) {
    const ay = abeYears();
    bits.push(`Centre and states together: ${ay[0]} to ${ay[ay.length - 1]}.`);
  }
  bits.push("Not covered: spending per pupil, which needs enrolment figures.");
  for (const b of bits) {
    const li = document.createElement("li");
    li.textContent = b;
    ul.appendChild(li);
  }
  cov.appendChild(ul);
}

// Every plot that can draw itself in, and whether it has been armed yet. A
// figure animates the first time it is scrolled to and never again, so a
// re-render from a control change redraws instantly instead of replaying.
// The scroll-driven graphics and the map animate themselves, so they are not
// in this list.
const PLOTS = [
  "abe-plot", "edu-plot", "whopays-plot", "stateshare-plot",
  "rank-plot", "util-plot", "class-plot",
];
const armed = new Set();

function armMotion() {
  for (const id of PLOTS) {
    if (armed.has(id)) continue;
    const host = $(id);
    if (!host) continue;
    armed.add(id);
    onFirstView(host, () => animateIn(host));
  }
}

function renderAll() {
  renderDefinitions();
  renderPromise();
  renderWhoPays();
  renderStateShare();
  renderUtilisation();
  renderClassification();
  renderScale();
  renderHeads();
  armMotion();
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

  segmented($("rank-measure"), [
    { value: "share", label: "% of own budget" },
    { value: "gsdp", label: "% of GSDP" },
  ], state.rankMeasure, (v) => { state.rankMeasure = v; wireControls(); renderRanking(); });

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

  $("map-play").addEventListener("click", togglePlay);
  $("map-range").addEventListener("input", (e) => {
    stopPlay();
    showYear(Number(e.target.value));
  });

  progressBar($("progress"));
  wireTheme();

  // Only re-render when the width actually changes. Mobile browsers fire
  // resize as the address bar shows and hides, which would otherwise rebuild
  // every chart mid-scroll.
  let timer;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(timer);
    timer = setTimeout(renderAll, 200);
  });

}

// Light unless the reader picks dark, and then remembered. Storage can throw
// in a private window; the toggle still works for the session, it just is not
// remembered.
function effectiveTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function labelTheme() {
  const btn = $("theme-toggle");
  if (btn) btn.textContent = effectiveTheme() === "dark" ? "Light" : "Dark";
}

function wireTheme() {
  const btn = $("theme-toggle");
  if (!btn) return;
  labelTheme();
  btn.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("budget-theme", next); } catch (e) { /* not remembered */ }
    labelTheme();
    // colours are read from the stylesheet at draw time, so redraw
    requestAnimationFrame(renderAll);
  });
}

Promise.all([
  load(),
  loadStates(),
  loadMap(),
  loadOptional("data/abe.json", ["national"]),
  loadOptional("data/schemes.json", ["schemes"]),
  loadOptional("data/union_actuals.json", ["years"]),
])
  .then(([data, states, map, abe, schemes, unionActuals]) => {
    DATA = data;
    STATES = states;
    MAP = map;
    ABE = abe;
    SCHEMES = schemes;
    UNION_ACTUALS = unionActuals;
    $("loading").remove();
    $("content").hidden = false;
    renderChrome();
    wireControls();
    wireOnce();
    renderAll();
    wireStories();
  })
  .catch((err) => {
    const el = $("loading");
    if (el) {
      el.textContent = `Could not load the data: ${err.message}. If you opened `
        + `this file directly, serve it over http instead: python -m http.server 8124`;
    }
    console.error(err);
  });

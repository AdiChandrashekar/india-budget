// Wiring. Reads data/union.json, renders the page, keeps the controls in sync.

import {
  load, pointsFor, valueAt, shareOfTotal, crore, lakhCrore, pct, csv, download,
} from "./data.js";
import { lineChart, groupedBars, stackedBars, legend } from "./charts.js";

const state = {
  measure: "cr",        // cr | share
  basis: "best",        // best | A | RE | BE
  wholeMeasure: "cr",   // cr | share
  headFilter: "edu",    // edu | all
  search: "",
  deptSort: { key: "latest", dir: -1 },
  headSort: { key: "latest", dir: -1 },
};

let DATA = null;
let COLOURS = {};

// Years with data, and the full span including years we could not parse. The
// charts use the span so a missing year leaves a hole; the tables use the
// years that exist so there are no empty columns.
function axisYears() {
  const all = [...DATA.meta.years, ...(DATA.meta.gap_years || [])];
  return all.sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
}

function readColours() {
  const s = getComputedStyle(document.documentElement);
  const get = (n, fallback) => (s.getPropertyValue(n) || fallback).trim();
  COLOURS = {
    edu: get("--edu", "#1f6f8b"),
    actual: get("--actual", "#16191d"),
    re: get("--re", "#b8762a"),
    be: get("--be", "#8a8f96"),
    warn: get("--warn", "#9c3b2e"),
    faint: get("--ink-faint", "#818a93"),
    soft: get("--edu-soft", "#cfe2e9"),
  };
}

// ---------------------------------------------------------------------------
// Small UI helpers
// ---------------------------------------------------------------------------

function segmented(host, options, current, onPick) {
  host.innerHTML = "";
  for (const opt of options) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = opt.label;
    b.title = opt.title || "";
    b.setAttribute("aria-pressed", String(opt.value === current));
    b.addEventListener("click", () => onPick(opt.value));
    host.appendChild(b);
  }
}

const EDU_SERIES = [
  { key: "moe", colourKey: "edu" },
  { key: "functional", colourKey: "re" },
  { key: "functional_narrow", colourKey: "be" },
];

function formatter() {
  return state.measure === "share"
    ? (v) => `${v.toFixed(1)}%`
    : (v) => (Math.abs(v) >= 100000 ? `${(v / 100000).toFixed(1)}L` : crore(v));
}

function seriesPoints(series, years) {
  if (state.measure === "share") {
    return years
      .map((year) => {
        const value = shareOfTotal(series, DATA.totals, year, state.basis);
        if (value == null) return null;
        const byType = series[year] || {};
        const used = state.basis === "best"
          ? ["A", "RE", "BE"].find((t) => byType[t] != null)
          : state.basis;
        return { year, value, basis: used };
      })
      .filter(Boolean);
  }
  return pointsFor(series, state.basis, years);
}

// ---------------------------------------------------------------------------
// Headline: education three ways
// ---------------------------------------------------------------------------

function renderHeadline() {
  const years = DATA.meta.years;
  const latest = years[years.length - 1];
  const stats = document.getElementById("headline-stats");

  stats.innerHTML = EDU_SERIES.map(({ key }) => {
    const block = DATA.education[key];
    const v = valueAt(block.series, latest, "BE");
    const share = shareOfTotal(block.series, DATA.totals, latest, "BE");
    return `<div class="stat">
      <dt>${block.label}</dt>
      <dd>${lakhCrore(v)}
        <span class="sub">${pct(share)} of Union spending &middot; ${latest} BE</span>
      </dd>
    </div>`;
  }).join("");

  const host = document.getElementById("edu-chart");
  const series = EDU_SERIES.map(({ key, colourKey }) => ({
    label: DATA.education[key].label,
    color: COLOURS[colourKey],
    points: seriesPoints(DATA.education[key].series, years),
  }));

  lineChart(host, { series, years: axisYears(), format: formatter() });

  legend(
    document.getElementById("edu-legend"),
    series
      .map((s) => ({ label: s.label, color: s.color }))
      .concat([{ label: "dashed = estimate, not an outturn", color: COLOURS.faint, dash: true }]),
  );

  document.getElementById("edu-caption").textContent =
    state.measure === "share"
      ? "Each definition as a share of total Union expenditure, read on the same basis as the total."
      : "Rupees crore, nominal. Not adjusted for inflation, so later years are flattered.";

  const gap = valueAt(DATA.education.moe.series, latest, "BE")
    - valueAt(DATA.education.functional.series, latest, "BE");
  document.getElementById("definitions-note").innerHTML = `
    <strong>Why they differ.</strong> ${EDU_SERIES.map(
      ({ key }) => `<em>${DATA.education[key].label}</em> &mdash; ${DATA.education[key].note}`,
    ).join("<br>")}
    <br><br>In ${latest} the ministry figure runs
    <strong>${lakhCrore(gap)}</strong> above the functional one, almost all of
    it money routed to states as grants-in-aid rather than booked by the Union
    under an education head.`;
}

// ---------------------------------------------------------------------------
// Budgeted against spent
// ---------------------------------------------------------------------------

function renderUtilisation() {
  const years = DATA.meta.years;
  const series = DATA.education.moe.series;
  const groups = [
    { key: "BE", label: "Budget Estimate", color: COLOURS.be, values: {} },
    { key: "RE", label: "Revised Estimate", color: COLOURS.re, values: {} },
    { key: "A", label: "Actuals", color: COLOURS.actual, values: {} },
  ];
  for (const year of years) {
    for (const g of groups) {
      const v = valueAt(series, year, g.key);
      if (v != null) g.values[year] = v;
    }
  }

  groupedBars(document.getElementById("util-chart"), {
    years: axisYears(),
    groups,
    format: (v) => (Math.abs(v) >= 100000 ? `${(v / 100000).toFixed(1)}L` : crore(v)),
  });

  legend(
    document.getElementById("util-legend"),
    groups.map((g) => ({ label: g.label, color: g.color })),
  );

  const settled = years
    .map((year) => {
      const be = valueAt(series, year, "BE");
      const a = valueAt(series, year, "A");
      return be && a ? { year, ratio: (100 * a) / be } : null;
    })
    .filter(Boolean);
  const spread = settled.length
    ? ` Where the actual is known, spending has run between
       ${Math.min(...settled.map((s) => s.ratio)).toFixed(0)}% and
       ${Math.max(...settled.map((s) => s.ratio)).toFixed(0)}% of the opening
       budget estimate.`
    : "";
  document.getElementById("util-caption").textContent =
    "Ministry of Education, Rs crore. A missing bar means that edition is not "
    + "yet parsed, not that the figure is zero." + spread.replace(/\s+/g, " ");

  const rows = years
    .map((year) => {
      const be = valueAt(series, year, "BE");
      const re = valueAt(series, year, "RE");
      const a = valueAt(series, year, "A");
      return { year, be, re, a, util: be && a ? (100 * a) / be : null };
    })
    .filter((r) => r.be != null || r.re != null || r.a != null);

  const table = document.getElementById("util-table");
  table.querySelector("thead").innerHTML =
    "<tr><th>Year</th><th>Budget Estimate</th><th>Revised</th>"
    + "<th>Actuals</th><th>Actuals as % of BE</th></tr>";
  table.querySelector("tbody").innerHTML = rows
    .map(
      (r) => `<tr><td>${r.year}</td>
        <td class="num">${crore(r.be)}</td>
        <td class="num">${crore(r.re)}</td>
        <td class="num">${crore(r.a)}</td>
        <td class="num">${r.util == null ? "—" : pct(r.util, 1)}</td></tr>`,
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Classification: where the ministry's money is booked
// ---------------------------------------------------------------------------

function renderClassification() {
  const years = DATA.meta.years;
  const latest = years[years.length - 1];
  const heads = DATA.moe_heads
    .filter((h) => Object.keys(h.series).length)
    .slice(0, 7);

  const palette = [COLOURS.warn, COLOURS.edu, COLOURS.re, COLOURS.be,
    COLOURS.soft, COLOURS.faint, COLOURS.actual];

  const layers = heads.map((h, i) => {
    const values = {};
    for (const year of years) {
      const v = valueAt(h.series, year, state.basis);
      if (v != null && v > 0) values[year] = v;
    }
    return {
      key: h.code,
      label: `${h.code} ${h.name}${h.education ? " (education head)" : ""}`,
      color: palette[i % palette.length],
      values,
    };
  });

  stackedBars(document.getElementById("class-chart"), {
    years: axisYears(),
    layers,
    format: (v) => (Math.abs(v) >= 100000 ? `${(v / 100000).toFixed(1)}L` : crore(v)),
  });

  legend(
    document.getElementById("class-legend"),
    layers.map((l) => ({ label: l.label, color: l.color })),
  );

  document.getElementById("class-caption").textContent =
    "Ministry of Education gross provision by major head, Rs crore. Gross, "
    + "because recoveries are netted against the heads they came from.";

  const grants = DATA.moe_heads.find((h) => h.code === "3601");
  const general = DATA.moe_heads.find((h) => h.code === "2202");
  const g = grants ? valueAt(grants.series, latest, "BE") : null;
  const e = general ? valueAt(general.series, latest, "BE") : null;
  document.getElementById("double-count-note").innerHTML = `
    <strong>Read this before comparing governments.</strong> In ${latest},
    ${g != null ? `<strong>${lakhCrore(g)}</strong>` : "the largest share"}
    of the ministry's provision sits under head 3601, grants-in-aid to state
    governments, against
    ${e != null ? `<strong>${lakhCrore(e)}</strong>` : "a smaller sum"} under
    2202, general education. Those grants are spent, and booked as education,
    by the states. The Union's own functional education figure therefore
    understates what the centre funds, and summing Union and state education
    budgets overstates it.`;
}

// ---------------------------------------------------------------------------
// The whole budget, by department
// ---------------------------------------------------------------------------

function deptValue(d, year) {
  return state.wholeMeasure === "share"
    ? shareOfTotal(d.series, DATA.totals, year, state.basis)
    : valueAt(d.series, year, state.basis);
}

function renderDepartments() {
  const years = DATA.meta.years;
  const latest = years[years.length - 1];
  const needle = state.search.trim().toLowerCase();

  let rows = DATA.demands.map((d) => ({
    d,
    latest: deptValue(d, latest),
    values: years.map((y) => deptValue(d, y)),
  }));
  if (needle) {
    rows = rows.filter(
      (r) => r.d.name.toLowerCase().includes(needle)
        || (r.d.ministry || "").toLowerCase().includes(needle),
    );
  }

  const { key, dir } = state.deptSort;
  rows.sort((a, b) => {
    if (key === "name") return dir * a.d.name.localeCompare(b.d.name);
    const ai = key === "latest" ? a.latest : a.values[years.indexOf(key)];
    const bi = key === "latest" ? b.latest : b.values[years.indexOf(key)];
    return dir * ((ai ?? -Infinity) - (bi ?? -Infinity));
  });

  const fmt = state.wholeMeasure === "share" ? (v) => pct(v, 2) : (v) => crore(v);
  const table = document.getElementById("dept-table");
  table.querySelector("thead").innerHTML = `<tr>
    <th data-sort="name">Department</th>
    ${years.map((y) => `<th data-sort="${y}">${y}</th>`).join("")}
  </tr>`;

  table.querySelector("tbody").innerHTML = rows
    .map((r) => {
      const isEdu = /school education|higher education/i.test(r.d.name);
      return `<tr class="${isEdu ? "is-edu" : ""}">
        <td>${r.d.name}${isEdu ? '<span class="tag">education</span>' : ""}</td>
        ${r.values.map((v) => `<td class="num">${v == null ? "—" : fmt(v)}</td>`).join("")}
      </tr>`;
    })
    .join("")
    + (needle
      ? ""
      : `<tr class="total"><td>Total Union expenditure</td>${years
        .map((y) => {
          const v = state.wholeMeasure === "share"
            ? 100
            : valueAt(DATA.totals, y, state.basis);
          return `<td class="num">${v == null ? "—" : fmt(v)}</td>`;
        })
        .join("")}</tr>`);

  for (const th of table.querySelectorAll("th")) {
    const k = th.dataset.sort;
    if (k === state.deptSort.key) {
      th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    }
    th.addEventListener("click", () => {
      state.deptSort = {
        key: k,
        dir: state.deptSort.key === k ? -state.deptSort.dir : (k === "name" ? 1 : -1),
      };
      renderDepartments();
    });
  }

  document.getElementById("dept-caption").textContent =
    `${rows.length} of ${DATA.demands.length} departments shown. `
    + (state.wholeMeasure === "share"
      ? "Share of total Union expenditure, per cent."
      : "Rs crore, net of receipts netted against the demand.");
}

// ---------------------------------------------------------------------------
// Functional heads
// ---------------------------------------------------------------------------

function renderHeads() {
  const years = DATA.meta.years;
  const latest = years[years.length - 1];
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

  const table = document.getElementById("head-table");
  table.querySelector("thead").innerHTML = `<tr>
    <th data-sort="name">Major head</th>
    ${years.map((y) => `<th data-sort="${y}">${y}</th>`).join("")}
  </tr>`;
  table.querySelector("tbody").innerHTML = rows
    .map(
      (r) => `<tr class="${r.h.education ? "is-edu" : ""}">
      <td>${r.h.code} &middot; ${r.h.name}${
        r.h.education ? '<span class="tag">education</span>' : ""
      }</td>
      ${r.values.map((v) => `<td class="num">${v == null ? "—" : crore(v)}</td>`).join("")}
    </tr>`,
    )
    .join("");

  for (const th of table.querySelectorAll("th")) {
    const k = th.dataset.sort;
    if (k === state.headSort.key) {
      th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    }
    th.addEventListener("click", () => {
      state.headSort = {
        key: k,
        dir: state.headSort.key === k ? -state.headSort.dir : (k === "name" ? 1 : -1),
      };
      renderHeads();
    });
  }

  document.getElementById("head-caption").textContent =
    `${rows.length} major heads, gross provision in Rs crore. `
    + "Summed across every demand that books to the head.";
}

// ---------------------------------------------------------------------------
// Chrome
// ---------------------------------------------------------------------------

function renderChrome() {
  const m = DATA.meta;
  document.getElementById("srcline").innerHTML = [
    `${m.years[0]} – ${m.years[m.years.length - 1]}`,
    `${m.editions.length} budget editions`,
    `${m.rows_in_long_table.toLocaleString("en-IN")} published figures`,
    `built ${m.generated}`,
  ].map((t) => `<span>${t}</span>`).join("");

  const gap = m.gap_years || [];
  document.getElementById("coverage").innerHTML = `
    <h3>Coverage</h3>
    <ul>
      <li>Editions parsed: ${m.editions.join(", ")}. Each one publishes four
        years &mdash; actuals for two years back, a revised and a budget
        estimate for last year, and a budget estimate for the year ahead
        &mdash; so a handful of editions covers a decade.</li>
      ${gap.length
    ? `<li><strong>Gap: ${gap.join(", ")}.</strong> The editions covering
        these years ship PDF only, with no Excel. Reading them needs a PDF
        table parser, which is the next piece of work, not a missing
        source.</li>`
    : ""}
      <li>Education departments seen across editions:
        ${m.moe_departments.join("; ")}.</li>
    </ul>`;
}

function renderAll() {
  readColours();
  renderHeadline();
  renderUtilisation();
  renderClassification();
  renderDepartments();
  renderHeads();
}

function wireControls() {
  segmented(
    document.getElementById("measure-toggle"),
    [
      { value: "cr", label: "Rs crore" },
      { value: "share", label: "% of Union spending" },
    ],
    state.measure,
    (v) => { state.measure = v; wireControls(); renderHeadline(); },
  );

  const bases = [
    { value: "best", label: "Best available", title: "Actuals, else revised, else budget estimate" },
    { value: "A", label: "Actuals" },
    { value: "RE", label: "Revised" },
    { value: "BE", label: "Budget" },
  ];
  segmented(document.getElementById("basis-toggle"), bases, state.basis, (v) => {
    state.basis = v;
    wireControls();
    renderHeadline();
    renderClassification();
    renderDepartments();
    renderHeads();
  });

  segmented(
    document.getElementById("whole-measure"),
    [
      { value: "cr", label: "Rs crore" },
      { value: "share", label: "% of total" },
    ],
    state.wholeMeasure,
    (v) => { state.wholeMeasure = v; wireControls(); renderDepartments(); },
  );

  segmented(
    document.getElementById("head-filter"),
    [
      { value: "edu", label: "Education only" },
      { value: "all", label: "All heads" },
    ],
    state.headFilter,
    (v) => { state.headFilter = v; wireControls(); renderHeads(); },
  );
}

function wireOnce() {
  const search = document.getElementById("dept-search");
  search.addEventListener("input", () => {
    state.search = search.value;
    renderDepartments();
  });

  document.getElementById("export-depts").addEventListener("click", () => {
    const years = DATA.meta.years;
    const rows = [["department", "ministry", ...years]];
    for (const d of DATA.demands) {
      rows.push([d.name, d.ministry, ...years.map((y) => deptValue(d, y) ?? "")]);
    }
    download(`union-departments-${state.basis}.csv`, csv(rows));
  });

  document.getElementById("export-heads").addEventListener("click", () => {
    const years = DATA.meta.years;
    const rows = [["major_head", "name", "is_education", ...years]];
    for (const h of DATA.heads) {
      rows.push([h.code, h.name, h.education, ...years.map((y) => valueAt(h.series, y, state.basis) ?? "")]);
    }
    download(`union-major-heads-${state.basis}.csv`, csv(rows));
  });

  let timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(renderAll, 180);
  });

  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  scheme.addEventListener("change", renderAll);
}

load()
  .then((data) => {
    DATA = data;
    document.getElementById("loading").remove();
    document.getElementById("content").hidden = false;
    readColours();
    renderChrome();
    wireControls();
    wireOnce();
    renderAll();
  })
  .catch((err) => {
    const el = document.getElementById("loading");
    if (el) {
      el.textContent = `Could not load the data: ${err.message}. `
        + "If you opened this file directly, serve it over http instead: "
        + "python -m http.server 8123";
    }
    console.error(err);
  });

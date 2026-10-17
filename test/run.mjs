// node test/run.mjs
//
// No framework, no dependencies. Checks the helpers in js/data.js and the
// shape and arithmetic of the published data/union.json, so a broken pipeline
// cannot ship a page that renders but lies.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  pointsFor, valueAt, shareOfTotal, crore, lakhCrore, pct, csv, fyStart,
} from "../js/data.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const data = JSON.parse(readFileSync(join(ROOT, "data", "union.json"), "utf8"));

let passed = 0;
const failures = [];

function ok(label, cond, detail = "") {
  if (cond) passed += 1;
  else failures.push(`${label}${detail ? ` — ${detail}` : ""}`);
}

function near(label, got, want, tol = 1) {
  ok(label, got != null && Math.abs(got - want) <= tol,
    `got ${got}, expected ${want} ± ${tol}`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const series = {
  "2023-24": { BE: 100, RE: 110, A: 105 },
  "2024-25": { BE: 200, RE: 190 },
  "2025-26": { BE: 300 },
};
const years = ["2023-24", "2024-25", "2025-26"];

ok("fyStart reads the opening year", fyStart("2026-27") === 2026);

const best = pointsFor(series, "best", years);
ok("best available prefers actuals", best[0].value === 105 && best[0].basis === "A");
ok("best available falls back to revised", best[1].value === 190 && best[1].basis === "RE");
ok("best available falls back to budget", best[2].value === 300 && best[2].basis === "BE");

const beOnly = pointsFor(series, "BE", years);
ok("an explicit basis never substitutes another", beOnly.every((p) => p.basis === "BE"));
ok("an explicit basis returns every year that has it", beOnly.length === 3);

ok("valueAt returns null for a year with no data", valueAt(series, "1999-00", "BE") === null);
ok("valueAt returns null for a missing basis", valueAt(series, "2025-26", "A") === null);

const totals = { "2023-24": { BE: 1000, A: 2100 } };
near("share is computed basis against like basis",
  shareOfTotal(series, totals, "2023-24", "BE"), 10, 0.001);
near("share on best available uses actuals both sides",
  shareOfTotal(series, totals, "2023-24", "best"), 5, 0.001);
ok("share is null when the denominator is missing",
  shareOfTotal(series, totals, "2024-25", "BE") === null);

ok("crore formats in the Indian grouping", crore(1234567) === "12,34,567");
ok("lakh crore switches unit above a lakh", lakhCrore(139289).includes("lakh cr"));
ok("lakh crore stays in crore below it", lakhCrore(83562) === "83,562 cr");
ok("missing values render as a dash", crore(null) === "—" && pct(null) === "—");
ok("csv quotes a field containing a comma",
  csv([["Ministry of Micro, Small", 1]]) === '"Ministry of Micro, Small",1');

// ---------------------------------------------------------------------------
// Shape of the published data
// ---------------------------------------------------------------------------

for (const key of ["meta", "totals", "education", "demands", "heads", "moe_heads"]) {
  ok(`union.json has ${key}`, data[key] != null);
}

const { years: dataYears } = data.meta;
ok("years are sorted", dataYears.every((y, i) => i === 0 || fyStart(y) > fyStart(dataYears[i - 1])));
ok("every year is well formed", dataYears.every((y) => /^\d{4}-\d{2}$/.test(y)));

const latest = dataYears[dataYears.length - 1];
ok("the latest year has a budget estimate", valueAt(data.totals, latest, "BE") != null);

// ---------------------------------------------------------------------------
// Figures the government published. These are the ones that matter.
// ---------------------------------------------------------------------------

near("total Union expenditure 2026-27 BE",
  valueAt(data.totals, "2026-27", "BE"), 5347315, 1);
near("Ministry of Education 2026-27 BE",
  valueAt(data.education.moe.series, "2026-27", "BE"), 139289.48, 0.01);

const school = data.demands.find((d) => d.key.includes("school education"));
const higher = data.demands.find((d) => d.key.includes("higher education"));
ok("both education departments are present", school != null && higher != null);
near("School Education & Literacy 2026-27 BE",
  valueAt(school.series, "2026-27", "BE"), 83562.26, 0.01);
near("Higher Education 2026-27 BE",
  valueAt(higher.series, "2026-27", "BE"), 55727.22, 0.01);
near("the two departments sum to the ministry",
  valueAt(school.series, "2026-27", "BE") + valueAt(higher.series, "2026-27", "BE"),
  valueAt(data.education.moe.series, "2026-27", "BE"), 0.01);

// The renumbering this pipeline exists to survive.
ok("School Education spans the 57 -> 25 renumbering",
  school.demand_numbers["2019-20"] === "57" && school.demand_numbers["2026-27"] === "25",
  JSON.stringify(school.demand_numbers));

// ---------------------------------------------------------------------------
// Relationships that must hold
// ---------------------------------------------------------------------------

ok("the narrow education definition never exceeds the wide one",
  dataYears.every((y) => {
    const wide = valueAt(data.education.functional.series, y, "BE");
    const narrow = valueAt(data.education.functional_narrow.series, y, "BE");
    return wide == null || narrow == null || narrow <= wide + 0.01;
  }));

ok("no department exceeds total Union expenditure",
  data.demands.every((d) => dataYears.every((y) => {
    const v = valueAt(d.series, y, "BE");
    const t = valueAt(data.totals, y, "BE");
    return v == null || t == null || v <= t;
  })));

ok("every department has a name",
  data.demands.every((d) => d.name && d.name.replace(/[^A-Za-z]/g, "").length >= 3),
  data.demands.filter((d) => !d.name || d.name.replace(/[^A-Za-z]/g, "").length < 3)
    .map((d) => d.name).join(", "));

ok("education heads are flagged",
  ["2202", "2203", "4202"].every((code) => {
    const h = data.heads.find((x) => x.code === code);
    return h && h.education === true;
  }));

ok("grants-in-aid is the ministry's largest head, which is the whole point",
  data.moe_heads[0].code === "3601", data.moe_heads[0].code);

ok("gap years are not also data years",
  (data.meta.gap_years || []).every((y) => !dataYears.includes(y)));

// ---------------------------------------------------------------------------
// data/states.json — the state layer
// ---------------------------------------------------------------------------

const states = JSON.parse(readFileSync(join(ROOT, "data", "states.json"), "utf8"));

ok("states.json has its top-level blocks",
  !!(states.meta && states.states && states.series));

const sYears = states.meta.years;
ok("state years run 1990-91 to 2025-26",
  sYears[0] === "1990-91" && sYears[sYears.length - 1] === "2025-26",
  `${sYears[0]}..${sYears[sYears.length - 1]}`);
ok("state years have no gaps", sYears.every(
  (y, i) => i === 0 || fyStart(y) === fyStart(sYears[i - 1]) + 1));
ok("31 states and UTs plus the all-states aggregate",
  states.states.length === 32, String(states.states.length));
ok("the all-states aggregate is present", !!states.series.ALL);

// The share definition, read off data/states.json exactly as the page reads
// it, against the percentages RBI prints in Statement 26.
function stateShare(code, year, etype) {
  const s = states.series[code];
  const spend = s?.education_spend?.[year]?.[etype];
  const agg = s?.aggregate_expenditure?.[year]?.[etype];
  if (spend == null || agg == null || agg === 0) return null;
  return (100 * spend) / agg;
}

near("all states, education share 2010-11 actuals (RBI Statement 26: 16.6%)",
  stateShare("ALL", "2010-11", "A"), 16.6, 0.051);
near("all states, education share 2025-26 BE (RBI Statement 26: 13.1%)",
  stateShare("ALL", "2025-26", "BE"), 13.1, 0.051);
near("Bihar, education share 2025-26 BE (RBI Statement 26: 20.0%)",
  stateShare("BR", "2025-26", "BE"), 20.0, 0.051);
near("Telangana, education share 2025-26 BE (RBI Statement 26: 7.8%)",
  stateShare("TG", "2025-26", "BE"), 7.8, 0.051);

// Published absolute amounts, from Appendix Table 7.
near("all states, revenue expenditure on education 2020-21 (Appendix 7)",
  states.series.ALL.education_revenue["2020-21"].A, 512428.9, 1);

// The two derived series must be exactly their parts, on the same basis.
ok("education spend is revenue expenditure plus capital outlay", (() => {
  const s = states.series.ALL;
  return sYears.every((y) => ["A", "RE", "BE"].every((t) => {
    const got = s.education_spend?.[y]?.[t];
    if (got == null) return true;
    const parts = (s.education_revenue?.[y]?.[t] ?? 0)
      + (s.education_capital?.[y]?.[t] ?? 0);
    return Math.abs(got - parts) <= 0.02;
  }));
})());

// A missing part silently drops a whole cell, so assert nothing was dropped.
// A future edition that stops publishing one of the four lines should fail
// here rather than quietly shortening every series.
ok("no state-year was dropped for want of a component", (() => {
  for (const [, s] of Object.entries(states.series)) {
    for (const [y, byType] of Object.entries(s.education_revenue ?? {})) {
      for (const t of Object.keys(byType)) {
        if (s.education_spend?.[y]?.[t] == null) return false;
        if (s.aggregate_expenditure?.[y]?.[t] == null) return false;
      }
    }
  }
  return true;
})());

// Containment: education is one item inside social services, which is inside
// total revenue expenditure.
ok("education revenue <= social services <= total revenue expenditure", (() => {
  for (const [, s] of Object.entries(states.series)) {
    for (const [y, byType] of Object.entries(s.education_revenue ?? {})) {
      for (const [t, v] of Object.entries(byType)) {
        const social = s.social_services?.[y]?.[t];
        const total = s.total_revenue?.[y]?.[t];
        if (social != null && v > social + 1) return false;
        if (social != null && total != null && social > total + 1) return false;
      }
    }
  }
  return true;
})());

ok("education spending never exceeds aggregate expenditure", (() => {
  for (const [, s] of Object.entries(states.series)) {
    for (const [y, byType] of Object.entries(s.education_spend ?? {})) {
      for (const [t, v] of Object.entries(byType)) {
        const agg = s.aggregate_expenditure?.[y]?.[t];
        if (agg != null && v > agg + 1) return false;
      }
    }
  }
  return true;
})());

// The reorganisations. e-STATES pads a state's pre-formation years with zeros,
// so the real test is that nothing was published for a state before it
// existed — a chart drawing Telangana back to 1990 would look entirely
// plausible and be entirely wrong.
const formation = {
  CT: "2000-01", UT: "2000-01", JH: "2001-02",
  TG: "2014-15", DL: "1993-94", PY: "2005-06",
};
for (const [code, first] of Object.entries(formation)) {
  const meta = states.states.find((s) => s.code === code);
  ok(`${code} series starts at ${first}`,
    meta?.first_year === first, `got ${meta?.first_year}`);
  const before = Object.keys(states.series[code]?.education_spend ?? {})
    .filter((y) => fyStart(y) < fyStart(first));
  ok(`${code} has nothing before ${first}`,
    before.length === 0, before.join(", "));
}

// Parent and successor are kept apart, never merged.
ok("Andhra Pradesh and Telangana are separate series",
  !!states.series.AP && !!states.series.TG
  && states.series.AP.education_spend["2013-14"] != null
  && states.series.TG.education_spend?.["2013-14"] == null);
ok("a split state names its parent",
  states.states.find((s) => s.code === "TG")?.parent === "AP");
ok("a parent state names its successor",
  (states.states.find((s) => s.code === "AP")?.successors ?? []).includes("TG"));

// GSDP is a shorter series than the budgets, so no ratio may be implied
// outside the window the Handbook actually publishes.
const gy = states.meta.gsdp?.years ?? [];
ok("GSDP starts in 2011-12", gy[0] === "2011-12", gy[0]);
ok("no GSDP figure outside the published window", (() => {
  const lo = fyStart(gy[0]);
  const hi = fyStart(gy[gy.length - 1]);
  for (const [, s] of Object.entries(states.series)) {
    for (const y of Object.keys(s.gsdp ?? {})) {
      if (fyStart(y) < lo || fyStart(y) > hi) return false;
    }
  }
  return true;
})());
ok("the all-states aggregate has no GSDP, because there is no all-India row",
  states.series.ALL.gsdp == null);

// The warning has to be in the data, not only in the prose, so that any
// consumer of states.json meets it.
ok("states.json carries the double-counting warning",
  /never be added/i.test(states.meta.never_add || "")
  && /3601/.test(states.meta.never_add || ""));
ok("the share definition is recorded with the data",
  /Statement 26/.test(states.meta.share_definition || ""));
ok("no combined centre-plus-state total is published anywhere",
  !JSON.stringify(states).includes("combined_total"));

// The Union figure is carried for contrast and is labelled as the same
// functional definition, which is the only way the comparison is honest.
ok("the Union functional series is carried for comparison",
  !!states.union_functional?.series
  && Object.keys(states.union_functional.series).length > 0);

// ---------------------------------------------------------------------------

console.log(`${passed} passed, ${failures.length} failed`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  process.exit(1);
}

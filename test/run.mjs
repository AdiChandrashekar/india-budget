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

// The renumbering this pipeline exists to survive. Across the editions parsed
// so far the School Education demand has been numbered 55, 56, 57, 58, 59, 24
// and 25 — it wanders year to year and then jumps when the list is
// re-alphabetised. Keying a series on the number would splice unrelated
// ministries together, so the test is that one department holds one series
// through all of it, not that any particular year carries any particular
// number. Two anchors keep it honest about which end is which.
const schoolNumbers = Object.values(school.demand_numbers);
ok("School Education survives repeated renumbering",
  new Set(schoolNumbers).size >= 4
  && school.demand_numbers["2018-19"] === "58"
  && school.demand_numbers["2026-27"] === "25",
  JSON.stringify(school.demand_numbers));

ok("every year of the series carries a demand number",
  dataYears.every((y) => typeof school.demand_numbers[y] === "string"),
  dataYears.filter((y) => !school.demand_numbers[y]).join(", "));

// Actuals stop where the Plan-era documents do: editions up to 2016-17 print
// Plan, Non-Plan and Total for three years and no actuals column at all. The
// charts must not imply an outturn exists for those years.
const actualYears = dataYears.filter((y) => valueAt(data.totals, y, "A") != null);
// The newest edition reports actuals for t-2, so the run ends two years
// short of the latest budget estimate. What matters is that it has no holes.
ok("actuals form one unbroken run at the recent end",
  actualYears.length > 0
  && fyStart(dataYears[dataYears.length - 1])
    - fyStart(actualYears[actualYears.length - 1]) <= 2
  && actualYears.every((y, i) => i === 0
    || fyStart(y) === fyStart(actualYears[i - 1]) + 1),
  actualYears.join(", "));

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
// The gap data: GDP, schemes, pre-2015-16 actuals, GSDP back-series, ABE.
// Each file is checked for the arithmetic a page would rely on, so that a
// consumer cannot divide by a chained GDP or add a family to its members.
// ---------------------------------------------------------------------------

const load = (name) => JSON.parse(readFileSync(join(ROOT, "data", name), "utf8"));

const gdp = load("gdp.json");
ok("gdp.json records both rebasings as breaks",
  JSON.stringify(gdp.meta.breaks) === JSON.stringify(["2011-12", "2022-23"]));
ok("gdp.json keeps three bases as separate segments",
  gdp.segments.map((s) => s.base).join() === "2004-05,2011-12,2022-23");
ok("every preferred GDP value is a printed value on its own base",
  Object.entries(gdp.preferred).every(([fy, p]) => gdp.series[p.base][fy] === p.value));
ok("the overlap years carry both bases, so a break can be measured",
  gdp.series["2004-05"]["2011-12"] > 0 && gdp.series["2011-12"]["2011-12"] > 0
  && gdp.series["2011-12"]["2022-23"] > 0 && gdp.series["2022-23"]["2022-23"] > 0);
ok("the preferred series covers 1990-91 to 2025-26 without a hole",
  Array.from({ length: 36 }, (_, i) => `${1990 + i}-${String((91 + i) % 100).padStart(2, "0")}`)
    .every((fy) => gdp.preferred[fy] != null));
ok("no rescaled or chained GDP is published",
  !JSON.stringify(gdp).match(/chained|spliced|linked_series/));
near("Union total expenditure 2008-09 is 15.8% of 2004-05-base GDP",
  100 * 883956 / gdp.series["2004-05"]["2008-09"], 15.8, 0.1);

const schemes = load("schemes.json");
const byId = Object.fromEntries(schemes.schemes.map((s) => [s.id, s]));
ok("a scheme's total is the sum of its members, every year and basis",
  schemes.schemes.every((s) => Object.entries(s.total).every(([fy, d]) =>
    Object.entries(d).every(([et, v]) => {
      const sum = Object.values(s.by_member)
        .reduce((a, m) => a + (m[fy]?.[et] ?? 0), 0);
      return Math.abs(sum - v) < 0.02;
    }))));
ok("Samagra Shiksha's lineage names its three predecessors",
  ["ssa", "rmsa", "teacher_education", "samagra_shiksha"]
    .every((m) => byId.samagra_shiksha.members.some((x) => x.id === m)));
near("Samagra Shiksha BE 2026-27", byId.samagra_shiksha.total["2026-27"].BE, 42100.02, 0.01);
near("Sarva Shiksha Abhiyan BE 2010-11",
  byId.samagra_shiksha.by_member.ssa["2010-11"].BE, 15000, 0.01);
ok("every scheme year says which edition it came from",
  schemes.schemes.every((s) => s.years.every((fy) => s.source[fy] != null)));
ok("the SBE carries actuals from 2009-10 and not before",
  byId.pm_poshan.total["2009-10"].A > 0 && byId.pm_poshan.total["2008-09"].A == null);

const ua = load("union_actuals.json");
const uaYears = Object.keys(ua.years);
ok("Union actuals run 1997-98 to 2014-15, where the demands take over",
  uaYears[0] === "1997-98" && uaYears[uaYears.length - 1] === "2014-15"
  && uaYears.length === 18);
ok("total expenditure = central sector + State Plans + UTs, every year",
  uaYears.every((y) => {
    const v = ua.years[y];
    return Math.abs(v.central_sector + v.state_plans + v.union_territories
      - v.total_expenditure) < 1;
  }));
ok("a department's total is its central-sector and State Plans lines",
  uaYears.every((y) => ua.years[y].departments.every((d) =>
    Math.abs((d.central_sector ?? 0) + (d.state_plans ?? 0) - d.total) < 0.01)));
ok("departments add up to the central sector, except the one recorded misprint",
  uaYears.every((y) => {
    const v = ua.years[y];
    const s = v.departments.reduce((a, d) => a + (d.central_sector ?? 0), 0);
    return Math.abs(s - v.central_sector) < 1 || v.known_gaps.length > 0;
  }));
ok("the 1998-99 edition is excluded with its reason, not silently",
  /truncated/.test(ua.excluded_editions["1998-99"] || ""));
const unionLast = data.meta.years.find((y) => valueAt(data.totals, y, "A") != null);
ok("the pre-2015-16 actuals meet union.json's own first actual year",
  unionLast === "2015-16" || unionLast == null,
  `union.json's first actual is ${unionLast}`);

const gsdp = load("gsdp.json");
ok("gsdp.json has five base segments, none chained",
  gsdp.segments.length === 5 && !JSON.stringify(gsdp).match(/chained|spliced/));
ok("the factor-cost to market-price change is recorded with the 2011-12 base",
  /factor cost/.test(gsdp.segments[3].measure) && /market/.test(gsdp.segments[4].measure));
ok("a parent's budget-boundary GSDP is never smaller than its printed GSDP",
  Object.entries(gsdp.budget_boundary).every(([code, bases]) =>
    Object.entries(bases).every(([b, ys]) => Object.entries(ys).every(([fy, v]) =>
      v + 0.01 >= gsdp.series[code][b][fy]))));
ok("undivided Andhra Pradesh 2011-12 includes Telangana",
  Math.abs(gsdp.budget_boundary.AP["2011-12"]["2011-12"]
    - gsdp.series.AP["2011-12"]["2011-12"] - gsdp.series.TG["2011-12"]["2011-12"]) < 0.01);
ok("GSDP reaches back to 1990-91 for the large states",
  ["UP", "MH", "WB", "TN"].every((s) => gsdp.series[s]["1980-81"]["1990-91"] > 0));

const abe = load("abe.json");
const nat = abe.national;
ok("the ABE national series runs 2000-01 to 2021-22",
  nat["2000-01"] != null && nat["2021-22"] != null && Object.keys(nat).length === 22);
ok("ABE: Centre + States = total, both definitions, every year",
  Object.values(nat).every((y) => ["education_departments",
    "education_and_other_departments"].every((k) =>
    Math.abs(y[k].states + y[k].centre - y[k].total) <= 2)));
ok("ABE: each % of GDP is the total over the GDP it prints",
  Object.values(nat).every((y) => Math.abs(100 * y.education_and_other_departments.total
    / y.gdp - y.education_and_other_departments.pct_gdp.total) < 0.011));
near("ABE: education by all departments, 2019-20, % of GDP",
  nat["2019-20"].education_and_other_departments.pct_gdp.total, 4.04, 0.001);
ok("ABE state rows carry the five main sub-sectors",
  ["elementary", "secondary", "adult", "university", "technical"]
    .every((s) => abe.states.AP?.[s] != null));
ok("ABE's combined total says it is the only one, and why",
  /never add/i.test(abe.meta.national_rule || ""));

// ---------------------------------------------------------------------------

console.log(`${passed} passed, ${failures.length} failed`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  process.exit(1);
}

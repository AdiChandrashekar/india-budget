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

console.log(`${passed} passed, ${failures.length} failed`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  process.exit(1);
}

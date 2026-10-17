// Loading and reshaping data/union.json. No rendering here.

export const PREFERENCE = ["A", "RE", "BE"];   // what "best available" means

async function loadJson(path, required) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status} ${res.statusText}`);
  const d = await res.json();
  for (const key of required) {
    if (!d[key]) throw new Error(`${path} is missing its ${key} block`);
  }
  return d;
}

export function load() {
  return loadJson("data/union.json", ["meta", "totals", "education"]);
}

// The state layer is a separate file and a separate pipeline. The page works
// without it — the Union sections render on their own — so a failure here is
// reported in place rather than taking the whole page down.
export async function loadStates() {
  try {
    return await loadJson("data/states.json", ["meta", "states", "series"]);
  } catch (err) {
    console.error(err);
    return null;
  }
}

// Boundaries are decoded to plain GeoJSON at build time, so the page needs no
// TopoJSON library. Absence is survivable: the ranked bars say the same thing.
export async function loadMap() {
  try {
    const res = await fetch("data/india-states.geo.json");
    if (!res.ok) throw new Error(res.status + " " + res.statusText);
    const d = await res.json();
    return d.features && d.features.length ? d : null;
  } catch (err) {
    console.error(err);
    return null;
  }
}

// A series is {year: {A|RE|BE: amount}}. Pick one number per year.
//
// "best" prefers audited actuals, then the revised estimate, then the budget
// estimate, which is how a reader should read a budget series: the further
// back you look the more settled the number is. It returns the basis it used
// so the chart can draw an estimate differently from an outturn.
export function pointsFor(series, basis, years) {
  const out = [];
  for (const year of years) {
    const byType = series?.[year];
    if (!byType) continue;
    if (basis === "best") {
      const used = PREFERENCE.find((t) => byType[t] != null);
      if (used) out.push({ year, value: byType[used], basis: used });
    } else if (byType[basis] != null) {
      out.push({ year, value: byType[basis], basis });
    }
  }
  return out;
}

export function valueAt(series, year, basis) {
  const byType = series?.[year];
  if (!byType) return null;
  if (basis === "best") {
    const used = PREFERENCE.find((t) => byType[t] != null);
    return used ? byType[used] : null;
  }
  return byType[basis] ?? null;
}

// Share of total Union expenditure, in per cent. Both numbers are read on the
// same basis, so a BE share is BE over BE and never mixes an outturn with a
// forecast.
export function shareOfTotal(series, totals, year, basis) {
  const part = valueAt(series, year, basis);
  const whole = valueAt(totals, year, basis);
  if (part == null || whole == null || whole === 0) return null;
  return (100 * part) / whole;
}

export function fyStart(year) {
  return parseInt(year.slice(0, 4), 10);
}

// ---------------------------------------------------------------------------
// Formatting. Indian budget documents are written in crore and read in lakh
// crore, so the tool does the same rather than converting to millions.
// ---------------------------------------------------------------------------

const GROUPED = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function crore(v, { decimals = 0 } = {}) {
  if (v == null) return "—";
  if (decimals > 0) {
    return new Intl.NumberFormat("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(v);
  }
  return GROUPED.format(Math.round(v));
}

export function lakhCrore(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 100000) return `${(v / 100000).toFixed(2)} lakh cr`;
  return `${GROUPED.format(Math.round(v))} cr`;
}

export function pct(v, decimals = 2) {
  return v == null ? "—" : `${v.toFixed(decimals)}%`;
}

export function csv(rows) {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          const s = cell == null ? "" : String(cell);
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        })
        .join(","),
    )
    .join("\n");
}

export function download(name, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

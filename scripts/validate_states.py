"""State-layer checks, called by scripts/validate.py.

Kept in its own module so the Union checks and these can be worked on
independently.

Three kinds of check, in increasing strength:

*   **Fixtures** -- figures printed in RBI's own statements, quoted here as
    literals with the statement they come from, so a failure can be argued
    with offline.
*   **The whole of Statement 26** -- all 570 percentages RBI publishes for
    education as a share of aggregate expenditure, 31 states and the
    all-states aggregate, 2008-09 to 2025-26, recomputed from the long table
    and compared cell by cell. This is the real test: it pins the numerator,
    the denominator and the estimate type simultaneously, for every state and
    every year, against what the central bank printed.
*   **Identities** -- relationships that must hold whether or not a published
    figure covers the year, which catch a parser that drops or double counts.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

TOLERANCE = 1.0          # Rs crore
PCT_TOLERANCE = 0.051    # percentage points; RBI prints one decimal

EDU_REVENUE = "Education, Sports, Art and Culture"
EDU_CAPITAL = "Capital Outlay on Education, Sports, Art and Culture"
EDU_LOANS = "Loans for Education, Sports, Art and Culture"
EDU_RECEIPTS = "Education, Sports, Art and Culture (receipts)"
TOTAL_REVENUE = "Total revenue expenditure"
TOTAL_CAPITAL_DISB = "Total capital disbursements, excluding the public account"
TOTAL_CAPITAL_OUTLAY = "Total capital outlay"
TOTAL_LOANS = "Total loans and advances"
SOCIAL_SERVICES = "Social Services"


# Published figures, with the statement each is printed in.
FIXTURES = [
    # (description, state, fiscal_year, estimate_type, measure, expected, source)
    ("All states, education as % of aggregate expenditure",
     "ALL", "2010-11", "A", "share", 16.6,
     "RBI State Finances, Statement 26"),
    ("All states, education as % of aggregate expenditure",
     "ALL", "2025-26", "BE", "share", 13.1,
     "RBI State Finances, Statement 26"),
    ("Kerala, education as % of aggregate expenditure",
     "KL", "2010-11", "A", "share", 17.0,
     "RBI State Finances, Statement 26"),
    ("Delhi, education as % of aggregate expenditure",
     "DL", "2016-17", "A", "share", 24.2,
     "RBI State Finances, Statement 26"),
    ("Punjab, education as % of aggregate expenditure",
     "PB", "2022-23", "A", "share", 8.2,
     "RBI State Finances, Statement 26"),
    ("Telangana, education as % of aggregate expenditure",
     "TG", "2014-15", "A", "share", 11.2,
     "RBI State Finances, Statement 26"),

    ("All states, revenue expenditure on education",
     "ALL", "2010-11", "A", "revenue_education", 187617.3,
     "RBI State Finances, Appendix Table 7"),
    ("All states, revenue expenditure on education",
     "ALL", "2017-18", "A", "revenue_education", 424798.0,
     "RBI State Finances, Appendix Table 7"),
    ("All states, revenue expenditure on education",
     "ALL", "2020-21", "A", "revenue_education", 512428.9,
     "RBI State Finances, Appendix Table 7"),
    ("All states, revenue expenditure on social services",
     "ALL", "2010-11", "A", "revenue_social_services", 365711.2,
     "RBI State Finances, Appendix Table 7"),
    ("All states, revenue expenditure on social services",
     "ALL", "2022-23", "A", "revenue_social_services", 1484370.9,
     "RBI State Finances, Appendix Table 7"),
]


# --------------------------------------------------------------------------- #


def index(rows):
    """(state, year, estimate type) -> {scheme: amount}, summed over duplicates."""
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        key = (r["state_code"], r["fiscal_year"], r["estimate_type"])
        out[key][r["scheme"]] += r["amount_cr"]
    return out


def measure(cell, name: str):
    """One derived figure for a single state-year-estimate, or None."""
    if not cell:
        return None
    revenue = cell.get(EDU_REVENUE)
    capital = cell.get(EDU_CAPITAL)
    total_rev = cell.get(TOTAL_REVENUE)
    total_cap = cell.get(TOTAL_CAPITAL_DISB)

    if name == "revenue_education":
        return revenue
    if name == "revenue_social_services":
        return cell.get(SOCIAL_SERVICES)
    if name == "aggregate_expenditure":
        if total_rev is None or total_cap is None:
            return None
        return total_rev + total_cap
    if name == "education_spend":
        # RBI's numerator: revenue expenditure plus capital outlay. Loans are
        # excluded, and so are the receipts under 0202. Statement 26's own
        # footnote says so, and all 570 cells agree.
        if revenue is None:
            return None
        return revenue + (capital or 0.0)
    if name == "share":
        num = measure(cell, "education_spend")
        den = measure(cell, "aggregate_expenditure")
        if num is None or not den:
            return None
        return 100.0 * num / den
    raise SystemExit("unknown measure %r" % name)


def check_fixtures(by_cell) -> list:
    failures = []
    print("\nState fixtures")
    for desc, code, fy, etype, name, expected, source in FIXTURES:
        got = measure(by_cell.get((code, fy, etype)), name)
        pct = name == "share"
        tol = PCT_TOLERANCE if pct else TOLERANCE
        if got is None:
            print("  %-52s %-9s %-3s %>14s" % (desc[:52], fy, etype, "MISSING"))
            failures.append("%s (%s %s): nothing parsed, expected %s per %s"
                            % (desc, fy, etype, expected, source))
            continue
        diff = got - expected
        ok = abs(diff) <= tol
        unit = "%" if pct else ""
        print("  %-52s %-9s %-3s %12.2f%-1s vs %10.2f%-1s  %+8.2f  %s"
              % (desc[:52], fy, etype, got, unit, expected, unit, diff,
                 "ok" if ok else "FAIL"))
        if not ok:
            failures.append("%s (%s %s): got %.2f, expected %.2f per %s"
                            % (desc, fy, etype, got, expected, source))
    return failures


def check_statement26(by_cell) -> list:
    """Recompute every percentage RBI publishes in Statement 26."""
    path = c.PROCESSED / "state_statement26.csv"
    if not path.exists():
        print("\nStatement 26: no %s; run scripts/parse_states.py" % path.name)
        return ["%s is missing, so the published percentages were not checked"
                % path.name]
    with path.open(encoding="utf-8") as fh:
        published = list(csv.DictReader(fh))

    failures, worst, missing = [], 0.0, 0
    for p in published:
        key = (p["state_code"], p["fiscal_year"], p["estimate_type"])
        got = measure(by_cell.get(key), "share")
        if got is None:
            missing += 1
            if missing <= 5:
                failures.append(
                    "Statement 26 publishes %s for %s %s %s, but nothing was "
                    "parsed for it"
                    % (p["published_pct"], p["state_code"], p["fiscal_year"],
                       p["estimate_type"]))
            continue
        expected = float(p["published_pct"])
        diff = abs(round(got, 1) - expected)
        worst = max(worst, diff)
        if diff > PCT_TOLERANCE:
            if len(failures) < 8:
                failures.append(
                    "%s %s %s: recomputed %.2f%%, RBI publishes %.1f%%"
                    % (p["state_code"], p["fiscal_year"], p["estimate_type"],
                       got, expected))

    checked = len(published) - missing
    print("\nStatement 26, education as a share of aggregate expenditure")
    print("  %d of %d published percentages reproduced, worst gap %.2f pp  %s"
          % (checked - sum(1 for f in failures if "recomputed" in f),
             len(published), worst,
             "ok" if not failures else "FAIL"))
    if missing:
        print("  %d published cells had nothing to compare against" % missing)
    return failures


def check_identities(by_cell) -> list:
    """Containment and sanity, over every state-year we parsed."""
    failures = []
    counts = collections.Counter()
    for (code, fy, etype), cell in sorted(by_cell.items()):
        edu_rev = cell.get(EDU_REVENUE)
        social = cell.get(SOCIAL_SERVICES)
        total_rev = cell.get(TOTAL_REVENUE)

        # Education is item 1 of Social Services, which is part A of
        # developmental revenue expenditure, which is part of the total. Each
        # containment must therefore hold in every state and every year.
        if edu_rev is not None and social is not None:
            counts["edu_in_social"] += 1
            if edu_rev > social + TOLERANCE:
                counts["bad_edu_in_social"] += 1
                if counts["bad_edu_in_social"] <= 3:
                    failures.append(
                        "%s %s %s: education revenue %.2f exceeds social "
                        "services %.2f" % (code, fy, etype, edu_rev, social))
        if social is not None and total_rev is not None:
            counts["social_in_total"] += 1
            if social > total_rev + TOLERANCE:
                counts["bad_social_in_total"] += 1
                if counts["bad_social_in_total"] <= 3:
                    failures.append(
                        "%s %s %s: social services %.2f exceeds total revenue "
                        "expenditure %.2f" % (code, fy, etype, social, total_rev))

        # Capital outlay and loans are published net of recoveries and
        # disinvestment, so a state's total for either can legitimately come
        # out negative -- Punjab's net capital outlay in 1996-97 was minus
        # Rs 239 crore. Education's own positive line then "exceeds" the
        # total without anything being wrong, so containment is only a
        # meaningful test where the total is positive. The negatives are
        # counted and reported rather than hidden, because a negative total
        # is worth knowing about before dividing by it.
        for part, whole, label in (
                (EDU_CAPITAL, TOTAL_CAPITAL_OUTLAY, "capital outlay"),
                (EDU_LOANS, TOTAL_LOANS, "loans and advances")):
            a, b = cell.get(part), cell.get(whole)
            if a is None or b is None:
                continue
            if b < 0:
                counts["negative_" + label] += 1
                continue
            counts["edu_in_" + label] += 1
            if a > b + TOLERANCE:
                counts["bad_edu_in_" + label] += 1
                if counts["bad_edu_in_" + label] <= 3:
                    failures.append(
                        "%s %s %s: education %s %.2f exceeds the state's "
                        "total %.2f" % (code, fy, etype, label, a, b))

        # A state-year with no aggregate expenditure should not have survived
        # the scope filter in parse_states.py.
        agg = measure(cell, "aggregate_expenditure")
        if agg is not None and agg <= 0:
            counts["bad_aggregate"] += 1
            if counts["bad_aggregate"] <= 3:
                failures.append(
                    "%s %s %s: aggregate expenditure is %.2f, so this "
                    "state-year should not be in the table"
                    % (code, fy, etype, agg))

    print("\nState identities over %d state-year-estimates" % len(by_cell))
    for label, key in (("education <= social services", "edu_in_social"),
                       ("social services <= total revenue expenditure",
                        "social_in_total"),
                       ("education capital outlay <= total capital outlay",
                        "edu_in_capital outlay"),
                       ("education loans <= total loans",
                        "edu_in_loans and advances")):
        bad = counts["bad_" + key]
        print("  %-48s %5d checked  %s"
              % (label, counts[key], "ok" if not bad else "FAIL in %d" % bad))
    print("  %-48s %5d checked  %s"
          % ("aggregate expenditure is positive", len(by_cell),
             "ok" if not counts["bad_aggregate"]
             else "FAIL in %d" % counts["bad_aggregate"]))
    for label in ("capital outlay", "loans and advances"):
        n = counts["negative_" + label]
        if n:
            print("  (%d state-years have a negative net total for %s, so "
                  "containment is not tested there)" % (n, label))
    return failures


def check_coverage(rows, by_cell) -> None:
    ref = c.read_json(c.REFERENCE / "states.json")
    meta = {s["code"]: s for s in ref["states"]}
    years = sorted({r["fiscal_year"] for r in rows}, key=c.fy_start)
    codes = sorted({r["state_code"] for r in rows})
    print("\nState coverage")
    print("  %d entities, %s to %s, %d fiscal years"
          % (len(codes), years[0], years[-1], len(years)))

    # Entities whose series starts late, with the reason, so a short line on a
    # chart is never mistaken for a state that stopped spending.
    late = []
    for code in codes:
        ys = sorted({r["fiscal_year"] for r in rows
                     if r["state_code"] == code}, key=c.fy_start)
        if ys[0] != years[0]:
            late.append((code, ys[0], len(ys)))
    if late:
        print("  series starting after %s:" % years[0])
        for code, first, n in late:
            parent = meta[code].get("parent")
            print("    %-3s %-18s from %s, %2d years%s"
                  % (code, meta[code]["name"], first, n,
                     "  (from %s)" % meta[parent]["name"] if parent else ""))

    gsdp_path = c.REFERENCE / "state_gsdp.json"
    if gsdp_path.exists():
        gsdp = c.read_json(gsdp_path)
        print("  GSDP available %s to %s for %d entities; no ratio is shown "
              "outside that window" % (gsdp["years"][0], gsdp["years"][-1],
                                       len(gsdp["series"])))

    print("\n  Union and state education figures must never be added. Most of"
          "\n  the Union's education money is booked as grants-in-aid to"
          "\n  states (major head 3601) and is spent and re-booked by them"
          "\n  under 2202. For a centre-plus-state total the sources are the"
          "\n  ministry's Analysis of Budgeted Expenditure on Education or"
          "\n  the CAG's Combined Finance and Revenue Accounts.")


def run() -> list:
    """Run every state check. Returns a list of failure descriptions."""
    path = c.PROCESSED / "state_education.csv"
    if not path.exists():
        print("\nStates: no %s; run scripts/parse_states.py" % path.name)
        return ["%s is missing, so no state check ran" % path.name]

    rows = c.read_long_table(path)
    print("\n" + "=" * 78)
    print("state_education.csv: %s rows" % format(len(rows), ","))
    by_cell = index(rows)

    failures = (check_fixtures(by_cell)
                + check_statement26(by_cell)
                + check_identities(by_cell))
    check_coverage(rows, by_cell)
    return failures


if __name__ == "__main__":
    bad = run()
    if bad:
        print("\n%d FAILURES" % len(bad))
        for f in bad:
            print("  -", f)
        raise SystemExit(1)
    print("\nall state checks passed")

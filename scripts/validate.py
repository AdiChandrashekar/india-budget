"""Check the processed tables against published figures and internal identities.

Run this after any pipeline change. It exits non-zero on the first failure, so
it works as a CI gate.

    python scripts/validate.py

Two kinds of check:

*   Fixtures - numbers printed in the budget documents themselves, so a pass
    means we reproduce what the government published, not merely what we
    parsed consistently.
*   Identities - relationships that must hold within every demand, which catch
    a parser that drops or double-counts rows even when no fixture covers the
    year.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import validate_states  # noqa: E402

TOLERANCE = 1.0          # Rs crore; the documents round to two decimals


# Published figures. Source is named so a failure can be argued with.
FIXTURES = [
    # (description, fiscal_year, estimate_type, selector, expected_cr, source)
    ("Total Union expenditure", "2026-27", "BE", "union_total", 5347315.0,
     "Budget at a Glance 2026-27"),
    ("Dept of School Education & Literacy", "2026-27", "BE",
     "dept:school education and literacy", 83562.26, "Demand No. 25, 2026-27"),
    ("Dept of Higher Education", "2026-27", "BE",
     "dept:higher education", 55727.22, "Demand No. 26, 2026-27"),
    ("Ministry of Education (both departments)", "2026-27", "BE",
     "moe", 139289.48, "PRS Demand for Grants 2026-27: Education"),

    # The PDF era. These two years exist in the table only because the
    # Demands for Grants were read out of alldg.pdf, so they are checked
    # against Budget at a Glance rather than against the parser's own
    # arithmetic. 2020-21 and 2021-22 are the years that used to be the hole
    # in the series; 2003-04 is as far back as the documents reach.
    ("Total Union expenditure", "2020-21", "A", "union_total", 3509836.0,
     "Budget at a Glance 2022-23, line 9"),
    ("Total Union expenditure", "2021-22", "A", "union_total", 3793801.0,
     "Budget at a Glance 2023-24, line 9"),
    ("Total Union expenditure", "2021-22", "BE", "union_total", 3483236.0,
     "Budget at a Glance 2022-23, line 9"),
    ("Total Union expenditure", "2022-23", "BE", "union_total", 3944909.0,
     "Budget at a Glance 2023-24, line 9"),
]

# Budget at a Glance prints whole crore, and the demands carry paise, so a
# total summed from the demands lands within a rupee or so of it rather than
# on it.
FIXTURE_TOLERANCE = {
    "union_total": 2.0,
}


def demand_of(row) -> str:
    return row["source_page"].split("!dg")[-1]


def net_by_demand(rows, fy: str, etype: str):
    """Each demand's expenditure net of receipts netted against it."""
    per = collections.defaultdict(dict)
    for r in rows:
        if r["fiscal_year"] != fy or r["estimate_type"] != etype:
            continue
        if r["major_head"] or r["definition"] != "whole":
            continue
        per[demand_of(r)][r["account"]] = r["amount_cr"]
    return {d: a.get("net_total", a.get("gross_total", 0.0))
            for d, a in per.items()}


def dept_net(rows, fy: str, etype: str, needle: str) -> float:
    total = 0.0
    for r in rows:
        if (r["fiscal_year"] == fy and r["estimate_type"] == etype
                and r["account"] == "net_total" and not r["major_head"]
                and needle in r["ministry_or_dept"].lower()):
            total += r["amount_cr"]
    return total


def resolve(rows, selector: str, fy: str, etype: str) -> float:
    if selector == "union_total":
        return sum(net_by_demand(rows, fy, etype).values())
    if selector == "moe":
        return (dept_net(rows, fy, etype, "school education")
                + dept_net(rows, fy, etype, "higher education"))
    if selector.startswith("dept:"):
        return dept_net(rows, fy, etype, selector[5:])
    raise SystemExit("unknown selector %r" % selector)


def check_fixtures(rows) -> list:
    failures = []
    print("Fixtures")
    for desc, fy, etype, selector, expected, source in FIXTURES:
        got = resolve(rows, selector, fy, etype)
        diff = got - expected
        ok = abs(diff) <= FIXTURE_TOLERANCE.get(selector, TOLERANCE)
        print("  %-42s %-9s %-3s %14.2f vs %14.2f  %+9.2f  %s"
              % (desc, fy, etype, got, expected, diff, "ok" if ok else "FAIL"))
        if not ok:
            failures.append("%s (%s %s): got %.2f, expected %.2f per %s"
                            % (desc, fy, etype, got, expected, source))
    return failures


def check_identities(rows) -> list:
    """gross + recoveries = net, and major heads sum to the section total.

    A Union Territory's demand is published as one block per ministry, each
    with its own section totals, and then totalled again for the demand as a
    whole, so its section totals come to twice its major heads. That is how
    the document reads, not a parse error, and the parser marks such a
    statement with a *_block account. Those demands are counted and named
    here rather than checked, because the identity does not apply to them.
    """
    failures = []
    nested = {(r["fiscal_year"], r["estimate_type"], demand_of(r))
              for r in rows if r["account"].endswith("_block")}
    groups = collections.defaultdict(lambda: collections.defaultdict(float))
    heads = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        key = (r["fiscal_year"], r["estimate_type"], demand_of(r))
        if r["major_head"]:
            heads[key][r["account"]] += r["amount_cr"]
        else:
            groups[key][r["account"]] += r["amount_cr"]

    bad_net = bad_section = 0
    for key, acc in groups.items():
        if key in nested:
            continue
        gross = acc.get("gross_total")
        net = acc.get("net_total")
        if gross is None or net is None:
            continue
        recov = (heads[key].get("recovery_revenue", 0.0)
                 + heads[key].get("recovery_capital", 0.0))
        if abs(gross + recov - net) > TOLERANCE:
            bad_net += 1
            if bad_net <= 5:
                failures.append(
                    "%s demand %s: gross %.2f + recoveries %.2f != net %.2f"
                    % (key[0] + " " + key[1], key[2], gross, recov, net))

        for section in ("revenue", "capital"):
            total = acc.get("gross_" + section)
            parts = heads[key].get("gross_" + section)
            if total is None or parts is None:
                continue
            if abs(total - parts) > TOLERANCE:
                bad_section += 1
                if bad_section <= 5:
                    failures.append(
                        "%s demand %s: %s heads sum to %.2f, section total %.2f"
                        % (key[0] + " " + key[1], key[2], section, parts, total))

    print("\nIdentities over %d demand-years" % len(groups))
    print("  gross + recoveries = net            %s"
          % ("ok" if not bad_net else "FAIL in %d" % bad_net))
    print("  major heads sum to section total    %s"
          % ("ok" if not bad_section else "FAIL in %d" % bad_section))
    return failures


def check_coverage(rows) -> None:
    print("\nCoverage")
    by_type = collections.defaultdict(set)
    for r in rows:
        by_type[r["estimate_type"]].add(r["fiscal_year"])
    for etype in ("A", "RE", "BE"):
        ys = sorted(by_type[etype], key=c.fy_start)
        print("  %-3s %2d years  %s" % (etype, len(ys), ", ".join(ys)))
    allyears = sorted({y for s in by_type.values() for y in s}, key=c.fy_start)
    span = range(c.fy_start(allyears[0]), c.fy_start(allyears[-1]) + 1)
    missing = [c.fy_shift("%d-%02d" % (y, (y + 1) % 100), 0) for y in span
               if ("%d-%02d" % (y, (y + 1) % 100)) not in allyears]
    if missing:
        print("  gaps in the span: %s" % ", ".join(missing))
        print("  (editions for these years ship PDF only; see docs/FINDINGS.md)")


def main() -> None:
    path = c.PROCESSED / "union_demands.csv"
    if not path.exists():
        raise SystemExit("no %s; run scripts/parse_union.py first" % path.name)
    rows = c.read_long_table(path)
    print("union_demands.csv: %s rows\n" % format(len(rows), ","))

    failures = check_fixtures(rows) + check_identities(rows)
    check_coverage(rows)

    # The state layer's own fixtures and identities live in validate_states.py.
    failures += validate_states.run()

    if failures:
        print("\n%d FAILURES" % len(failures))
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()

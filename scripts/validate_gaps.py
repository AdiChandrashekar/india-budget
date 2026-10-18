"""Fixtures and identities for the data that closed the gaps.

Called by scripts/validate.py; run alone with

    python scripts/validate_gaps.py

Each fixture is a number printed in a published document, named so that a
failure can be argued with. Where possible the document is not the one the
pipeline read, so a pass means two publications agree, not that a parser
agrees with itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

DATA = c.ROOT / "data"


def _load(name):
    path = DATA / name
    if not path.exists():
        return None
    return c.read_json(path)


def _check(failures, desc, got, want, tol, source):
    ok = got is not None and abs(got - want) <= tol
    print("  %-58s %14s vs %14.2f  %s" % (desc[:58], "%.2f" % got if got is not None
                                           else "missing", want, "ok" if ok else "FAIL"))
    if not ok:
        failures.append("%s: got %s, expected %.2f per %s" % (desc, got, want, source))


# --------------------------------------------------------------------------- #


def gdp(failures):
    d = _load("gdp.json")
    print("\nNational GDP (data/gdp.json)")
    if d is None:
        failures.append("data/gdp.json missing; run scripts/national_gdp.py")
        return
    s = d["series"]
    for desc, base, fy, want, tol, src in [
        # The ABE prints the GDP it divides by; it is a different ministry's
        # document from the RBI Handbook this file was read from.
        ("GDP 2011-12, base 2011-12", "2011-12", "2011-12", 8736329, 1,
         "MoE ABE 2019-20 to 2021-22, Table 4, col. 3"),
        ("GDP 2019-20, base 2011-12", "2011-12", "2019-20", 20103593, 1,
         "MoE ABE 2019-20 to 2021-22, Table 4, col. 3"),
        ("GDP 2018-19, base 2011-12", "2011-12", "2018-19", 18899668, 1,
         "MoE ABE 2019-20 to 2021-22, Table 4, col. 3"),
        ("GDP 2004-05, base 2004-05", "2004-05", "2004-05", 3242209, 1,
         "RBI HBIE 2017, Table 1 (Rs 32,422.09 billion)"),
        ("GDP 2022-23, base 2022-23", "2022-23", "2022-23", 26117627, 1,
         "RBI HBIE 2026, Table 1"),
        ("GDP 2022-23, base 2011-12 (the overlap)", "2011-12", "2022-23", 26890473, 1,
         "RBI HBIE 2026, Table 1"),
    ]:
        _check(failures, desc, s.get(base, {}).get(fy), want, tol, src)
    if d["meta"]["breaks"] != ["2011-12", "2022-23"]:
        failures.append("gdp.json breaks are %s, expected the two rebasings"
                        % d["meta"]["breaks"])
    years = sorted(d["preferred"], key=c.fy_start)
    need = set(range(1990, 2026))
    have = {c.fy_start(y) for y in years}
    if need - have:
        failures.append("gdp.json preferred series misses %s" % sorted(need - have))
    print("  preferred series %s to %s, breaks at %s"
          % (years[0], years[-1], ", ".join(d["meta"]["breaks"])))


def schemes(failures):
    d = _load("schemes.json")
    print("\nSchemes (data/schemes.json)")
    if d is None:
        failures.append("data/schemes.json missing; run scripts/parse_schemes.py")
        return
    by = {s["id"]: s for s in d["schemes"]}

    def v(sid, fy, et, member=None):
        s = by.get(sid)
        if s is None:
            return None
        src = s["by_member"].get(member, {}) if member else s["total"]
        return src.get(fy, {}).get(et)

    for desc, sid, member, fy, et, want, src in [
        ("Samagra Shiksha BE 2026-27", "samagra_shiksha", None, "2026-27", "BE",
         42100.02, "SBE 2026-27, Demand 25, item 12 'Net'"),
        ("PM POSHAN BE 2026-27", "pm_poshan", None, "2026-27", "BE", 12750.00,
         "SBE 2026-27, Demand 25, item 13 'Net'"),
        ("Samagra Shiksha BE 2022-23", "samagra_shiksha", None, "2022-23", "BE",
         37383.36, "SBE 2022-23, Demand 25, 'Total - Samagra Shiksha'"),
        ("Samagra Shiksha BE 2019-20 (first year as one line)", "samagra_shiksha",
         "samagra_shiksha", "2019-20", "BE", 36322.00, "SBE 2020-21, Demand 58"),
        ("Sarva Shiksha Abhiyan BE 2010-11", "samagra_shiksha", "ssa", "2010-11", "BE",
         15000.00, "SBE 2011-12, Demand 58 (items 6, 9.02 and the NE line)"),
        ("Mid-Day Meal BE 2013-14", "pm_poshan", None, "2013-14", "BE", 13215.00,
         "SBE 2013-14, Demand 59: item 5 Total 3917.50 + 9.01 Total 7976.00 "
         "+ NE 34.04 1321.50"),
        ("RUSA BE 2016-17", "pm_usha", None, "2016-17", "BE", 1300.00,
         "SBE 2016-17, Demand 52, 'National Education Mission - RUSA'"),
    ]:
        _check(failures, desc, v(sid, fy, et, member), want, 0.02, src)
    # A scheme cannot exceed the department it is printed in.
    import csv
    path = c.PROCESSED / "union_schemes.csv"
    gt = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["account"] == "sbe_grand_total":
                gt[(r["source_edition"], r["source_page"], r["fiscal_year"],
                    r["estimate_type"])] = float(r["amount_cr"])
    _check(failures, "SBE Grand Total, School Education BE 2026-27",
           gt.get(("ExpBudget 2026-27", "sbe25", "2026-27", "BE")), 83562.26, 0.01,
           "Demand No. 25, 2026-27 (the Demands for Grants)")
    _check(failures, "SBE Grand Total, Higher Education BE 2026-27",
           gt.get(("ExpBudget 2026-27", "sbe26", "2026-27", "BE")), 55727.22, 0.01,
           "Demand No. 26, 2026-27 (the Demands for Grants)")
    names = [m["name"] for s in d["schemes"] for m in s["members"]]
    if len(set(names)) != len(names):
        failures.append("a lineage member appears twice")


def union_actuals(failures):
    d = _load("union_actuals.json")
    print("\nUnion actuals before 2015-16 (data/union_actuals.json)")
    if d is None:
        failures.append("data/union_actuals.json missing; run scripts/parse_union_actuals.py")
        return
    y = d["years"]

    def total(fy):
        return y.get(fy, {}).get("total_expenditure")

    for fy, want, src in [
        ("1998-99", 279366, "Budget at a Glance 2000-01, line 16"),
        ("2001-02", 362453, "Budget at a Glance 2003-04, line 16"),
        ("2008-09", 883956, "Budget at a Glance 2010-11, line 16"),
        ("2011-12", 1304365, "Budget at a Glance 2013-14, line 16"),
    ]:
        # Budget at a Glance prints whole crore.
        _check(failures, "Total expenditure, actuals %s" % fy, total(fy), want, 1.0, src)

    def dept(fy, key):
        for x in y.get(fy, {}).get("departments", []):
            if x["key"] == key:
                return x["total"]
        return None

    # Two documents of the same edition family read by two different
    # parsers: Statement 2 here, the Statement of Budget Estimates there.
    _check(failures, "School Education actuals 2009-10",
           dept("2009-10", "department of school education and literacy")
           or dept("2009-10", "school education and literacy"), 24466.07, 0.01,
           "SBE 2011-12, Demand 58, actuals column")
    _check(failures, "Higher Education actuals 2013-14 (central + State Plans)",
           dept("2013-14", "department of higher education")
           or dept("2013-14", "higher education"), 24465.17, 0.01,
           "SBE 2015-16, Demand 60, actuals column")
    years = sorted(y, key=c.fy_start)
    span = set(range(c.fy_start(years[0]), c.fy_start(years[-1]) + 1))
    if span - {c.fy_start(x) for x in years}:
        failures.append("union_actuals.json has holes")
    if years[-1] != "2014-15":
        failures.append("union_actuals.json should end at 2014-15, where the "
                        "Demands for Grants' own actuals begin")
    print("  actuals %s to %s, %d years" % (years[0], years[-1], len(years)))


def gsdp(failures):
    d = _load("gsdp.json")
    print("\nState GSDP back-series (data/gsdp.json)")
    if d is None:
        failures.append("data/gsdp.json missing; run scripts/state_gsdp_series.py")
        return
    s = d["series"]
    for desc, code, base, fy, want, src in [
        ("Andhra Pradesh 1990-91, base 1980-81", "AP", "1980-81", "1990-91",
         34621.95, "RBI HSIS 2018, Table 15 (Rs 34,62,195 lakh)"),
        ("Uttar Pradesh 1990-91, base 1980-81", "UP", "1980-81", "1990-91",
         55505.71, "RBI HSIS 2018, Table 15 (Rs 55,50,571 lakh)"),
        ("Bihar 1993-94, base 1993-94 (residual boundary)", "BR", "1993-94",
         "1993-94", 22811.98, "RBI HSIS 2018, Table 15 (Rs 22,81,198 lakh)"),
        ("Delhi 2004-05, base 2004-05", "DL", "2004-05", "2004-05", 100324.52,
         "RBI HSIS 2018, Table 15 (Rs 1,00,32,452 lakh)"),
    ]:
        _check(failures, desc, s.get(code, {}).get(base, {}).get(fy), want, 0.01, src)
    bb = d["budget_boundary"]
    ap = s["AP"]["2004-05"]["2004-05"] + s["TG"]["2004-05"]["2004-05"]
    _check(failures, "Undivided AP 2004-05 = residual AP + Telangana (2004-05 base)",
           bb["AP"]["2004-05"]["2004-05"], ap, 0.01,
           "both halves as printed in RBI HSIS 2018, Table 15")
    if "TG" in bb and any(c.fy_start(fy) < 2014 for b in bb["TG"].values() for fy in b):
        failures.append("Telangana has a budget-boundary GSDP before it had a budget")
    bases = [x["base"] for x in d["segments"]]
    if bases != ["1980-81", "1993-94", "1999-00", "2004-05", "2011-12"]:
        failures.append("gsdp.json segments are %s" % bases)
    print("  segments: %s" % ", ".join("%s (%s..%s)" % (x["base"], x["first"], x["last"])
                                       for x in d["segments"]))


def abe(failures):
    d = _load("abe.json")
    print("\nAnalysis of Budgeted Expenditure on Education (data/abe.json)")
    if d is None:
        failures.append("data/abe.json missing; run scripts/fetch_abe.py and parse_abe.py")
        return
    n = d["national"]

    def nat(fy, kind, part):
        return n.get(fy, {}).get(kind, {}).get(part)

    for desc, fy, kind, part, want, src in [
        ("Centre+States education, all depts, 2019-20 A", "2019-20",
         "education_and_other_departments", "total", 812214, "ABE 2019-22, Table 4"),
        ("Centre education, all depts, 2019-20 A", "2019-20",
         "education_and_other_departments", "centre", 202991, "ABE 2019-22, Table 4"),
        ("Centre+States, education depts, 2000-01", "2000-01",
         "education_departments", "total", 62498, "ABE 2019-22, Table 4"),
        # A different table of a different edition, nine years older.
        ("Centre+States, all depts, 2010-11 A", "2010-11",
         "education_and_other_departments", "total", 293478.25,
         "ABE 2010-11 to 2012-13, Table 6, Total (Education)"),
    ]:
        _check(failures, desc, nat(fy, kind, part), want, 1.0, src)
    st = d["states"]

    def sv(code, sector, fy, et):
        return st.get(code, {}).get(sector, {}).get(fy, {}).get(et)

    for desc, code, sector, fy, et, want, src in [
        ("Andhra Pradesh elementary 2019-20 A", "AP", "elementary", "2019-20", "A",
         9572.78, "ABE 2019-22, Statement 4 (Rs 9,57,27,800 thousand)"),
        ("All states & UTs elementary 2019-20 A", "total", "elementary", "2019-20",
         "A", 226837.56, "ABE 2019-22, Statement 14, col. 3"),
        ("All states & UTs secondary 2019-20 A", "total", "secondary", "2019-20",
         "A", 169040.99, "ABE 2019-22, Statement 14, col. 3"),
    ]:
        _check(failures, desc, sv(code, sector, fy, et), want, 0.02, src)
    years = sorted({fy for code in st.values() for sec in code.values() for fy in sec},
                   key=c.fy_start)
    print("  state sub-sector years %s to %s" % (years[0], years[-1]))


def run() -> list:
    failures = []
    for f in (gdp, schemes, union_actuals, gsdp, abe):
        f(failures)
    return failures


if __name__ == "__main__":
    fails = run()
    if fails:
        print("\n%d FAILURES" % len(fails))
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print("\nall gap checks passed")

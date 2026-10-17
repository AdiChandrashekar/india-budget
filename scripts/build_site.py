"""Turn the long table into the compact JSON the site reads.

The long table is the archive: one row per published number, with provenance.
The site needs something much smaller, so this collapses it into series keyed
by year and estimate type, and precomputes the three definitions of education
spending so the page does not have to know the account rules.

    python scripts/build_site.py

Writes data/union.json.
"""

from __future__ import annotations

import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

# Functional classification. These are LMMHA major heads, common to the Union
# and every state, which is what makes a cross-government comparison possible.
EDUCATION_HEADS = {
    "2202": "General Education",
    "2203": "Technical Education",
    "2204": "Sports and Youth Services",
    "2205": "Art and Culture",
    "4202": "Capital Outlay on Education, Sports, Art and Culture",
    "6202": "Loans for Education, Sports, Art and Culture",
}
# RBI's "education" figure for the states covers all of the above. A narrower
# reading stops at teaching, so both are offered rather than chosen for you.
EDUCATION_HEADS_NARROW = ("2202", "2203", "4202", "6202")

MOE_NEEDLES = ("school education", "higher education",
               "elementary education", "secondary education")


def demand_of(row) -> str:
    return row["source_page"].split("!dg")[-1]


def is_moe(name) -> bool:
    """Is this department part of the education ministry, in any year's naming?"""
    key = c.dept_key(name)
    return any(n in key for n in MOE_NEEDLES)


def series(pairs):
    """[(fy, etype, amount)] -> {fy: {etype: amount}}"""
    out = collections.defaultdict(dict)
    for fy, etype, amount in pairs:
        out[fy][etype] = round(out[fy].get(etype, 0.0) + amount, 2)
    return dict(out)


def main() -> None:
    rows = c.read_long_table(c.PROCESSED / "union_demands.csv")
    ministries = {}
    mpath = c.REFERENCE / "union_ministries.json"
    if mpath.exists():
        ministries = c.read_json(mpath)

    years = sorted({r["fiscal_year"] for r in rows}, key=c.fy_start)

    # ---- the whole budget, by demand ---------------------------------------
    # A demand's expenditure is its net figure: gross minus the receipts the
    # document nets against it. parse_union.py guarantees a net row exists.
    demand_rows = [r for r in rows
                   if r["account"] == "net_total" and not r["major_head"]]

    # Group by department, never by demand number. Demand numbers are not
    # identifiers: the list was re-alphabetised, so the education departments
    # were Demands 57 and 58 in the 2019-20 edition and 25 and 26 from
    # 2024-25. Keying on the number silently splices two different ministries
    # into one series.
    demands = {}
    for r in demand_rows:
        key = c.dept_key(r["ministry_or_dept"])
        rec = demands.setdefault(key, {
            "name": r["ministry_or_dept"],
            "numbers": {},
            "points": [],
            "latest": "",
        })
        rec["points"].append((r["fiscal_year"], r["estimate_type"],
                              r["amount_cr"]))
        rec["numbers"][r["fiscal_year"]] = demand_of(r)
        # Prefer the most recent edition's spelling for display.
        edition = r["source_edition"].split()[-1]
        if not rec["latest"] or c.fy_start(edition) >= c.fy_start(rec["latest"]):
            rec["latest"] = edition
            rec["name"] = r["ministry_or_dept"]

    latest_ministries = (ministries.get(max(ministries, key=c.fy_start))
                         if ministries else {})
    out_demands = []
    for key, rec in demands.items():
        newest_number = rec["numbers"].get(years[-1], "")
        info = latest_ministries.get(newest_number, {})
        out_demands.append({
            "key": key,
            "name": rec["name"],
            "ministry": info.get("ministry", rec["name"]),
            "demand_numbers": rec["numbers"],
            "series": series(rec["points"]),
        })
    out_demands.sort(key=lambda x: x["name"])

    totals = series([(fy, etype, amount)
                     for d in out_demands
                     for fy, by_type in d["series"].items()
                     for etype, amount in by_type.items()])

    # ---- the whole budget, by function -------------------------------------
    head_points = collections.defaultdict(list)
    head_names = {}
    for r in rows:
        if not r["major_head"] or not r["account"].startswith("gross"):
            continue
        code = r["major_head"]
        head_points[code].append((r["fiscal_year"], r["estimate_type"],
                                  r["amount_cr"]))
        name = r["scheme"]
        if name and len(name) > len(head_names.get(code, "")):
            head_names[code] = name
    heads = [{
        "code": code,
        "name": EDUCATION_HEADS.get(code) or head_names.get(code, code),
        "education": code in EDUCATION_HEADS,
        "series": series(pts),
    } for code, pts in head_points.items()]
    heads.sort(key=lambda h: h["code"])

    # ---- education, three ways ---------------------------------------------
    # These do not reconcile, and are not meant to. Most of the Ministry of
    # Education's money leaves as grants-in-aid to states (major head 3601),
    # which the functional heads for education do not count, so the ministry
    # figure runs well above the functional one. Saying which definition a
    # number uses is the whole point of showing all three.
    moe = [(r["fiscal_year"], r["estimate_type"], r["amount_cr"])
           for r in demand_rows if is_moe(r["ministry_or_dept"])]

    edu_head_rows = [r for r in rows
                     if r["major_head"] in EDUCATION_HEADS
                     and r["account"].startswith("gross")]
    func_all = [(r["fiscal_year"], r["estimate_type"], r["amount_cr"])
                for r in edu_head_rows]
    func_narrow = [(r["fiscal_year"], r["estimate_type"], r["amount_cr"])
                   for r in edu_head_rows
                   if r["major_head"] in EDUCATION_HEADS_NARROW]

    education = {
        "moe": {
            "label": "Ministry of Education",
            "note": ("The two education departments' own demands, net of "
                     "receipts. What budget speeches and the press quote."),
            "series": series(moe),
        },
        "functional": {
            "label": "Education, sports, art and culture (functional)",
            "note": ("Major heads 2202, 2203, 2204, 2205, 4202 and 6202 "
                     "across every ministry. The definition RBI uses for the "
                     "states, so it is the one that compares."),
            "series": series(func_all),
        },
        "functional_narrow": {
            "label": "Education only (functional)",
            "note": ("The same, without sports (2204) and art and culture "
                     "(2205)."),
            "series": series(func_narrow),
        },
    }

    # Where the Ministry of Education's money sits in the accounts. This is the
    # trap worth showing rather than burying: most of it is classified as
    # grants-in-aid to state governments (3601), not as education (2202/2203),
    # which is why the ministry total and the functional total differ so much
    # and why Union and state figures must never simply be added.
    # Match on each row's own department name, not on a set of demand numbers:
    # the numbers mean different ministries in different editions.
    moe_head_points = collections.defaultdict(list)
    for r in rows:
        if (is_moe(r["ministry_or_dept"]) and r["major_head"]
                and r["account"].startswith("gross")):
            moe_head_points[r["major_head"]].append(
                (r["fiscal_year"], r["estimate_type"], r["amount_cr"]))
    moe_heads = [{
        "code": code,
        "name": EDUCATION_HEADS.get(code) or head_names.get(code, code),
        "education": code in EDUCATION_HEADS,
        "series": series(pts),
    } for code, pts in moe_head_points.items()]
    moe_heads.sort(key=lambda h: -(h["series"].get(years[-1], {}).get("BE") or 0))

    # Which education departments existed in each year, for the lineage note.
    moe_depts = sorted({r["ministry_or_dept"] for r in demand_rows
                        if is_moe(r["ministry_or_dept"])})

    editions = sorted({r["source_edition"] for r in rows})
    gap = [y for y in range(c.fy_start(years[0]), c.fy_start(years[-1]) + 1)
           if ("%d-%02d" % (y, (y + 1) % 100)) not in years]

    payload = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "unit": "Rs crore, nominal",
            "years": years,
            "gap_years": ["%d-%02d" % (y, (y + 1) % 100) for y in gap],
            "editions": editions,
            "estimate_types": {
                "A": "Actuals",
                "RE": "Revised Estimates",
                "BE": "Budget Estimates",
            },
            "source": "indiabudget.gov.in, Expenditure Budget / Demands for Grants",
            "moe_departments": moe_depts,
            "rows_in_long_table": len(rows),
        },
        "totals": totals,
        "education": education,
        "demands": out_demands,
        "heads": heads,
        "moe_heads": moe_heads,
    }

    # Refuse to ship something obviously broken.
    if not totals or not out_demands or not heads:
        raise SystemExit("empty payload; check the long table")
    latest = years[-1]
    if "BE" not in totals.get(latest, {}):
        raise SystemExit("no BE for %s; the latest edition did not parse" % latest)

    c.write_json(payload, c.ROOT / "data" / "union.json", indent=0)

    print("\nyears      %s" % ", ".join(years))
    print("demands    %d" % len(out_demands))
    print("heads      %d major heads, %d of them education"
          % (len(heads), sum(1 for h in heads if h["education"])))
    print("\neducation, %s BE (Rs crore)" % latest)
    for key, block in education.items():
        v = block["series"].get(latest, {}).get("BE")
        tot = totals.get(latest, {}).get("BE")
        if v and tot:
            print("  %-20s %12.2f   %.2f%% of total expenditure"
                  % (key, v, 100 * v / tot))


if __name__ == "__main__":
    main()

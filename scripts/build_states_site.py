"""Collapse the state long table into the compact JSON the page reads.

    python scripts/build_states_site.py

Writes data/states.json.

Kept separate from build_site.py so the Union and state halves of the site can
be rebuilt independently.

Shares are deliberately *not* precomputed. The page divides education spending
by aggregate expenditure itself, from the two series stored here, which is the
same arithmetic validate_states.py checks against all 570 of RBI's published
percentages. Storing a third, derived series would let the page drift away
from the figure the central bank prints.
"""

from __future__ import annotations

import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

# scheme label in the long table -> key in the payload
MEASURES = {
    "Education, Sports, Art and Culture": "education_revenue",
    "Capital Outlay on Education, Sports, Art and Culture": "education_capital",
    "Loans for Education, Sports, Art and Culture": "education_loans",
    "Education, Sports, Art and Culture (receipts)": "education_receipts",
    "Total revenue expenditure": "total_revenue",
    "Social Services": "social_services",
    "Total capital outlay": "total_capital_outlay",
    "Total loans and advances": "total_loans",
    "Total capital disbursements, excluding the public account":
        "total_capital_disbursement",
}

# RBI's Statement 26 numerator and denominator, named once here so the page
# and the validator cannot disagree about them.
SPEND_PARTS = ("education_revenue", "education_capital")
AGGREGATE_PARTS = ("total_revenue", "total_capital_disbursement")

ESTIMATES = ("A", "RE", "BE")


def collapse(rows):
    """{state: {measure: {year: {etype: amount}}}}"""
    out = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(dict)))
    for r in rows:
        key = MEASURES.get(r["scheme"])
        if key is None:
            continue
        cell = out[r["state_code"]][key][r["fiscal_year"]]
        cell[r["estimate_type"]] = round(
            cell.get(r["estimate_type"], 0.0) + r["amount_cr"], 2)
    return out


def derive(series, parts):
    """Sum several measures year by year and estimate type by estimate type.

    A year is only summed where every part is present on that basis, so an
    actuals figure is never completed with a budget estimate.
    """
    out = {}
    first = series.get(parts[0], {})
    for year in first:
        for etype in ESTIMATES:
            values = [series.get(p, {}).get(year, {}).get(etype) for p in parts]
            if any(v is None for v in values):
                continue
            out.setdefault(year, {})[etype] = round(sum(values), 2)
    return out


def main() -> None:
    path = c.PROCESSED / "state_education.csv"
    if not path.exists():
        raise SystemExit("no %s; run scripts/parse_states.py first" % path.name)
    rows = c.read_long_table(path)
    ref = c.read_json(c.REFERENCE / "states.json")
    editions = c.read_json(c.REFERENCE / "state_editions.json")

    gsdp = {}
    gsdp_meta = {}
    gpath = c.REFERENCE / "state_gsdp.json"
    if gpath.exists():
        g = c.read_json(gpath)
        gsdp = g["series"]
        gsdp_meta = {"years": g["years"], "unit": g["unit"],
                     "source": g["source"], "source_url": g["source_url"],
                     "notes": g["notes"]}

    collapsed = collapse(rows)
    years = sorted({r["fiscal_year"] for r in rows}, key=c.fy_start)

    entities, series_out = [], {}
    for meta in ref["states"]:
        code = meta["code"]
        series = collapsed.get(code)
        if not series:
            continue
        series = {k: dict(v) for k, v in series.items()}
        series["education_spend"] = derive(series, SPEND_PARTS)
        series["aggregate_expenditure"] = derive(series, AGGREGATE_PARTS)

        # The span of the *budget* series, measured before GSDP is attached.
        # The national accounts back-cast Telangana's GSDP to 2011-12, three
        # years before Telangana had a budget, so taking the first year across
        # every series would report the state as existing in 2011-12.
        mine = sorted({y for k, m in series.items() for y in m}, key=c.fy_start)

        if code in gsdp:
            series["gsdp"] = gsdp[code]
        entities.append({
            "code": code,
            "name": meta["name"],
            "kind": meta["kind"],
            "parent": meta["parent"],
            "successors": meta["successors"],
            "formed": meta["formed"],
            "note": meta["note"],
            "first_year": mine[0],
            "last_year": mine[-1],
            "has_gsdp": code in gsdp,
        })
        series_out[code] = series

    # The Union's own functional education figure, for the contrast the page
    # has to draw -- and has to label, because these two must never be added.
    union = {}
    upath = c.ROOT / "data" / "union.json"
    if upath.exists():
        u = c.read_json(upath)
        block = u.get("education", {}).get("functional", {})
        union = {
            "label": block.get("label", ""),
            "note": block.get("note", ""),
            "years": u.get("meta", {}).get("years", []),
            "series": block.get("series", {}),
        }

    payload = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "unit": "Rs crore, nominal",
            "years": years,
            "edition": editions.get("edition", ""),
            "source": ("RBI, State Finances: A Study of Budgets -- e-STATES "
                       "database, with Statement 26 and Appendix Table 7 as "
                       "the published checks"),
            "source_index": editions["state_finances"]["index"],
            "estimate_types": {"A": "Accounts", "RE": "Revised Estimates",
                               "BE": "Budget Estimates"},
            "definition": ("Education, Sports, Art and Culture: major heads "
                           "2202, 2203, 2204 and 2205 on revenue account, "
                           "4202 capital outlay and 6202 loans. The same "
                           "functional definition the Union view uses, which "
                           "is what makes the two comparable."),
            "share_definition": ("Education spending is revenue expenditure "
                                 "plus capital outlay, and aggregate "
                                 "expenditure is total revenue expenditure "
                                 "plus total capital disbursements excluding "
                                 "the public account. That is RBI's own "
                                 "Statement 26 definition; all 570 "
                                 "percentages it publishes reproduce from "
                                 "these series."),
            "never_add": ("Union and state education figures must never be "
                          "added. Rs 1.08 lakh crore of the Union's education "
                          "ministry budget for 2026-27 is grants-in-aid to "
                          "state governments (major head 3601), which the "
                          "states then spend and book again under 2202. For a "
                          "genuine centre-plus-state total the sources are "
                          "the ministry's Analysis of Budgeted Expenditure on "
                          "Education or the CAG's Combined Finance and "
                          "Revenue Accounts."),
            "gsdp": gsdp_meta,
            "rows_in_long_table": len(rows),
        },
        "states": entities,
        "series": series_out,
        "union_functional": union,
    }

    # Refuse to ship something obviously broken.
    if len(entities) < 30:
        raise SystemExit("only %d entities; expected 31 states and UTs plus "
                         "the all-states aggregate" % len(entities))
    latest = years[-1]
    for code in ("ALL", "UP", "KL"):
        if not series_out.get(code, {}).get("education_spend", {}).get(latest):
            raise SystemExit("no education figure for %s in %s; the latest "
                             "edition did not parse" % (code, latest))

    c.write_json(payload, c.ROOT / "data" / "states.json", indent=0)

    print("\nentities  %d" % len(entities))
    print("years     %s to %s (%d)" % (years[0], years[-1], len(years)))
    all_ = series_out["ALL"]
    print("\nall states, %s (Rs crore)" % latest)
    for etype in ESTIMATES:
        spend = all_["education_spend"].get(latest, {}).get(etype)
        agg = all_["aggregate_expenditure"].get(latest, {}).get(etype)
        if spend and agg:
            print("  %-3s education %12.2f   aggregate %12.2f   %.2f%%"
                  % (etype, spend, agg, 100 * spend / agg))
    if union.get("series"):
        uyear = max(union["series"], key=c.fy_start)
        ubest = union["series"][uyear]
        print("\nfor contrast, never for addition:")
        print("  Union functional education, %s: %s"
              % (uyear, ", ".join("%s %.2f" % (k, v)
                                  for k, v in sorted(ubest.items()))))


if __name__ == "__main__":
    main()

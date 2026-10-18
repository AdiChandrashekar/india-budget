"""Scheme-level education spending from the Statements of Budget Estimates.

    python scripts/sbe.py fetch-education   # first: find and download
    python scripts/parse_schemes.py         # then this

Reads every education department's SBE from the 1998-99 edition on and
writes

    data/processed/union_schemes.csv   every printed line, long-table shape
    data/schemes.json                  the lineage-tracked schemes, per year
    data/reference/sbe_coverage.json   what was read and what was given up

Checks, any of which stops the write:

1.  Every statement's leaves sum to its Grand Total and its top block
    (sbe.classify). A statement that fails is left out whole and listed in
    the coverage file -- two do, both because the source itself is defective.
2.  Each statement's total equals the net total of the same demand in the
    Demands for Grants, year by year, wherever the demands table has it. Two
    documents, two parsers, one number.
3.  Every printed scheme total ('Total' under a scheme's major heads, 'Net'
    under a parent) equals the sum of the lines it totals.
4.  Every lineage pattern matches something, so a typo in the reference file
    cannot silently drop a scheme.

Which edition a year comes from follows parse_union.py: for each (year,
estimate type, department) the latest edition that printed it and passed.
"""

from __future__ import annotations

import collections
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import sbe  # noqa: E402

LINEAGE = c.REFERENCE / "scheme_lineage.json"
OUT_CSV = c.PROCESSED / "union_schemes.csv"
OUT_JSON = c.ROOT / "data" / "schemes.json"
COVERAGE = c.REFERENCE / "sbe_coverage.json"
TOL = 1.0

# Printed totals the document itself gets wrong, each checked by hand against
# the lines above it. Demand 47 of 1999-00 adds Rs 2.00 crore too little in
# its 1999-00 budget column: the DPEP total prints 758.00 over a Plan figure
# of 760.00, and the error carries into 'Total Elementary Education' and the
# Grand Total (7934.74 against a top block of 7936.74).
MISPRINTS = {
    ("1999-00", 47, "13", "1999-00", "BE"),
}


def squash(label: str) -> str:
    return re.sub(r"[^a-z]", "", label.lower())


def dept_kind(dept: str) -> str:
    d = dept.lower()
    if "higher" in d:
        return "higher"
    if "elementary" in d or "school" in d:
        return "school"
    if "secondary" in d:          # Secondary Education and Higher Education
        return "higher"
    return "education"            # the undivided Department of Education


# --------------------------------------------------------------------------- #


def read_all():
    ref = sbe.load_ref()
    statements, coverage = [], {}
    for fy, nums in ref["education"].items():
        for n, dept in nums.items():
            f = ref["files"][fy][n]
            path = sbe.local_path(fy, int(n), f["format"])
            key = "%s sbe%s" % (fy, n)
            if not path.exists():
                raise SystemExit("%s missing; run scripts/sbe.py fetch-education"
                                 % path)
            try:
                st = sbe.read(path, fy, int(n), f["url"])
            except ValueError as exc:
                coverage[key] = {"dept": dept, "read": False, "why": str(exc)}
                continue
            st.dept = dept
            coverage[key] = {"dept": dept, "format": f["format"],
                             "url": f["url"], "read": not st.problems,
                             "columns": ["%s %s" % col for col in st.columns],
                             "lines": len(st.lines)}
            if st.problems:
                coverage[key]["why"] = st.problems
            if st.notes:
                coverage[key]["notes"] = st.notes
            statements.append(st)
    return statements, coverage


def dg_totals():
    """{(edition, demand, fy, etype): net} from the Demands for Grants."""
    out = {}
    for name in ("union_demands.csv", "union_demands_pdf.csv"):
        path = c.PROCESSED / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["major_head"] or r["definition"] != "whole":
                    continue
                if r["account"] not in ("net_total", "gross_total"):
                    continue
                ed = r["source_edition"].replace("ExpBudget ", "")
                key = (ed, int(r["source_page"].split("!dg")[-1]),
                       r["fiscal_year"], r["estimate_type"])
                if r["account"] == "net_total" or key not in out:
                    out[key] = float(r["amount_cr"])
    return out


def check_against_dg(st, dg, problems, stats):
    for col in st.columns:
        key = (st.edition, st.demand) + col
        if key not in dg:
            continue
        gt = st.grand_total.get(col)
        stats["dg_checked"] += 1
        if gt is None or abs(gt - dg[key]) > TOL:
            problems.append("%s sbe%d %s %s: statement %.2f, demands %.2f"
                            % (st.edition, st.demand, col[0], col[1],
                               gt or 0.0, dg[key]))


def check_printed_totals(st, values, problems, stats):
    """'Total' under a scheme and 'Net' under a parent must equal its lines."""
    # Which lines a printed total covers is not marked: a 'Net' closes a
    # parent but follows its last child, and the 1998-99 'Total' under item
    # 12a covers 12 and 12a together. So a printed total passes if it equals
    # the item it follows, any item enclosing that one, or the run of lines
    # since the previous printed total -- and fails only if it equals none.
    items = {ln.item: k for k, ln in enumerate(st.lines) if ln.item}
    run, boundary = {}, ("item_total", "net", "group_total", "grand_total")
    for k, ln in enumerate(st.lines):
        if ln.kind == "leaf":
            for col, v in ln.values.items():
                run[col] = run.get(col, 0.0) + v
            continue
        if ln.kind not in boundary:
            continue
        if ln.kind in ("item_total", "net") and ln.owner >= 0:
            owner = st.lines[ln.owner]
            candidates = [values.get(ln.owner, {}), dict(run)]
            # The item and the one before it: the 1999-00 DPEP 'Total' covers
            # both of its components, items 12 and 13.
            prev = [j for j in range(ln.owner) if st.lines[j].item]
            if prev:
                a, b = values.get(prev[-1], {}), values.get(ln.owner, {})
                candidates.append({col: a.get(col, 0.0) + b.get(col, 0.0)
                                   for col in set(a) | set(b)})
            anc = sbe.parent_of(owner.item, items)
            while anc:
                candidates.append(values.get(items[anc], {}))
                anc = sbe.parent_of(anc, items)
            for col, v in ln.values.items():
                stats["totals_checked"] += 1
                if (st.edition, st.demand, owner.item) + col in MISPRINTS:
                    stats["misprints"] += 1
                    continue
                if not any(abs(cand.get(col, 0.0) - v) <= TOL
                           for cand in candidates):
                    problems.append(
                        "%s sbe%d item %s %r %s %s: printed %s %.2f, lines %.2f"
                        % (st.edition, st.demand, owner.item, owner.label[:40],
                           col[0], col[1], ln.kind, v,
                           candidates[0].get(col, 0.0)))
        run = {}


# --------------------------------------------------------------------------- #


def long_rows(st, values):
    rows = []
    src = "ExpBudget " + st.edition
    for k, ln in enumerate(st.lines):
        if ln.kind == "leaf":
            owner = st.lines[k] if ln.item else (
                st.lines[ln.owner] if ln.owner >= 0 else None)
            item = owner.item if owner else ""
            for (fy, et), v in ln.values.items():
                rows.append(c.Row(
                    fiscal_year=fy, govt="union", estimate_type=et,
                    source_edition=src, definition="moe",
                    major_head=ln.code if sbe.CODE.match(ln.code or "") else "",
                    ministry_or_dept=st.dept,
                    scheme=owner.label if owner else "",
                    account="sbe_line", amount_cr=v, source_url=st.source_url,
                    source_page="sbe%d!%s" % (st.demand, item)))
        if ln.item and k in values:
            for (fy, et), v in values[k].items():
                rows.append(c.Row(
                    fiscal_year=fy, govt="union", estimate_type=et,
                    source_edition=src, definition="moe",
                    ministry_or_dept=st.dept, scheme=ln.label,
                    account="sbe_item", amount_cr=v, source_url=st.source_url,
                    source_page="sbe%d!%s" % (st.demand, ln.item)))
    for (fy, et), v in st.grand_total.items():
        rows.append(c.Row(
            fiscal_year=fy, govt="union", estimate_type=et,
            source_edition=src, definition="moe", ministry_or_dept=st.dept,
            account="sbe_grand_total", amount_cr=v, source_url=st.source_url,
            source_page="sbe%d" % st.demand))
    return rows


def match_schemes(st, values, lineage, hits):
    """{(scheme id, member id): {(fy, etype): value}} for one statement."""
    exclude = [re.compile(p) for p in lineage["exclude"]]
    pats = [(s["id"], m["id"], [re.compile(p) for p in m["match"]])
            for s in lineage["schemes"] for m in s["members"]]
    items = {ln.item: k for k, ln in enumerate(st.lines) if ln.item}
    matched_items = set()
    out = collections.defaultdict(dict)
    for k, ln in enumerate(st.lines):
        if not ln.item or k not in values:
            continue
        lab = squash(ln.label)
        if any(p.match(lab) for p in exclude):
            continue
        # Never count a line inside a line that is already counted.
        anc = sbe.parent_of(ln.item, items)
        skip = False
        while anc:
            if anc in matched_items:
                skip = True
                break
            anc = sbe.parent_of(anc, items)
        if skip:
            continue
        for sid, mid, ps in pats:
            if any(p.match(lab) for p in ps):
                matched_items.add(ln.item)
                hits[(sid, mid)] += 1
                d = out[(sid, mid)]
                for col, v in values[k].items():
                    d[col] = d.get(col, 0.0) + v
                break
    return out


def main() -> None:
    lineage = c.read_json(LINEAGE)
    statements, coverage = read_all()
    good = [st for st in statements if not st.problems]
    print("%d statements read, %d pass the leaf identity"
          % (len(statements), len(good)))

    problems = []
    stats = collections.Counter()
    dg = dg_totals()
    all_rows = []
    per = {}           # (edition, dept kind) -> {(sid, mid): {col: v}}
    hits = collections.Counter()
    for st in good:
        values = sbe.item_values(st)
        check_against_dg(st, dg, problems, stats)
        check_printed_totals(st, values, problems, stats)
        all_rows.extend(long_rows(st, values))
        found = match_schemes(st, values, lineage, hits)
        slot = per.setdefault((st.edition, dept_kind(st.dept)), {})
        for key, d in found.items():
            tgt = slot.setdefault(key, {})
            for col, v in d.items():
                tgt[col] = tgt.get(col, 0.0) + v
        slot.setdefault("_columns", set()).update(st.columns)

    for s in lineage["schemes"]:
        for m in s["members"]:
            if not hits[(s["id"], m["id"])]:
                problems.append("lineage pattern for %s/%s matches no line"
                                % (s["id"], m["id"]))

    print("checked %d statement totals against the Demands for Grants, %d "
          "printed scheme totals against their lines"
          % (stats["dg_checked"], stats["totals_checked"]))
    if problems:
        print("\nrefusing to write:")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print("  ... and %d more" % (len(problems) - 40))
        raise SystemExit(1)

    c.write_long_table(sorted(all_rows, key=lambda r: (
        c.fy_start(r.fiscal_year), r.estimate_type, r.source_edition,
        r.source_page, r.account)), OUT_CSV)

    # ---- per scheme: latest edition wins for each (year, etype, dept) -----
    # The undivided Department of Education (1998-99, 1999-00 editions)
    # stands in for whichever department the scheme later belongs to.
    schemes_out = []
    for s in lineage["schemes"]:
        members = {}
        sources = collections.defaultdict(dict)
        cols_seen = {}
        for (ed, kind), slot in sorted(per.items(), key=lambda kv: c.fy_start(kv[0][0])):
            if kind not in (s["department"], "education"):
                continue
            for col in slot["_columns"]:
                cols_seen[col] = ed          # later editions overwrite
        for col, ed in cols_seen.items():
            fy, et = col
            for kind in (s["department"], "education"):
                slot = per.get((ed, kind))
                if slot is None or col not in slot["_columns"]:
                    continue
                for m in s["members"]:
                    v = slot.get((s["id"], m["id"]), {}).get(col)
                    if v is None:
                        continue
                    members.setdefault(m["id"], {}).setdefault(fy, {})[et] = round(v, 2)
                sources[fy][et] = "ExpBudget " + ed
        total = {}
        for mid, series in members.items():
            for fy, d in series.items():
                for et, v in d.items():
                    total.setdefault(fy, {})[et] = round(
                        total.get(fy, {}).get(et, 0.0) + v, 2)
        years = sorted(total, key=c.fy_start)
        schemes_out.append({
            "id": s["id"], "name": s["name"], "department": s["department"],
            "kind": s["kind"], "note": s.get("note", ""),
            "members": [{"id": m["id"], "name": m["name"],
                         "first": min(members.get(m["id"], {}) or [""], key=lambda y: c.fy_start(y) if y else 0),
                         "last": max(members.get(m["id"], {}) or [""], key=lambda y: c.fy_start(y) if y else 0)}
                        for m in s["members"]],
            "years": years,
            "total": {fy: total[fy] for fy in years},
            "by_member": {mid: {fy: members[mid][fy]
                                for fy in sorted(members[mid], key=c.fy_start)}
                          for mid in members},
            "source": {fy: dict(sources[fy]) for fy in sorted(sources, key=c.fy_start)
                       if fy in total},
        })

    c.write_json({
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "unit": "Rs crore, nominal",
            "source": ("Statements of Budget Estimates (Notes on Demands for "
                       "Grants), Expenditure Budget, editions 1998-99 to "
                       "2026-27, the education departments' demands."),
            "estimate_types": {"A": "actuals", "RE": "revised estimate",
                               "BE": "budget estimate"},
            "actuals_from": ("The SBEs print actuals only from the 2011-12 "
                             "edition (actuals for 2009-10). Earlier years "
                             "are budget and revised estimates only."),
            "value": ("A scheme's figure is the sum of every line the "
                      "statement prints for it -- gross budgetary support, "
                      "lines financed from the Prarambhik Shiksha Kosh or "
                      "other funds, and the North East provision -- net of "
                      "nothing but its own recoveries. Transfers into a fund "
                      "and the 'amount met from' lines that cancel them are "
                      "excluded, since they move money rather than spend it."),
            "family_rule": ("`total` adds a scheme's members; for a family "
                            "(Samagra Shiksha) that is the predecessors' sum "
                            "before the merger. Never add `total` to its own "
                            "members, and never add a scheme to the "
                            "department total it is part of."),
            "lineage": "data/reference/scheme_lineage.json",
        },
        "schemes": schemes_out,
    }, OUT_JSON)
    c.write_json(coverage, COVERAGE)
    for s in schemes_out:
        last = s["years"][-1] if s["years"] else ""
        print("  %-22s %s..%s  %s" % (s["id"], s["years"][0] if s["years"] else "",
                                      last, s["total"].get(last)))


if __name__ == "__main__":
    main()

"""Union actuals before 2015-16, by ministry and department.

    python scripts/parse_union_actuals.py           # fetch if needed, parse
    python scripts/parse_union_actuals.py --offline

The Demands for Grants of the Plan era print no actuals, so the Union series
had them only from 2015-16. They are not absent from the budget, though. The
Expenditure Budget, Volume I, opens with two summary statements that do
print them:

*   Statement 1, "Summary of Expenditure": total expenditure, revenue and
    capital, Plan and Non-Plan.
*   Statement 2, "Total Expenditure of Ministries / Departments": every
    ministry and department's expenditure, Plan, Non-Plan and Total, split
    revenue / capital -- for **actuals of the year before last**, and the
    revised and budget estimates.

Every edition from 1998-99 to 2016-17 publishes stat02.pdf, which gives
actuals for 1996-97 to 2014-15, one year per edition. With the demands'
own actuals from 2015-16 the Union series has actuals for every year from
1996-97. The detail is the department, not the major head: that is what
Statement 2 prints, and it is the level the brief allowed for this gap.

The figures are the actuals as known when the budget was presented, which
the documents mark "provisional" for most years. The audited figure is in the
Finance Accounts (CGA) and the Appropriation Accounts (CAG); it can differ
slightly. The provisional label is carried into the output.

Checks, every edition, any failure stops the write:

1.  Every line: revenue + capital = total, where both are printed.
2.  The departments of the central sector add up to the printed
    central-sector total.
3.  Central sector + central assistance for State Plans + Union
    Territories = the printed Grand Total.
4.  That Grand Total equals Statement 1's Total Expenditure for every column
    Statement 1 prints (it prints actuals only from the 2008-09 edition; for
    the actuals column of earlier editions checks 1-3 are what there is,
    plus the Budget at a Glance fixtures in validate.py).
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import sbe  # noqa: E402

FIRST, LAST = "1998-99", "2016-17"          # editions with stat02 and no DG actuals
OUT_CSV = c.PROCESSED / "union_stat2.csv"
OUT_JSON = c.ROOT / "data" / "union_actuals.json"
TOL = 1.0
JUNK = re.compile(r"^#+$|^[*@]+$")
EST = re.compile(r"(?i)^(actuals?|revised|budget)")
CS_HEAD = re.compile(r"(?i)^I\.\s*CENTRAL SECTOR$")
FOOTNOTE = re.compile(r"(?i)^(notes?\s*:|\*|website|statement|total expenditure of"
                      r"|nic\s*/\s*dea$)"
                      r"|actuals? (for|of) .*\b(are|is|include)|inclusive of|provisional")

# Editions left out whole, each because the source document is defective,
# not the parser. The script confirms each one still fails its checks, so an
# exclusion cannot outlive its reason.
EXCLUDED = {
    "1998-99": ("stat02.pdf is truncated: pages 1, 4 and 6 carry about 230 "
                "characters each against about 1,900 on a full page, so most "
                "departments on them are not in the file. The departments "
                "that remain add up to Rs 62,867 crore of a printed central "
                "sector of Rs 1,75,940 crore. 1996-97 actuals are therefore "
                "not available by department."),
}

# Printed totals that disagree with the lines under them, where an
# independent document says the printed total is the right one. The
# department lines are published as printed; the gap is recorded.
KNOWN_GAPS = {
    ("2000-01", "1998-99", "A"): (53.62, (
        "The 1998-99 actuals of the departments in the 2000-01 Statement 2 "
        "add up to Rs 53.62 crore more than its printed central-sector total "
        "(2,48,387.05 against 2,48,333.43), though every department's revenue "
        "and capital add up to its own total. Budget at a Glance 2000-01 "
        "prints total expenditure of Rs 2,79,366 crore, which agrees with the "
        "printed total (2,79,365.30), so one department line is misprinted. "
        "The document does not say which.")),
}


def raw_dir(fy):
    return c.RAW / "union" / fy / "stat"


def fetch_all():
    for ed in sbe.editions():
        fy = ed["fiscal_year"]
        if not c.fy_start(FIRST) <= c.fy_start(fy) <= c.fy_start(LAST):
            continue
        for name in ("stat01.pdf", "stat02.pdf"):
            dest = raw_dir(fy) / name
            if dest.exists():
                continue
            url = ed["eb_base"] + name
            if not sbe.probe(url):
                raise SystemExit("%s: %s does not serve a PDF" % (fy, url))
            c.fetch(url, dest, pause=0.2)


# --------------------------------------------------------------------------- #
# Statement 2
# --------------------------------------------------------------------------- #


def header(rows, edition):
    """-> (row index, [(fy, etype)], anchors of every sub-column) or None."""
    import parse_union_pdf as P
    for j, row in enumerate(rows[:14]):
        sub = [w for w in row if re.match(r"(?i)^(non\s*-?\s*plan|plan|total)$",
                                          w["text"])]
        if sum(1 for w in sub if w["text"].lower() == "total") < 3 \
                or len(sub) % 3:
            continue
        anchors = [P.centre(w) for w in sub]
        groups = [sum(anchors[g:g + 3]) / 3 for g in range(0, len(anchors), 3)]
        words = [[] for _ in groups]
        years = [[] for _ in groups]
        for k in range(max(0, j - 4), j):
            for w in rows[k]:
                g = P.nearest(P.centre(w), groups)
                if EST.match(w["text"]):
                    words[g].append(w["text"].lower())
                m = re.search(r"((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})", w["text"])
                if m:
                    years[g].append(c.fy_normalise(m.group(1) + "-" + m.group(2)))
        cols = []
        for g in range(len(groups)):
            if not words[g]:
                return None
            w = words[g][0]
            if w.startswith("actual"):
                col = (c.fy_shift(edition, -2), "A")
            elif w.startswith("revised"):
                col = (c.fy_shift(edition, -1), "RE")
            else:
                col = (edition if g == len(groups) - 1
                       else c.fy_shift(edition, -1), "BE")
            if years[g] and years[g][0] != col[0]:
                raise ValueError("header year %s under %r, expected %s"
                                 % (years[g][0], w, col[0]))
            cols.append(col)
        return j, cols, anchors
    return None


def read_stat2(path, edition):
    import pdfplumber
    import parse_union_pdf as P
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows = P.page_lines(page)
            h = header(rows, edition)
            if h is None:
                continue
            j, cols, anchors = h
            pages.append((rows, j, cols, list(range(2, len(anchors), 3)), anchors))
    if not pages:
        raise ValueError("no Statement 2 header")
    cols = pages[0][2]
    if any(p[2] != cols for p in pages):
        raise ValueError("pages disagree on columns")
    margin = min(pages[0][4]) - 45.0
    clustered = [([[w for w in r if w["x1"] >= margin or not P.is_amount(w["text"])]
                   for r in rows], h, cl, ix, an) for rows, h, cl, ix, an in pages]
    edges = P.money_columns(clustered, pages[0][4])
    if edges is None:
        raise ValueError("could not place the money columns")
    live = [i for i, e in enumerate(edges) if e is not None]
    index = pages[0][3]
    lines, pending = [], []
    for rows, j, _, _, _ in pages:
        for row in rows[j + 1:]:
            amounts, words = {}, []
            for w in row:
                if P.is_amount(w["text"]) and live:
                    col = live[P.nearest(w["x1"], [edges[i] for i in live])]
                    tol = P.NIL_TOL if P.NIL.match(w["text"]) else P.EDGE_TOL
                    if abs(w["x1"] - edges[col]) <= tol:
                        v = c.num(w["text"])
                        if v is not None and col not in amounts:
                            amounts[col] = v
                        continue
                if JUNK.match(w["text"]):
                    continue
                words.append(w["text"])
            label = c.squeeze(" ".join(words))
            values = {cols[n]: amounts[i] for n, i in enumerate(index) if i in amounts}
            if not values:
                # Footnotes, page furniture: never the head of a name. Left
                # in, '* Actuals for 1998-99 are inclusive of Secondary &
                # Higher Education.' becomes the first words of Company
                # Affairs, the next department printed.
                if not label or sbe.FOOTER.match(label) or FOOTNOTE.search(label):
                    continue
                if CS_HEAD.match(label):
                    lines.append(("cs_head", label, {}))
                    pending = []
                    continue
                pending.append(label)
                continue
            if pending and label.lower() not in ("revenue", "capital"):
                # A name printed before its figures: 'Agricultural Research
                # and' / 'Education 1629.97 ...'.
                label = c.squeeze(" ".join(pending) + " " + label)
            elif pending and lines and lines[-1][0] == "line":
                # A name whose tail is printed after its figures, before its
                # Revenue row: 'Agriculture, Cooperation and Farmers 4766.09
                # ...' / 'Welfare' (2016-17).
                kind, prev, vals = lines[-1]
                lines[-1] = (kind, c.squeeze(prev + " " + " ".join(pending)), vals)
            pending = []
            lines.append(("line", label, values))
    return cols, lines


def structure(cols, lines, edition=""):
    """-> dict with central-sector departments, the three totals, problems."""
    out = {"departments": [], "problems": [], "revcap": 0, "edition": edition,
           "gaps": []}
    ents = []                     # [label, total, revenue, capital]
    for kind, label, values in lines:
        if kind == "cs_head":
            ents.append(["__CS_HEAD__", {}, {}, {}])
            continue
        low = label.lower()
        # The Department of Revenue is printed as plain 'Revenue', exactly
        # like the revenue sub-row of every department. It is the department
        # when the line above already has both its sub-rows; read as a
        # sub-row it overwrites the Department of Expenditure's revenue and
        # drops the Department of Revenue from the central sector.
        if low == "revenue" and ents and not (ents[-1][2] and ents[-1][3])                 and ents[-1][0] != "__CS_HEAD__":
            ents[-1][2] = values
        elif low == "capital" and ents:
            ents[-1][3] = values
        else:
            ents.append([label, values, {}, {}])
    # A wrapped name whose first printed line carries only nil markers
    # ('The President, Parliament, Union Public Service' / '... ... ...',
    # 2000-01) arrives as an entity of zeros with no sub-rows; it is the head
    # of the next one.
    merged = []
    for e in ents:
        prev = merged[-1] if merged else None
        if (prev and prev[0] != "__CS_HEAD__" and not prev[2] and not prev[3]
                and prev[1] and all(v == 0 for v in prev[1].values())
                and e[0].lower() not in ("revenue", "capital")
                and not re.match(r"(?i)^(grand|total|[ivx]+\.)", e[0])):
            merged.pop()
            e = [c.squeeze(prev[0] + " " + e[0])] + e[1:]
        merged.append(e)
    ents = merged

    def check_revcap(label, tot, rev, cap):
        if not rev or not cap:
            return
        for col in cols:
            if col in tot and (col in rev or col in cap):
                out["revcap"] += 1
                if abs(rev.get(col, 0.0) + cap.get(col, 0.0) - tot[col]) > TOL:
                    out["problems"].append(
                        "%r %s %s: revenue %.2f + capital %.2f != total %.2f"
                        % (label, col[0], col[1], rev.get(col, 0.0),
                           cap.get(col, 0.0), tot[col]))

    def find(pattern, start=0):
        for k in range(start, len(ents)):
            if re.search(pattern, ents[k][0], re.I):
                return k
        return None

    gt = find(r"grand\s*total")
    if gt is None:
        out["problems"].append("no GRAND TOTAL")
        return out
    # The central sector: either a heading 'I. CENTRAL SECTOR' printed with
    # its total (2014-15 on) or without (2008-09 to 2013-14), closed by a
    # total line; or (to 2007-08) a list closed by 'Central Ministries/
    # Departments Total'.
    head = find(r"^__CS_HEAD__$")
    top = find(r"^I\.\s*CENTRAL SECTOR")
    close = find(r"central (sector|ministries\s*/?\s*departments)\s*-?\s*total")
    if top is not None and ents[top][1]:
        cs_total, first = ents[top][1], top + 1
        nxt = find(r"^II\.", first)
        last = nxt if nxt is not None else gt
        if close is not None and close < last:
            last = close
    elif close is not None:
        cs_total, first, last = ents[close][1], (head + 1 if head is not None else 0), close
    else:
        out["problems"].append("no central-sector total")
        return out
    depts = [e for e in ents[first:last] if e[0] != "__CS_HEAD__"]
    out["departments"] = depts
    # Revenue + capital = total is checked on what is published: the
    # departments and the Grand Total. The aggregates in between are checked
    # by adding up their parts instead, which matters because the documents
    # misprint them: the 2011-12 to 2014-15 editions print the Union
    # Territories' revised capital as 4454.32 over parts of 72.00 and 722.53.
    for e in depts + [ents[gt]]:
        check_revcap(*e)
    for col in cols:
        s = sum(e[1].get(col, 0.0) for e in depts)
        gap = KNOWN_GAPS.get((edition,) + col)
        if gap and abs(s - cs_total.get(col, 0.0) - gap[0]) <= 0.01:
            out["gaps"].append(gap[1])
            continue
        if abs(s - cs_total.get(col, 0.0)) > TOL:
            out["problems"].append("%s %s: departments sum to %.2f, central "
                                   "sector total %.2f" % (col[0], col[1], s,
                                                          cs_total.get(col, 0.0)))
    # State Plans and UTs: the first line naming each after the central sector.
    after = last if re.match(r"^II\.", ents[last][0]) else last + 1
    sp = find(r"state plans.*total|total.*\(a\s*\+\s*b\)|^II\.?\s*state plans", after)
    ut = find(r"^(III\.\s*)?union territories(\s*\(a\s*\+\s*b\))?$", after)
    if ut is None:
        ut = find(r"union territories\s*\(a\s*\+\s*b\)", after)
    parts = {"central_sector": cs_total,
             "state_plans": ents[sp][1] if sp is not None else {},
             "union_territories": ents[ut][1] if ut is not None else {}}
    if sp is None or ut is None:
        out["problems"].append("could not find the State Plans (%s) or UT (%s) "
                               "total" % (sp, ut))
    # Central assistance for State Plans, by the ministry it passes through.
    # Up to the 2015-16 edition this is a handful of channels (Finance for
    # normal central assistance, Agriculture, Panchayati Raj ...). The
    # 2016-17 edition restates it ministry by ministry -- 'm. School
    # Education and Literacy 39695.04' -- because the centrally sponsored
    # schemes were moved out of the ministries' own lines that year. A
    # department's comparable figure is therefore its central-sector line
    # plus its line here. Aggregates ('A. STATE PLANS', 'B. DONER (gg+hh)',
    # 'State Plans', 'NEC Plan') are skipped and the items must add up to
    # the printed State Plans total.
    out["state_plan_items"] = []
    if sp is not None and ut is not None:
        # Case matters for the first alternative: 'A. STATE PLANS' is an
        # aggregate, 'a. Agriculture ...' is an item.
        agg = re.compile(r"^[AB]\.\s|(?i:^state plans$|^nec plan$|doner|\(.*\+.*\)"
                         r"|^total\b|^II\.)")
        items = [e for e in ents[sp + 1:ut] if not agg.search(e[0])]
        for col in cols:
            s = sum(e[1].get(col, 0.0) for e in items)
            if abs(s - ents[sp][1].get(col, 0.0)) > TOL:
                out["problems"].append(
                    "%s %s: State Plan items sum to %.2f, State Plans total %.2f"
                    % (col[0], col[1], s, ents[sp][1].get(col, 0.0)))
        out["state_plan_items"] = [
            [re.sub(r"^[a-z]{1,2}\.\s*", "", e[0])] + e[1:] for e in items]
    grand = ents[gt][1]
    for col in cols:
        s = sum(p.get(col, 0.0) for p in parts.values())
        if abs(s - grand.get(col, 0.0)) > TOL:
            out["problems"].append(
                "%s %s: central sector + State Plans + UTs = %.2f, Grand Total "
                "%.2f" % (col[0], col[1], s, grand.get(col, 0.0)))
    out["parts"] = parts
    out["grand_total"] = grand
    return out


def provisional_note(path, fy):
    """True if the statement's own footnote calls this year's actuals provisional."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = " ".join(p.extract_text() or "" for p in pdf.pages)
    start = str(c.fy_start(fy))
    return bool(re.search(r"(?i)actuals?\s*(for|of)\s*" + start + r"[^.]{0,30}"
                          r"(are|is)\s*provisional", text))


# --------------------------------------------------------------------------- #
# Statement 1
# --------------------------------------------------------------------------- #


def read_stat1(path, edition):
    """{(fy, etype): total expenditure} for the columns Statement 1 prints."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages[:1])
    heads = re.findall(r"(?i)(actuals?|budget|revised)", text.split("TOTAL")[0])
    m = re.search(r"TOTAL\s*EXPENDITURE\s*\(2\s*\+\s*3\)(.*?)(?:\n\s*2\.?\s*Non|\n2\s)",
                  text, re.S)
    if not m:
        raise ValueError("no TOTAL EXPENDITURE line")
    nums = [c.num(x) for x in re.findall(r"-?\d+\.\d{2}|\.\.\.", m.group(1))]
    if len(nums) % 3 or len(nums) // 3 not in (3, 4):
        raise ValueError("TOTAL EXPENDITURE line has %d figures" % len(nums))
    groups = len(nums) // 3
    shape = {3: ((-1, "BE"), (-1, "RE"), (0, "BE")),
             4: ((-2, "A"), (-1, "BE"), (-1, "RE"), (0, "BE"))}[groups]
    words = [h.lower() for h in heads][-groups:]
    for (d, et), w in zip(shape, words):
        want = {"A": "actual", "RE": "revised", "BE": "budget"}[et]
        if not w.startswith(want):
            raise ValueError("Statement 1 header %r where %s expected" % (w, et))
    return {(c.fy_shift(edition, d), et): nums[3 * g + 2]
            for g, (d, et) in enumerate(shape)}


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if not args.offline:
        fetch_all()

    eds = [e for e in sbe.editions()
           if c.fy_start(FIRST) <= c.fy_start(e["fiscal_year"]) <= c.fy_start(LAST)]
    problems, rows, by_year, excluded = [], [], {}, {}
    stats = collections.Counter()
    for ed in eds:
        fy = ed["fiscal_year"]
        url2 = ed["eb_base"] + "stat02.pdf"
        try:
            cols, lines = read_stat2(raw_dir(fy) / "stat02.pdf", fy)
        except ValueError as exc:
            problems.append("%s stat02: %s" % (fy, exc))
            continue
        s = structure(cols, lines, fy)
        if fy in EXCLUDED:
            if not s["problems"]:
                problems.append("%s is excluded as defective but now passes "
                                "every check; remove it from EXCLUDED" % fy)
            excluded[fy] = EXCLUDED[fy]
            print("  %s  excluded: %s..." % (fy, EXCLUDED[fy][:60]))
            continue
        problems += ["%s stat02: %s" % (fy, p) for p in s["problems"]]
        stats["revcap"] += s["revcap"]
        try:
            st1 = read_stat1(raw_dir(fy) / "stat01.pdf", fy)
        except ValueError as exc:
            problems.append("%s stat01: %s" % (fy, exc))
            st1 = {}
        for col, v in st1.items():
            if col not in cols:
                continue      # Statement 1 of the older editions starts a year earlier
            stats["stat1"] += 1
            g = s.get("grand_total", {}).get(col)
            if g is None or abs(g - v) > TOL:
                problems.append("%s: Statement 1 total %s %s = %.2f, Statement 2 "
                                "Grand Total %s" % (fy, col[0], col[1], v, g))
        if s["problems"]:
            continue
        actual = [col for col in cols if col[1] == "A"]
        if len(actual) != 1:
            problems.append("%s: %d actuals columns" % (fy, len(actual)))
            continue
        a = actual[0]
        provisional = provisional_note(raw_dir(fy) / "stat02.pdf", a[0])
        depts = {}
        for section, entries in (("central_sector", s["departments"]),
                                 ("state_plans", s["state_plan_items"])):
            for label, tot, rev, cap in entries:
                for col, v in tot.items():
                    rows.append(c.Row(
                        fiscal_year=col[0], govt="union", estimate_type=col[1],
                        source_edition="ExpBudget " + fy, definition="whole",
                        ministry_or_dept=label, account="stat2_" + section,
                        amount_cr=v, source_url=url2,
                        source_page="stat02!" + section))
                    for acc, d in (("stat2_revenue", rev), ("stat2_capital", cap)):
                        if col in d and section == "central_sector":
                            rows.append(c.Row(
                                fiscal_year=col[0], govt="union",
                                estimate_type=col[1],
                                source_edition="ExpBudget " + fy,
                                definition="whole", ministry_or_dept=label,
                                account=acc, amount_cr=d[col], source_url=url2,
                                source_page="stat02!" + section))
                if a not in tot:
                    continue
                key = c.dept_key(label)
                d = depts.setdefault(key, {"name": label, "key": key,
                                           "central_sector": None,
                                           "state_plans": None,
                                           "revenue": None, "capital": None})
                if section == "central_sector":
                    d["name"] = label
                    d["central_sector"] = round(tot[a], 2)
                    d["revenue"] = round(rev[a], 2) if a in rev else None
                    d["capital"] = round(cap[a], 2) if a in cap else None
                else:
                    d["state_plans"] = round((d["state_plans"] or 0.0) + tot[a], 2)
        for d in depts.values():
            d["total"] = round((d["central_sector"] or 0.0)
                               + (d["state_plans"] or 0.0), 2)
        depts = list(depts.values())
        for part, d in list(s["parts"].items()) + [("grand_total", s["grand_total"])]:
            for col, v in d.items():
                rows.append(c.Row(
                    fiscal_year=col[0], govt="union", estimate_type=col[1],
                    source_edition="ExpBudget " + fy, definition="whole",
                    ministry_or_dept=part.replace("_", " "),
                    account="stat2_" + part, amount_cr=v, source_url=url2,
                    source_page="stat02!" + part))
        by_year[a[0]] = {
            "edition": "ExpBudget " + fy,
            "source_url": url2,
            "provisional": provisional,
            "total_expenditure": round(s["grand_total"][a], 2),
            "central_sector": round(s["parts"]["central_sector"][a], 2),
            "state_plans": round(s["parts"]["state_plans"].get(a, 0.0), 2),
            "union_territories": round(s["parts"]["union_territories"].get(a, 0.0), 2),
            "statement_1_checked": a in st1,
            "known_gaps": s["gaps"],
            "departments": sorted(depts, key=lambda d: -d["total"]),
            "state_plans_by_ministry": bool(len(s["state_plan_items"]) > 12),
        }
        print("  %s  actuals %s: %d departments, total %.2f%s"
              % (fy, a[0], len(depts), s["grand_total"][a],
                 " (provisional)" if provisional else ""))

    print("checked %d revenue+capital=total lines, %d Statement 1 totals"
          % (stats["revcap"], stats["stat1"]))
    if problems:
        print("\nrefusing to write:")
        for p in problems[:40]:
            print("  -", p)
        raise SystemExit(1)

    c.write_long_table(rows, OUT_CSV)
    years = sorted(by_year, key=c.fy_start)
    c.write_json({
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "unit": "Rs crore, nominal",
            "estimate_type": "A (actuals)",
            "source": ("Expenditure Budget Vol. I, Statement 2 'Total "
                       "Expenditure of Ministries / Departments' (with "
                       "Statement 1 'Summary of Expenditure' as a check), "
                       "editions 1998-99 to 2016-17. Each edition gives the "
                       "actuals of the year before last."),
            "years": years,
            "level": ("Department or ministry as Statement 2 prints it, "
                      "Plan plus Non-Plan; revenue and capital where "
                      "printed. Not major heads."),
            "provisional": ("Actuals as known at budget time. Most editions "
                            "mark them provisional; the audited figures are "
                            "in the Union Government Finance Accounts and can "
                            "differ slightly."),
            "total_definition": ("total_expenditure is Statement 2's Grand "
                                 "Total = Statement 1's Total Expenditure = "
                                 "Budget at a Glance's total expenditure: "
                                 "central sector + central assistance for "
                                 "State Plans + Union Territories."),
            "joins": ("From 2015-16 the Union's actuals are in data/union.json "
                      "from the Demands for Grants. Departments here are keyed "
                      "with common.dept_key, the same key union.json uses, "
                      "but departments were created, split and renamed over "
                      "these years; a key that stops is not a department "
                      "that stopped spending."),
        },
        "years": {y: by_year[y] for y in years},
        "excluded_editions": excluded,
    }, OUT_JSON)


if __name__ == "__main__":
    main()

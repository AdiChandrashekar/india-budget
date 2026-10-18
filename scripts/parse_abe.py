"""The Analysis of Budgeted Expenditure on Education: sub-sectors, and the
Centre and the states together.

    python scripts/fetch_abe.py     # first
    python scripts/parse_abe.py

Writes data/processed/abe_states.csv (long table) and data/abe.json.

Two things only this publication has, and both are read here:

1.  **A legitimate Centre-plus-states total.** Adding the Union's education
    budget to the states' double counts the grants the Union gives the
    states for education, which the states spend and book again. The ABE
    counts each rupee once, by the government that spends it. Its Table 4
    ("Public expenditure on education as percentage of GDP from 2000-01")
    gives the series in one vintage, Centre, States/UTs and total, for the
    education departments alone and for education and other departments,
    with the GDP it used. Taken from the newest edition only.
2.  **The state sub-sector split.** Statements 4-10 of the modern editions
    (7-13 of the older ones) give each state's revenue expenditure on
    elementary, secondary, adult, university & higher, technical, general
    and language education, by the education departments.

Layouts. Up to the 2014-17 edition a sector statement prints each year as
Plan / Non-Plan / Total / % of education; from 2016-19 as value / % only.
Both are read by placing every figure in a column by its right edge, the
columns found by clustering all the figures on the page -- not by counting
figures in a row, because a row prints only the figures it has.

The text layer of the modern editions draws a space glyph on top of the first
digit of most numbers, so a plain text extraction gives '9 ,57,27,800' and
'1 4,56,78,657'. Space glyphs are dropped before words are formed, and the
numbers come back whole.

Checks, any failure stops the write:

*   in every sector statement: the state rows add up to TOTAL STATES, the UT
    rows to TOTAL U.T., and the two to TOTAL (STATE & UTs);
*   in the old layout, Plan + Non-Plan = Total in every cell;
*   in Table 4: States + Centre = total, and each % of GDP is the total over
    the GDP column it prints;
*   Table 4's 2010-11 total equals the 2010-13 edition's own figure, a
    cross-edition fixture taken from a different table of a different year.
"""

from __future__ import annotations

import collections
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

RAW = c.RAW / "abe"
REF = c.REFERENCE / "abe_editions.json"
OUT_CSV = c.PROCESSED / "abe_states.csv"
OUT_JSON = c.ROOT / "data" / "abe.json"

SECTORS = [
    ("elementary", r"ELEMENTARY"),
    ("secondary", r"SECONDARY"),
    ("adult", r"ADULT"),
    ("university", r"UNIVERSITY"),
    ("technical", r"TECHNICAL"),
    ("general", r"GENERAL EDUCATION"),
    ("language", r"LANGUAGE"),
]

# ABE spellings -> state codes. The codes are data/reference/states.json's
# where that file has the entity, ISO 3166-2:IN otherwise.
NAMES = {
    "ANDHRAPRADESH": "AP", "ARUNACHALPRADESH": "AR", "ASSAM": "AS", "BIHAR": "BR",
    "CHHATTISGARH": "CT", "GOA": "GA", "GUJARAT": "GJ", "HARYANA": "HR",
    "HIMACHALPRADESH": "HP", "JAMMUANDKASHMIR": "JK", "JAMMUANDKASHMIRUT": "JK",
    "JHARKHAND": "JH", "KARNATAKA": "KA", "KERALA": "KL", "MADHYAPRADESH": "MP",
    "MAHARASHTRA": "MH", "MAHARAHSTRA": "MH", "MANIPUR": "MN", "MEGHALAYA": "ML",
    "MIZORAM": "MZ", "NAGALAND": "NL", "ODISHA": "OR", "ORISSA": "OR",
    "PUNJAB": "PB", "RAJASTHAN": "RJ", "SIKKIM": "SK", "TAMILNADU": "TN",
    "TELANGANA": "TG", "TRIPURA": "TR", "UTTARPRADESH": "UP", "UTTARAKHAND": "UT",
    "UTTARANCHAL": "UT", "WESTBENGAL": "WB",
    "ANDNISLANDS": "AN", "ANISLANDS": "AN", "AANDNISLANDS": "AN", "AANDNISLAND": "AN",
    # Spelt this way in the 2014-17 edition.
    "GUJRAT": "GJ", "MEHGLAYA": "ML", "PUDUCHEERY": "PY", "ANDAMANANDNICOBARISLANDS": "AN",
    "ANDAMANNICOBARISLANDS": "AN", "CHANDIGARH": "CH",
    "DADRAANDNAGARHAVELI": "DN", "DADRANAGARHAVELI": "DN",
    "DADRAANDNAGARHAVELIANDDAMANANDDIU": "DH", "DAMANANDDIU": "DD",
    "DAMANDIU": "DD", "DELHI": "DL", "NCTDELHI": "DL", "NCTOFDELHI": "DL",
    "LADAKH": "LA", "LAKSHADWEEP": "LD", "PUDUCHERRY": "PY", "PONDICHERRY": "PY",
}
UTS = {"AN", "CH", "DN", "DH", "DD", "DL", "LA", "LD", "PY", "JK_UT"}
TOTAL_ROWS = {
    "TOTALSTATES": "total_states", "TOTALUT": "total_uts", "TOTALUTS": "total_uts",
    "TOTALSTATEANDUTS": "total", "TOTALSTATESANDUTS": "total",
    "TOTALSTATEUTS": "total", "TOTALSTATESUTS": "total",
}
NUM = re.compile(r"^-?\(?\d[\d,]*(\.\d+)?\)?%?$")
# Sector pages left out, each because the document is defective, not the
# parser. read_edition confirms each still fails its identities, so an entry
# cannot outlive its reason.
DEFECTIVE = {
    ("2017-18", sector): ("the text layer of this page superimposes two tables: "
                          "two state lists share the same baselines ('13 KERALA "
                          "... 15 MAHARAHSTRA') and figures run together into "
                          "17-digit strings, so no row can be assigned")
    for sector in ("secondary", "adult", "university", "language")
}
TOL_K = 2.0e3          # Rs thousand; the statements round to the thousand-rupee
TOL_K_PER_ROW = 1.0e3


def norm(label: str) -> str:
    s = label.upper().replace("&", " AND ")
    return re.sub(r"[^A-Z]", "", s)


CID = re.compile(r"\(cid:(\d+)\)")
# The 2016-19 edition sets its state figures in a font with no Unicode map,
# so they extract as glyph ids: (cid:882) to (cid:891) are 0 to 9 and
# (cid:484) the decimal point. The mapping is checked, not trusted: the total
# rows are in an ordinary font, and the decoded state rows must add up to them.
CID_DIGITS = {str(882 + d): str(d) for d in range(10)}
CID_DIGITS["484"] = "."


def words(page):
    """Words with the stray space glyphs removed (see the module note), glyph-id
    digits decoded and marked."""
    pg = page.filter(lambda o: not (o.get("object_type") == "char"
                                    and o.get("text", "").isspace()))
    out = []
    for w in pg.extract_words(x_tolerance=1.5, use_text_flow=False):
        if "(cid:" in w["text"]:
            text = CID.sub(lambda m: CID_DIGITS.get(m.group(1), "?"), w["text"])
            w = dict(w, text=text, cid=True)
        out.append(w)
    return out


def realign(ws):
    """Move displaced figures back onto their own rows.

    In the 2016-19 and 2017-20 editions the state figures are reported about
    18 points below the names they belong to -- more than a row lower --
    while the total rows' figures sit on their own baselines. Grouped as
    printed, every state's figures land on the next state's name, or on a
    row of their own. The page says when this has happened: the first
    state's row has no figures on it. The offset is then measured from that
    row to the first figure below it, and every figure not already on a
    total row's baseline is moved up by it. The identities decide whether
    that was right.
    """
    def is_fig(w):
        return w["x0"] > 150 and (NUM.match(w["text"]) or w["text"] == "-")

    labels = [w for w in ws if not is_fig(w)]
    figs = [w for w in ws if is_fig(w)]
    if not figs:
        return ws
    first_state, totals = None, []
    for r in rows_of(labels):
        label = re.sub(r"^\d+\s*", "", " ".join(w["text"] for w in r))
        if first_state is None and NAMES.get(norm(label)):
            first_state = r[0]["bottom"]
        if TOTAL_ROWS.get(norm(label)):
            totals.append(r[0]["bottom"])
    if first_state is None:
        return ws
    if any(abs(w["bottom"] - first_state) <= 2.5 for w in figs):
        return ws                          # figures are on their own rows
    below = [w["bottom"] for w in figs if w["bottom"] > first_state + 2.5]
    if not below:
        return ws
    delta = min(below) - first_state
    if delta > 30:
        return ws                          # too far to be the same row
    out = list(labels)
    for w in figs:
        if any(abs(w["bottom"] - t) <= 2.5 for t in totals):
            out.append(w)
        else:
            out.append(dict(w, top=w["top"] - delta, bottom=w["bottom"] - delta))
    return out


def rows_of(ws, tol=4.0):
    rows = []
    for w in sorted(ws, key=lambda w: (w["bottom"], w["x0"])):
        for r in rows:
            if abs(r[0]["bottom"] - w["bottom"]) <= tol:
                r.append(w)
                break
        else:
            rows.append([w])
    for r in rows:
        r.sort(key=lambda w: w["x0"])
    rows.sort(key=lambda r: r[0]["bottom"])
    return rows


def value(text: str):
    t = text.strip()
    if t in ("-", "--"):
        return None
    t = t.replace(",", "").replace("%", "")
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1]
    try:
        return float(t)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Sector statements
# --------------------------------------------------------------------------- #

TITLE = re.compile(r"(?:PLAN\s*&\s*NON-PLAN\s+)?BUDGETED\s+EXPENDITURE\s+ON\s+"
                   r"(ELEMENTARY|SECONDARY|ADULT|UNIVERSITY|TECHNICAL|GENERAL|LANGUAGE)")


def is_sector_total(text: str):
    """The sector of a statement's *total* page, or None (sub-heads, other)."""
    head = " ".join(text.upper().split())[:500]
    m = TITLE.search(head)
    if not m or "STATEMENT" not in head:
        return None
    if re.search(r"SUB-HEAD|SUBHEAD", head):
        return None
    sn = re.search(r"STATEMENT\s*NO\.?\s*\(?\s*(\d+(?:\.\d+)?)", head)
    if sn and "." in sn.group(1):
        return None                      # 4.1, 4.2 ... are sub-heads
    if not re.search(r"TOTAL\s+EXPENDITURE|PROGRAM\s*:\s*TOTAL", head):
        return None
    for key, pat in SECTORS:
        if re.match(pat, m.group(1)):
            return key
    return None


def columns(rows, first_row):
    """Right edges of the money columns on a page, left to right."""
    xs = sorted(w["x1"] for r in rows[first_row:] for w in r if NUM.match(w["text"])
                and w["x0"] > 150)
    if not xs:
        return []
    groups, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] <= 9.0:
            cur.append(x)
        else:
            groups.append(cur)
            cur = [x]
    groups.append(cur)
    big = max(len(g) for g in groups)
    return [sum(g) / len(g) for g in groups if len(g) >= max(3, big // 6)]


def read_sector_page(page, edition):
    ws = realign(words(page))
    rows = rows_of(ws)
    text = " ".join(w["text"] for w in ws)
    first = next((k for k, r in enumerate(rows)
                  if r and NAMES.get(norm(" ".join(w["text"] for w in r
                                                   if not NUM.match(w["text"])))) ), None)
    if first is None:
        raise ValueError("no state rows")
    cols = columns(rows, first)
    n = len(cols)
    if n == 12:
        layout = "plan_nonplan"
    elif n == 4:
        layout = "plan_nonplan_1"     # one year per page (2014-17)
    elif n == 6:
        layout = "value_pct"
    else:
        raise ValueError("%d money columns" % n)
    parsed = []
    for r in rows[first:]:
        lab_words = [w for w in r if not (NUM.match(w["text"]) and w["x0"] > 150)
                     and w["text"] not in ("-",)]
        label = re.sub(r"^\d+\s*", "", " ".join(w["text"] for w in lab_words))
        cells = [None] * n
        has = False
        for w in r:
            if w["x0"] <= 150 or not (NUM.match(w["text"]) or w["text"] == "-"):
                continue
            j = min(range(n), key=lambda i: abs(cols[i] - w["x1"]))
            if abs(cols[j] - w["x1"]) > 12:
                continue
            cells[j] = value(w["text"])
            has = True
        parsed.append([label, cells, has])
    # Figures printed as rows of their own, a line below their names (the
    # 2017-20 edition): every named row is empty and every figure row is
    # nameless. Paired in order, and only when the counts agree exactly --
    # otherwise the page is left as it is and the identities reject it.
    named_empty = [k for k, (lab, _, has) in enumerate(parsed)
                   if not has and (NAMES.get(norm(lab)) or TOTAL_ROWS.get(norm(lab)))]
    orphans = [k for k, (lab, _, has) in enumerate(parsed) if has and not lab.strip()]
    if len(orphans) >= 10 and len(orphans) == len(named_empty) and all(
            o > nm for o, nm in zip(orphans, named_empty)):
        for nm, o in zip(named_empty, orphans):
            parsed[nm][1], parsed[nm][2] = parsed[o][1], True
            parsed[o][2] = False
    # A name set over two or three lines, its figures on one of them:
    # 'DADRA & NAGAR HAVELI &' / '31 15,57,475 ...' / 'DAMAN & DIU'.
    def code_of(label):
        k = norm(label)
        return NAMES.get(k) or TOTAL_ROWS.get(k)

    out, order = {}, []
    for k, (label, cells, has) in enumerate(parsed):
        if not has:
            continue
        code = code_of(label)
        if code is None:
            prev = parsed[k - 1][0] if k and not parsed[k - 1][2] else ""
            nxt = parsed[k + 1][0] if k + 1 < len(parsed) and not parsed[k + 1][2] else ""
            for cand in (prev + " " + label, label + " " + nxt,
                         prev + " " + label + " " + nxt, prev, nxt):
                code = code_of(cand)
                if code:
                    break
        if code is None:
            continue
        if code in out and code in NAMES.values():
            # Printed twice: Jammu and Kashmir as a state (to 2018-19) and
            # again as a UT (from 2019-20) in the 2018-21 edition. Kept apart
            # here, for the state and UT sums, and merged on output.
            code = code + "_2"
        out[code] = cells
        order.append(code)
    # States and UTs are told apart by where they are printed -- before
    # TOTAL STATES, or between it and TOTAL U.T. -- because the ABE moves
    # entities between the two: Jammu and Kashmir is a state until 2019-20
    # and a UT after, and Delhi and Puducherry are printed with the UTs.
    group, seen = {}, "state"
    for code in order:
        if code == "total_states":
            seen = "ut"
            continue
        if code in ("total_uts", "total"):
            seen = "after"
            continue
        group[code] = seen
    return layout, out, group


def sector_values(layout, cells, problems, where):
    """Totals in Rs thousand, one per year group the page prints, checking
    Plan + Non-Plan = Total where the layout has them."""
    groups = 1 if layout == "plan_nonplan_1" else 3
    vals = []
    for g in range(groups):
        if layout.startswith("plan_nonplan"):
            p, np_, t = cells[4 * g:4 * g + 3]
            if t is not None and p is not None and np_ is not None:
                if abs(p + np_ - t) > TOL_K_PER_ROW:
                    problems.append("%s group %d: plan %.0f + non-plan %.0f != %.0f"
                                    % (where, g, p, np_, t))
            vals.append(t)
        else:
            vals.append(cells[2 * g])
    return vals


def read_edition(path, ed, problems):
    """Every sector's totals for the edition's three years.

    A page prints either all three years (most editions) or one (2014-17,
    which sets each year of each statement on a page of its own). Either way
    the figures are filed by the year's position in the edition, and the
    state, UT and all-India identities are checked page by page.
    """
    import pdfplumber
    first = ed["first"]
    years = [(first, "A"), (c.fy_shift(first, 1), "RE"), (c.fy_shift(first, 2), "BE")]
    found, excluded = {}, {}
    done = set()
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            # Only the head of the page decides what it is; reading the whole
            # page's text for each of 1,700 pages is what made this slow.
            x0, y0, x1, y1 = page.bbox      # not always at the origin (2014-17)
            top = page.crop((x0, y0, x1, min(y1, y0 + 150)))
            text = top.extract_text() or ""
            sector = is_sector_total(text)
            if sector is None:
                continue
            head = " ".join(text.upper().split())[:700]
            ys = re.findall(r"((?:19|20)\d{2})\s*-\s*(\d{2})", head)
            ys = sorted({c.fy_normalise(a + "-" + b) for a, b in ys})
            want = [y for y, _ in years]
            # The modern header prints '2020-21 2021-22 ... 2019-20' in reading
            # order, so the years are matched as a set, not by position.
            if set(want) <= set(ys):
                slots = [0, 1, 2]
            elif len(ys) == 1 and ys[0] in want:
                slots = [want.index(ys[0])]
            else:
                problems.append("%s p%d: header years %s, edition %s"
                                % (path.name, i + 1, ys, first))
                continue
            if all((sector, g) in done for g in slots):
                continue
            try:
                layout, table, group = read_sector_page(page, path.name)
            except ValueError as exc:
                problems.append("%s p%d %s: %s" % (path.name, i + 1, sector, exc))
                continue
            page_problems = []
            got = {code: sector_values(layout, cells, page_problems,
                                       "%s p%d %s %s" % (path.name, i + 1, sector, code))
                   for code, cells in table.items()}
            if len(next(iter(got.values()))) != len(slots):
                problems.append("%s p%d %s: %d year groups on a page that names %d"
                                % (path.name, i + 1, sector,
                                   len(next(iter(got.values()))), len(slots)))
                continue
            for j, g in enumerate(slots):
                col = years[g]
                st = sum(v[j] or 0.0 for k, v in got.items() if group.get(k) == "state")
                ut = sum(v[j] or 0.0 for k, v in got.items() if group.get(k) == "ut")
                for tot, s_, what in (("total_states", st, "states"),
                                      ("total_uts", ut, "UTs"),
                                      ("total", st + ut, "states + UTs")):
                    if tot not in got or got[tot][j] is None:
                        if tot != "total_uts":
                            page_problems.append("%s p%d %s: no %s row"
                                                 % (path.name, i + 1, sector, tot))
                        continue
                    if abs(got[tot][j] - s_) > TOL_K + TOL_K_PER_ROW * len(got):
                        page_problems.append(
                            "%s p%d %s %s %s: %s add to %.0f, printed %.0f"
                            % (path.name, i + 1, sector, col[0], col[1], what, s_,
                               got[tot][j]))
            if (first, sector) in DEFECTIVE:
                if not page_problems:
                    problems.append("%s p%d %s is listed as defective but now passes "
                                    "every check; remove it from DEFECTIVE"
                                    % (path.name, i + 1, sector))
                for g in slots:
                    done.add((sector, g))
                excluded[sector] = {"page": i + 1, "reason": DEFECTIVE[(first, sector)]}
                continue
            problems.extend(page_problems)
            for j, g in enumerate(slots):
                f = found.setdefault(sector, {"page": i + 1, "layout": layout,
                                              "values": {}, "group": group})
                for code, v in got.items():
                    f["values"].setdefault(code, [None, None, None])[g] = v[j]
                done.add((sector, g))
    missing = [k for k, _ in SECTORS[:5]
               if not all((k, g) in done for g in range(3))]
    if missing:
        problems.append("%s: no total statement for %s" % (path.name, ", ".join(missing)))
    return years, found, excluded


# --------------------------------------------------------------------------- #
# Table 4: the national series
# --------------------------------------------------------------------------- #


def read_table4(path, problems):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages[:60]):
            text = page.extract_text() or ""
            if not re.search(r"PUBLIC EXPENDITURE ON EDUCATION AS PERCENTAGE OF GDP FROM",
                             text.upper()):
                continue
            out = {}
            if re.search(r"\bCONTENTS\b", text.upper()):
                continue                 # the contents page names the table too
            for r in rows_of(words(page)):
                toks = [w["text"] for w in r]
                if len(toks) < 15 or not re.fullmatch(r"\d{1,2}", toks[0]):
                    continue
                m = re.match(r"((?:19|20)\d{2}-\d{2})", toks[1])
                if not m:
                    continue
                fy = c.fy_normalise(m.group(1))
                rest = " ".join(toks[1:])
                et = "BE" if "BE" in rest else "RE" if "RE" in rest else "A"
                # Everything after the year cell; '(Actual)' is not a number.
                nums = [value(t) for t in toks[2:] if NUM.match(t)]
                nums = [x for x in nums if x is not None]
                if len(nums) != 13:
                    problems.append("Table 4 %s: %d figures" % (fy, len(nums)))
                    continue
                gdp, s, cen, tot, sp, cp, tp, s2, c2, t2, sp2, cp2, tp2 = nums
                for a, b, cc, what in ((s, cen, tot, "education departments"),
                                       (s2, c2, t2, "education and other departments")):
                    if abs(a + b - cc) > 2.0:
                        problems.append("Table 4 %s %s: %.0f + %.0f != %.0f"
                                        % (fy, what, a, b, cc))
                for x, pct in ((tot, tp), (t2, tp2), (s, sp), (cen, cp), (s2, sp2), (c2, cp2)):
                    if abs(100.0 * x / gdp - pct) > 0.011:
                        problems.append("Table 4 %s: %.0f / GDP %.0f = %.3f%%, printed %.2f"
                                        % (fy, x, gdp, 100.0 * x / gdp, pct))
                out[fy] = {
                    "estimate_type": et, "gdp": gdp,
                    "education_departments": {"states": s, "centre": cen, "total": tot,
                                              "pct_gdp": {"states": sp, "centre": cp,
                                                          "total": tp}},
                    "education_and_other_departments": {
                        "states": s2, "centre": c2, "total": t2,
                        "pct_gdp": {"states": sp2, "centre": cp2, "total": tp2}},
                }
            if not out:
                continue
            note = " ".join(text.split("Note")[-1].split())[:600] if "Note" in text else ""
            return i + 1, out, note
    problems.append("%s: no Table 4" % path.name)
    return None, {}, ""


# --------------------------------------------------------------------------- #


def main() -> None:
    ref = c.read_json(REF)
    copies = collections.defaultdict(list)
    for key, ed in ref["editions"].items():
        if not ed.get("ok") or not ed.get("first"):
            continue
        copies[(ed["first"], ed["last"])].append(ed)
    problems, all_rows = [], []
    by_edition = {}
    for span, eds in sorted(copies.items(), key=lambda kv: c.fy_start(kv[0][0])):
        # Two editions survive as two files (2011-14 in both upload
        # directories; 2016-19 as Analysis_..._2017-2019.pdf and
        # budget_expenditure.pdf). They are different typesettings of the
        # same tables, and the second 2016-19 file reads where the first's
        # language page does not. Every copy is read; the one with the fewest
        # problems is kept, and its problems, if any, stand.
        best = None
        for ed in eds:
            local = []
            years, found, excl = read_edition(RAW / ed["path"], ed, local)
            if best is None or len(local) < len(best[3]):
                best = (ed, years, found, local, excl)
        ed, years, found, local, excl = best
        if local and all("no state rows" in p or "money columns" in p or
                         "no total statement" in p for p in local) and not found:
            print("  %s: no text-layer sector statements (%s)" % (ed["file"], local[0][:60]))
            by_edition[span] = {"file": ed["file"], "skipped": local[0]}
            continue
        problems += local
        by_edition[span] = {"file": ed["file"], "path": ed["path"], "years": years,
                            "found": found, "url": ed["archive_url"],
                            "original": ed["original"], "excluded": excl}
        print("  %-60s %s: %s" % (ed["file"][:60], "/".join("%s %s" % y for y in years),
                                  ", ".join("%s p%d" % (k, v["page"]) for k, v in found.items())))

    latest = max((s for s in by_edition if "found" in by_edition[s]),
                 key=lambda s: c.fy_start(s[0]))
    t4_page, national, t4_note = read_table4(RAW / by_edition[latest]["path"], problems)
    # Cross-edition fixture: 2010-11 total (education + other departments).
    if national.get("2010-11") and abs(national["2010-11"]["education_and_other_departments"]
                                       ["total"] - 293478.0) > 1.0:
        problems.append("Table 4's 2010-11 total is %.0f, but the 2010-13 edition "
                        "prints 293478.25" % national["2010-11"]
                        ["education_and_other_departments"]["total"])

    if problems:
        print("\nrefusing to write:")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print("  ... and %d more" % (len(problems) - 40))
        raise SystemExit(1)

    # Latest edition wins for each (year, estimate type).
    chosen = {}
    for span, e in sorted(by_edition.items(), key=lambda kv: c.fy_start(kv[0][0])):
        if "found" not in e:
            continue
        for g, col in enumerate(e["years"]):
            chosen[col] = span
    states = collections.defaultdict(lambda: collections.defaultdict(dict))
    where = {}
    for col, span in chosen.items():
        e = by_edition[span]
        g = e["years"].index(col)
        for sector, f in e["found"].items():
            for code, vals in f["values"].items():
                v = vals[g]
                if v is None:
                    continue
                code = code.replace("_2", "")     # J&K as state, then as UT
                cr = c.to_crore(v, "thousand")
                cell = states[code][sector].setdefault(col[0], {})
                cell[col[1]] = round(cell.get(col[1], 0.0) + cr, 2)
                where[(code, sector) + col] = (span, e["url"], f["page"])
    for (code, sector, fy, et), (span, url, page) in sorted(where.items()):
        all_rows.append(c.Row(
            fiscal_year=fy, govt="state", state_code=code, estimate_type=et,
            source_edition="ABE " + "-".join(span), definition="functional",
            ministry_or_dept="education departments", scheme=sector,
            account="abe_revenue_by_sector",
            amount_cr=states[code][sector][fy][et], source_url=url,
            source_page="p%d" % page))
    c.write_long_table(all_rows, OUT_CSV)
    c.write_json({
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "source": ("Ministry of Education, Analysis of Budgeted Expenditure "
                       "on Education, editions 2007-10 to 2019-22, retrieved "
                       "from the Wayback Machine (the ministry's own URLs 404)."),
            "unit": "Rs crore, nominal",
            "national_source": "%s, Table 4 (p%s)" % (by_edition[latest]["file"], t4_page),
            "national_note": t4_note,
            "national_rule": ("The only Centre-plus-states figure in this "
                              "repository. Each rupee is counted once, by the "
                              "government that spends it; never add "
                              "data/union.json to data/states.json instead."),
            "states_definition": ("Revenue account expenditure of the education "
                                  "departments only, by sub-sector. Capital, "
                                  "loans and other departments' education "
                                  "spending are not split by sub-sector in the "
                                  "ABE."),
            "sectors": [k for k, _ in SECTORS],
            "state_rows": ("Codes follow data/reference/states.json; UTs "
                           "without a legislature use ISO 3166-2:IN. "
                           "total_states, total_uts and total are the ABE's "
                           "own printed totals."),
            "editions": {"-".join(span): {k: v for k, v in e.items()
                                          if k in ("file", "url", "original", "skipped",
                                                   "excluded")}
                         for span, e in sorted(by_edition.items())},
            "chosen": {"%s %s" % col: "-".join(span) for col, span in sorted(chosen.items())},
        },
        "national": national,
        "states": {code: {s: dict(sorted(v.items(), key=lambda kv: c.fy_start(kv[0])))
                          for s, v in states[code].items()} for code in sorted(states)},
    }, OUT_JSON)


if __name__ == "__main__":
    main()

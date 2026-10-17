"""Parse the PDF-era Demands for Grants into the long table.

Only four editions ship ``alldg.xlsx``. Every edition from 2003-04 publishes
the same statements as PDF, so this is what closes the 2020-21 / 2021-22 hole
and takes the series back twenty years:

*   ``alldg.pdf``  - one bundle, 2011-12 onwards, demand pages after the front
    matter and the SUMMARY.
*   ``dg<N>.pdf``  - one file per demand, 2003-04 onwards.

    python scripts/parse_union_pdf.py            # report, and write the
    python scripts/parse_union_pdf.py 2021-22    # PDF-only diagnostic table

The statement is the same shape as the workbook's, so the layout rules live
in union_statement.py and are shared. What is different is the container, and
the container is where the work is:

1.  **A PDF has no columns, only x coordinates.** A row prints only the
    amounts it has, so reading the words in order silently shifts a lone
    figure into the wrong year: demand 25 of 2021-22 shows a single -0.06
    against Secretariat-Social Services, and that is 2019-20 actuals, not the
    first column of anything. Amounts are therefore placed by their right
    edge, against column edges clustered from the whole edition.

2.  **Two header shapes.** From the 2017-18 edition the table is four columns
    (t-2 actuals, t-1 BE, t-1 RE, t BE), as in the workbooks. Before that,
    every year is split Plan / Non-Plan / Total and there is no actuals
    column at all, so those editions can only ever contribute BE and RE.

3.  **The Devanagari half is not always Devanagari.** Up to the 2018-19
    edition it is set in a legacy font with no usable encoding, so it
    extracts as Latin-1 noise. It cannot be stripped by script, so a word is
    kept only if it is ASCII once the typographic quotes are folded.

4.  **A head name wraps.** 'Grants-in-aid to State / Governments' is two
    printed lines; the second is folded back into the first when it is
    indented to the same column and the line above carries the amounts.
"""

from __future__ import annotations

import collections
import itertools
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import union_statement as us  # noqa: E402

try:
    import pdfplumber
except ImportError:
    raise SystemExit("pdfplumber is required: python -m pip install pdfplumber")

# pdfminer is loud about the older files' broken font descriptors. They
# extract fine; the warnings would bury the parse report.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

FY_TOKEN = re.compile(r"^((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})$")
ESTIMATE_TOKEN = re.compile(r"actual|budget|revised|estimate", re.I)
NON_PLAN = re.compile(r"^non\s*-?\s*plan$", re.I)
TOTAL_TOKEN = re.compile(r"^total$", re.I)
MAJOR_HEAD_LABEL = re.compile(r"major\s*head", re.I)
AMOUNT = re.compile(r"^\(?-?\d{1,3}(?:,\d{2,3})*\.\d{1,3}\)?$|^\(?-?\d+\.\d{1,3}\)?$")
NIL = re.compile(r"^\.{2,}$")
ON_BEHALF = re.compile(r"accounted for on behalf of the\s+(.+?)\.?$", re.I)
CODE = re.compile(r"^\d{4}$")

LINE_TOL = 3.0        # points; words of one printed row share a baseline
EDGE_TOL = 4.5        # points; how far an amount's right edge may wander
NIL_TOL = 12.0        # points; the nil marker is not always flush right
SPLIT_TOL = 6.0       # points; a row whose figures sit below its own name
FIT_TOL = 20.0        # points; how unevenly the columns may sit under the header
CID = re.compile(r"\(cid:\d+\)")
FOLD = {"’": "'", "‘": "'", "“": '"', "”": '"',
        "‐": "-", "‑": "-", "–": "-", "—": "-",
        " ": " ", "₹": "Rs"}


def clean(text: str) -> str:
    """A word as it should be read, or '' if it is the other script.

    Devanagari is dropped whether it arrives as Devanagari (2019-20 onwards)
    or as the legacy font's Latin-1 noise (up to 2018-19). Both are rejected
    by the same test, because real English in these documents is ASCII.
    """
    s = CID.sub("", text or "")
    for bad, good in FOLD.items():
        s = s.replace(bad, good)
    s = s.strip()
    return s if s.isascii() else ""


def page_lines(page):
    """Words grouped into printed rows, each row left to right.

    Rows are grouped on the baseline, not the top of the glyphs: Devanagari
    ascenders make a bilingual row's two halves report tops that differ by
    several points while their baselines agree.
    """
    rows = []
    for w in page.extract_words(use_text_flow=False):
        w = dict(w, text=clean(w["text"]))
        if not w["text"]:
            continue
        for row in rows:
            if abs(row[0]["bottom"] - w["bottom"]) <= LINE_TOL:
                row.append(w)
                break
        else:
            rows.append([w])
    rows.sort(key=lambda r: r[0]["bottom"])
    for row in rows:
        row.sort(key=lambda w: w["x0"])

    # The 2017-18 bundle sets a head's name a few points above its figures,
    # so one printed row arrives as two baselines. Join them back: a row of
    # nothing but amounts belongs to the row of nothing but words above it.
    out = []
    for row in rows:
        if (out and all(is_amount(w["text"]) for w in row)
                and not any(is_amount(w["text"]) for w in out[-1])
                and row[0]["bottom"] - out[-1][0]["bottom"] <= SPLIT_TOL):
            out[-1] = sorted(out[-1] + row, key=lambda w: w["x0"])
            continue
        out.append(row)
    return out


def is_amount(text: str) -> bool:
    return bool(AMOUNT.match(text) or NIL.match(text))


def centre(w) -> float:
    return (w["x0"] + w["x1"]) / 2.0


def nearest(x: float, anchors) -> int:
    return min(range(len(anchors)), key=lambda i: abs(x - anchors[i]))


# --------------------------------------------------------------------------- #
# The header: which fiscal year and estimate each money column holds
# --------------------------------------------------------------------------- #


# Every edition lays its money columns out one of exactly two ways. Knowing
# which, from the number of column groups, is what lets a page be read when
# the legacy font eats a word of its header: demand 62 of 2003-04 prints
# '2002-2003 Budget Revised 2003-2004 Budget', having lost the second year
# outright. Whatever the header does extract still has to agree, so a real
# change of layout is rejected rather than assumed away.
SHAPES = {
    3: ((-1, "BE"), (-1, "RE"), (0, "BE")),
    4: ((-2, "A"), (-1, "BE"), (-1, "RE"), (0, "BE")),
}

SUB_COLUMN = re.compile(r"^(non\s*-?\s*plan|plan|total)$", re.I)


def expected_columns(edition_fy: str, groups: int):
    shape = SHAPES.get(groups)
    if shape is None:
        return None
    return [(c.fy_shift(edition_fy, d), e) for d, e in shape]


def sub_columns(rows, lo, hi):
    """The Plan / Non-Plan / Total band under the years, if the edition has one.

    -> (row index, [words], columns per group, offset of Total within a group)
    """
    for j in range(max(0, lo), min(hi, len(rows))):
        row = rows[j]
        if sum(1 for w in row if NON_PLAN.match(w["text"])) < 2:
            continue
        sub = [w for w in row if SUB_COLUMN.match(w["text"])]
        totals = [n for n, w in enumerate(sub) if TOTAL_TOKEN.match(w["text"])]
        if not totals or len(sub) % len(totals):
            return None
        k = len(sub) // len(totals)
        if sorted(totals) != list(range(k - 1, len(sub), k)):
            return None
        return j, sub, k, k - 1
    return None


def read_header(rows, edition_fy: str):
    """-> (last header row index, [(fy, etype)], money column per year, anchors).

    Returns (None, [], [], []) when the page is not a demand table. The front
    matter and the SUMMARY carry fiscal years and amounts too, and the
    SUMMARY is a different statement; only a demand table names a Major Head.

    The header is found from the Major Head line downwards, not from the
    years, because the years are the part that goes missing: the 2014-15
    bundle sets them in the legacy font and its header extracts as the bare
    words 'Budget Revised Budget'.
    """
    blank = (None, [], [], [])
    mh = next((j for j, r in enumerate(rows[:24])
               if MAJOR_HEAD_LABEL.search(" ".join(w["text"] for w in r))), None)
    if mh is None:
        return blank

    top = max(0, mh - 3)
    band = sub_columns(rows, mh - 1, mh + 2)
    if band is None:
        year_row = max(range(top, mh + 1),
                       key=lambda j: sum(1 for w in rows[j]
                                         if FY_TOKEN.match(w["text"])))
        years = [w for w in rows[year_row] if FY_TOKEN.match(w["text"])]
        if len(years) < 3:
            return blank
        last = mh
        anchors = [centre(w) for w in years]
        group_at = list(anchors)
        index = list(range(len(anchors)))
    else:
        band_row, sub, k, off = band
        last = max(mh, band_row)
        anchors = [centre(w) for w in sub]
        group_at = [sum(anchors[g:g + k]) / k
                    for g in range(0, len(anchors), k)]
        index = [g * k + off for g in range(len(group_at))]

    cols = expected_columns(edition_fy, len(group_at))
    if cols is None:
        return blank
    found = [w for j in range(top, last + 1) for w in rows[j]
             if FY_TOKEN.match(w["text"])]
    said = [[] for _ in group_at]
    for j in range(top, last + 1):
        for w in rows[j]:
            if FY_TOKEN.match(w["text"]) or not ESTIMATE_TOKEN.search(w["text"]):
                continue
            said[nearest(centre(w), group_at)].append(w["text"])

    # Enough of the header has to survive extraction to confirm the shape:
    # either the years, or an estimate word over every single group.
    if len(found) < 2 and not all(said):
        return blank
    for w in found:
        try:
            fy = c.fy_normalise(w["text"])
        except ValueError:
            return blank
        if fy != cols[nearest(centre(w), group_at)][0]:
            return blank
    for group, (_, etype) in zip(said, cols):
        if group and us.estimate_type(" ".join(group)) != etype:
            return blank
    return last, cols, index, anchors


def money_columns(pages, anchors):
    """Where each money column's amounts end, or None where none were printed.

    Amounts are right-aligned and a column does not move between the pages of
    one file, so the x of every amount in the file clusters onto the columns.
    Only tokens with a decimal point are counted. A four-digit major head is
    a number too and is not money; and the nil marker is set centred rather
    than flush right in the older editions, so counting it would split every
    column in two.

    The clusters are then matched to the header's columns in order, allowing
    for columns that are entirely empty - demand 19 of 2003-04 is wholly
    non-Plan, so three of its nine columns print nothing at all and a
    positional read would file its Non-Plan figures as Plan.
    """
    xs = []
    for rows, header, _, _, _ in pages:
        for row in rows[header + 1:]:
            xs += [w["x1"] for w in row if AMOUNT.match(w["text"])]
    if not xs:
        return None
    xs.sort()
    groups, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] <= EDGE_TOL:
            cur.append(x)
        else:
            groups.append(cur)
            cur = [x]
    groups.append(cur)
    floor = max(2, max(len(g) for g in groups) // 8)
    found = [sum(g) / len(g) for g in groups if len(g) >= floor]

    n = len(anchors)
    if not found or len(found) > n:
        return None
    best = None
    for combo in itertools.combinations(range(n), len(found)):
        off = [found[j] - anchors[i] for j, i in enumerate(combo)]
        spread = max(off) - min(off)
        if best is None or spread < best[0]:
            best = (spread, combo)
    if best[0] > FIT_TOL:
        return None
    edges = [None] * n
    for j, i in enumerate(best[1]):
        edges[i] = found[j]
    return edges


# --------------------------------------------------------------------------- #
# The demand a page belongs to
# --------------------------------------------------------------------------- #


def page_header(rows, upto: int):
    """Demand number, department and ministry from the matter above the table.

    Appropriations are headed 'NO. 37 (APPROPRIATION)' because the word for
    Demand is printed only in Devanagari. They include Interest Payments, so
    a parser that insists on 'DEMAND NO.' loses Rs 14 lakh crore.
    """
    demand_no, dept, ministry = None, "", ""
    for row in rows[:upto]:
        text = " ".join(w["text"] for w in row)
        text = re.sub(r"\(\s*\)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if demand_no is None and re.match(r"^(DEMAND\s+)?NO\.", text, re.I):
            m = us.DEMAND_NO.search(text)
            if m:
                demand_no = int(m.group(1))
                continue
        m = ON_BEHALF.search(text)
        if m:
            ministry = re.sub(r"\(.*?\)", "", m.group(1)).strip().title()
            continue
        if demand_no is not None and not dept:
            letters = re.sub(r"[^A-Za-z]", "", text)
            if len(letters) > 5 and letters.isupper():
                dept = re.sub(r"\(.*?\)", "", text).strip().title()
    return demand_no, dept, ministry


# --------------------------------------------------------------------------- #
# A page of table rows -> union_statement.Line records
# --------------------------------------------------------------------------- #


class _Line(us.Line):
    """A Line that also remembers where its label starts, for wrapped names."""

    def __init__(self, label, code, amounts, x0):
        super().__init__(label=label, code=code, amounts=amounts)
        self.x0 = x0


def table_lines(rows, header: int, edges, index):
    live = [i for i, e in enumerate(edges) if e is not None]
    out = []
    for row in rows[header + 1:]:
        amounts, words = {}, []
        for w in row:
            if is_amount(w["text"]) and live:
                col = live[nearest(w["x1"], [edges[i] for i in live])]
                tol = NIL_TOL if NIL.match(w["text"]) else EDGE_TOL
                if abs(w["x1"] - edges[col]) <= tol:
                    v = c.num(w["text"])
                    if v is not None and col not in amounts:
                        amounts[col] = v
                    continue
            words.append(w)
        code = next((w["text"] for w in words if CODE.match(w["text"])), "")
        label_words = [w for w in words if w["text"] != code]
        label = " ".join(w["text"] for w in label_words)
        x0 = label_words[0]["x0"] if label_words else None

        # A wrapped head name: same indent, nothing of its own to say.
        if (out and not amounts and not code and x0 is not None
                and out[-1].amounts and out[-1].code
                and out[-1].x0 is not None and abs(x0 - out[-1].x0) <= 3.0
                and 0 < len(label.split()) <= 6):
            out[-1].label += " " + label
            continue

        out.append(_Line(label=label, code=code,
                         amounts={n: amounts[i] for n, i in enumerate(index)
                                  if i in amounts},
                         x0=x0))
    return out


# --------------------------------------------------------------------------- #
# Whole documents
# --------------------------------------------------------------------------- #


def read_pages(path, edition_fy: str):
    """[(rows, header index, columns, column index)] for one file's demand pages."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows = page_lines(page)
            header, cols, index, anchors = read_header(rows, edition_fy)
            if header is None:
                continue
            pages.append((rows, header, cols, index, anchors))
    return pages


def parse_edition(paths, edition_fy: str, source_url: str):
    """Every demand in one edition's PDFs -> (rows, demands, problems).

    Column edges are clustered per file, not per edition. The bundle is one
    typesetting run so it makes no difference there, but an edition published
    as a hundred separate dg<N>.pdf is a hundred runs, and the columns of
    demand 1 are a point or two from those of demand 2.
    """
    rows_out, demands, problems = [], {}, []
    shapes = set()

    for path in paths:
        try:
            pages = read_pages(path, edition_fy)
        except Exception as exc:                      # a broken or encrypted file
            problems.append("%s: %s: %s" % (edition_fy, path.name,
                                            str(exc).strip()[:80]))
            continue
        if not pages:
            problems.append("%s: %s: no demand table" % (edition_fy, path.name))
            continue

        here = {tuple(cols) for _, _, cols, _, _ in pages}
        if len(here) != 1:
            problems.append("%s: %s: %d different column headers"
                            % (edition_fy, path.name, len(here)))
            continue
        shapes |= here
        year_cols = list(here.pop())
        index, anchors = pages[0][3], pages[0][4]
        edges = money_columns(pages, anchors)
        if edges is None:
            problems.append("%s: %s: could not place %d money columns"
                            % (edition_fy, path.name, len(anchors)))
            continue

        cols = dict(enumerate(year_cols))
        demand_no = None
        pending = collections.defaultdict(list)
        for rows, header, _, _, _ in pages:
            n, d, m = page_header(rows, header)
            if n is not None:
                demand_no = n
                demands[n] = {"department": d, "ministry": m or d}
            if demand_no is None:
                problems.append("%s: %s: a table page before any demand number"
                                % (edition_fy, path.name))
                continue
            pending[demand_no] += table_lines(rows, header, edges, index)

        for no, lines in sorted(pending.items()):
            rows_out += us.walk(
                lines, cols,
                dept=demands.get(no, {}).get("department", ""),
                edition="ExpBudget " + edition_fy,
                source_url=source_url,
                source_page="%s!dg%d" % (edition_fy, no))

    if len(shapes) > 1:
        return [], {}, ["%s: %d different column headers in one edition: %s"
                        % (edition_fy, len(shapes), sorted(shapes)[:3])]
    return rows_out, demands, problems


def edition_paths(ed: dict):
    """Where this edition's PDFs are on disk, and the URL they came from."""
    base = c.RAW / "union" / ed["fiscal_year"]
    if (base / "alldg.pdf").exists():
        return [base / "alldg.pdf"], ed["eb_base"] + "alldg.pdf"
    per = sorted((base / "dg").glob("dg*.pdf"),
                 key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    return per, ed["eb_base"] + "dg<N>.pdf"


def pdf_editions(only=None):
    """The editions with usable PDFs on disk, oldest first.

    An edition the map marks ``unparsed`` is skipped: the layout drifted far
    enough that the figures could not be stood behind, and a wrong number is
    worse than a missing year.
    """
    out = []
    for ed in c.read_json(c.REFERENCE / "union_editions.json"):
        if ed["interim"] or ed.get("unparsed"):
            continue
        if only and ed["fiscal_year"] not in only:
            continue
        paths, url = edition_paths(ed)
        if paths:
            out.append((ed, paths, url))
    return out


def main(argv) -> None:
    only = {c.fy_normalise(a) for a in argv if not a.startswith("--")} or None
    todo = pdf_editions(only)
    if not todo:
        raise SystemExit("no raw PDFs; run scripts/fetch_union.py --pdf first")

    all_rows, problems = [], []
    for ed, paths, url in todo:
        fy = ed["fiscal_year"]
        rows, demands, probs = parse_edition(paths, fy, url)
        problems += probs
        all_rows += rows
        years = sorted({(r.fiscal_year, r.estimate_type) for r in rows})
        print("  %-9s %3d demands %7d rows   %s"
              % (fy, len(demands), len(rows),
                 ", ".join("%s %s" % y for y in years)))

    if problems:
        print("\n%d problems:" % len(problems))
        for p in problems[:12]:
            print("   ", p)

    if all_rows:
        all_rows.sort(key=lambda r: (r.fiscal_year, r.source_page, r.account))
        c.write_long_table(all_rows, c.PROCESSED / "union_demands_pdf.csv")


if __name__ == "__main__":
    main(sys.argv[1:])

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
import hashlib
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
DASH = re.compile(r"^[-‐-―]+$")

LINE_TOL = 3.0        # points; words of one printed row share a baseline
EDGE_TOL = 8.0        # points; how far an amount's right edge may wander
CLUSTER_TOL = 9.0     # points; still far inside the ~34pt gap between columns
NIL_TOL = 12.0        # points; the nil marker is not always flush right
SPLIT_TOL = 6.0       # points; a row whose figures sit below its own name
FIT_TOL = 28.0        # points; how unevenly a sparse table may sit under its header
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


RUN_ON = re.compile(r"^((?:19|20)\d{2}\s*-\s*(?:19|20)?\d{2})([^\W\d].*)$")
ONE_CELL = re.compile(r"^(?:-?\d+\.\d{2}|\.{2,3})")


def split_figures(text):
    """['...', '14318.18'] if the token is cells run together, else []."""
    parts, rest = [], text
    while rest:
        m = ONE_CELL.match(rest)
        if not m:
            return []
        parts.append(m.group(0))
        rest = rest[m.end():]
    return parts if len(parts) > 1 else []


def split_word(w):
    """One extracted token back into the words it was printed as.

    Two things in the older editions arrive glued together, and both are
    fatal rather than untidy:

    *   A year and its estimate: '2009-2010Budget' (demand 2 of 2010-11)
        matches neither the year test nor anything else, so the page reads as
        having no columns at all.
    *   Two adjacent cells, figures or the nil marker: 'GRAND TOTAL 905.00
        2014.68 2919.68 695.00 2013.432708.43 ...' (demand 5 of 2003-04),
        'Total ...14318.18 14318.18 ...' (demand 24 of 2010-11). The glued
        pair is not a number, so it is taken for part of the label, the
        landmark stops matching, and the parser never learns that the
        recoveries have started - it then reports a demand's recoveries as
        its expenditure.

    The width is apportioned by character, which is close enough to place
    each part in its own column.
    """
    for parts in (split_figures(w["text"]),):
        if parts:
            out, at = [], w["x0"]
            span = (w["x1"] - w["x0"]) / len(w["text"])
            for part in parts:
                out.append(dict(w, text=part, x0=at, x1=at + span * len(part)))
                at += span * len(part)
            return out
    m = RUN_ON.match(w["text"])
    if not m:
        return [w]
    cut = w["x0"] + (w["x1"] - w["x0"]) * len(m.group(1)) / len(w["text"])
    return [dict(w, text=m.group(1), x1=cut),
            dict(w, text=m.group(2), x0=cut)]


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
        for part in split_word(w):
            for row in rows:
                if abs(row[0]["bottom"] - part["bottom"]) <= LINE_TOL:
                    row.append(part)
                    break
            else:
                rows.append([part])
    rows.sort(key=lambda r: r[0]["bottom"])
    for row in rows:
        row.sort(key=lambda w: w["x0"])

    # The 2017-18 bundle sets a head's name a few points above its figures,
    # so one printed row arrives as two baselines. Join them back: a row of
    # nothing but figures belongs to the row of nothing but words above it.
    # The figures are often led by a stray dash, left behind where the
    # Devanagari was stripped, and that dash has to be allowed for or the
    # recoveries of the Defence demands are dropped whole.
    out = []
    for row in rows:
        if (out and all(is_amount(w["text"]) or DASH.match(w["text"])
                        for w in row)
                and any(is_amount(w["text"]) for w in row)
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
    # Only a row that carries several years is the year row. Every page is
    # headed '2021-2022 Demands For Grants', and reading that as a column
    # heading rejects every continuation page in the bundle.
    year_rows = [j for j in range(top, last + 1)
                 if sum(1 for w in rows[j] if FY_TOKEN.match(w["text"])) >= 2]
    found = [w for j in year_rows for w in rows[j]
             if FY_TOKEN.match(w["text"])]
    said = [[] for _ in group_at]
    for j in range(min(year_rows) if year_rows else top, last + 1):
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


def cluster(xs, tol):
    xs = sorted(xs)
    out, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] <= tol:
            cur.append(x)
        else:
            out.append(cur)
            cur = [x]
    out.append(cur)
    return out


def money_columns(pages, anchors):
    """Where each money column's figures end, or None where it printed none.

    Figures are flush right and a column does not move between the pages of
    one typesetting, so the right edge of every figure in the file clusters
    onto the columns. A four-digit major head is a number too and is not
    money; requiring a decimal point keeps it out.

    The nil marker is counted separately, because up to the 2010-11 editions
    it is set centred rather than flush right and sits a few points to the
    left of its own column. It still says a column is there, which matters:
    demand 61 of 2003-04 is wholly non-Plan and prints nothing but '...' in
    three of its nine columns, and without them the remaining six can be read
    one column to the left - putting its Non-Plan figures under Plan and
    leaving the Total column, the only one this parser reads, empty.
    """
    figures, nils = [], []
    for rows, header, _, _, _ in pages:
        for row in rows[header + 1:]:
            for w in row:
                if AMOUNT.match(w["text"]):
                    figures.append(w["x1"])
                elif NIL.match(w["text"]):
                    nils.append(w["x1"])
    if not figures:
        return None

    groups = cluster(figures, CLUSTER_TOL)
    floor = max(2, max(len(g) for g in groups) // 8)
    seen = [(sum(g) / len(g), True) for g in groups if len(g) >= floor]
    if nils:
        groups = cluster(nils, CLUSTER_TOL)
        floor = max(2, max(len(g) for g in groups) // 8)
        seen += [(sum(g) / len(g), False) for g in groups if len(g) >= floor]
    seen.sort()

    # A column's figures and its nils are two clusters of the same column.
    columns, cur = [], [seen[0]]
    for x in seen[1:]:
        if x[0] - cur[-1][0] <= NIL_TOL:
            cur.append(x)
        else:
            columns.append(cur)
            cur = [x]
    columns.append(cur)

    # Where a column printed only nils, place it at the offset the columns
    # that printed both show the nil marker to sit at.
    shift = [sum(x for x, real in col if real) / sum(1 for _, real in col if real)
             - sum(x for x, real in col if not real)
             / sum(1 for _, real in col if not real)
             for col in columns
             if any(r for _, r in col) and any(not r for _, r in col)]
    shift = sorted(shift)[len(shift) // 2] if shift else 0.0
    found = []
    for col in columns:
        real = [x for x, r in col if r]
        found.append(sum(real) / len(real) if real
                     else sum(x for x, _ in col) / len(col) + shift)

    n = len(anchors)
    if len(found) > n:
        return None
    if len(found) == n:
        # Every column said something, so there is nothing to decide. The
        # header words themselves are not precise enough to second-guess it:
        # a bilingual cell drags its English half several points either way.
        return found
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


IN_RESPECT = re.compile(r"in respect of (?:the )?(.+?)\.?$", re.I)


def caps_tail(text: str) -> str:
    """The run of capitals at the end of a line, as a name.

    The heading of a demand is set in capitals, but the legacy font leaves
    noise in front of it: demand 11 of 2004-05 reads 'Jx DEPARTMENT OF
    MINES'. Dropping the words that are not capitals leaves the name.
    """
    words = text.split()
    while words and not re.sub(r"[^A-Za-z]", "", words[0]).isupper():
        words.pop(0)
    name = re.sub(r"\(.*?\)", "", " ".join(words)).strip()
    letters = re.sub(r"[^A-Za-z]", "", name)
    return name.title() if len(letters) > 5 and letters.isupper() else ""


def page_header(rows, upto: int):
    """Demand number, department and ministry from the matter above the table.

    Appropriations are headed 'NO. 37 (APPROPRIATION)' because the word for
    Demand is printed only in Devanagari. They include Interest Payments, so
    a parser that insists on 'DEMAND NO.' loses Rs 14 lakh crore.

    The department is named twice, as the heading and in the sentence that
    opens the demand, and neither survives every edition: the heading of
    demand 102 of 2012-13 wraps, so only 'WORKS' is left of Public Works,
    and demand 40 of 2014-15 has no heading at all. The sentence in turn is
    cut off where it wraps. The longer of the two is taken.
    """
    demand_no, dept, said, ministry = None, "", "", ""
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
        m = IN_RESPECT.search(text)
        if m and not said:
            said = caps_tail(m.group(1))
            continue
        if demand_no is not None and not dept:
            dept = caps_tail(text)
    return demand_no, max(dept, said, key=len), ministry


# --------------------------------------------------------------------------- #
# A page of table rows -> union_statement.Line records
# --------------------------------------------------------------------------- #


class _Line(us.Line):
    """A Line that also remembers where its label starts, for wrapped names."""

    def __init__(self, label, code, amounts, x0):
        super().__init__(label=label, code=code, amounts=amounts)
        self.x0 = x0


CODE_THEN_FIGURE = re.compile(r"^(\d{4})(-?\d+\.\d{1,3})$")
NAME_THEN_CODE = re.compile(r"^(\D.*?[A-Za-z.)])(\d{4})$")


def code_column(pages, edges):
    """Where the Major Head column ends, if the file ever prints it alone."""
    live = [e for e in edges if e is not None]
    xs = []
    for rows, header, _, _, _ in pages:
        for row in rows[header + 1:]:
            for w in row:
                if CODE.match(w["text"]) and all(abs(w["x1"] - e) > EDGE_TOL
                                                 for e in live):
                    xs.append(w["x1"])
    if not xs:
        # A demand of two heads, one of them glued to its name, leaves
        # nothing to learn the column from - demand 82 of 2003-04. One
        # unglued code is enough: the column does not move within a file.
        return None
    groups = cluster(xs, CLUSTER_TOL)
    best = max(groups, key=len)
    return sum(best) / len(best)


def unglue_code(w, code_at):
    """Split a major head away from the name or the figure stuck to it.

    Two spellings of the same accident, both in the 2003-04 edition:

    *   'Tourism 3452107.50' (demand 91). The code and the first figure run
        together into something that parses as a number, so the head loses
        its code and a column gains a figure of Rs 3.45 lakh crore.
    *   'International Financial Institutions3466' (demand 33). The name and
        the code run together, so the line has no code at all and is taken
        for the wrapped tail of the line above - and Rs 8.46 crore quietly
        leaves the revenue section.

    Either way the split is accepted only where the part that would be the
    code really does sit in the Major Head column.
    """
    if code_at is None:
        return [w]
    m = CODE_THEN_FIGURE.match(w["text"])
    if m:
        cut = w["x0"] + (w["x1"] - w["x0"]) * len(m.group(1)) / len(w["text"])
        if abs(cut - code_at) <= EDGE_TOL:
            return [dict(w, text=m.group(1), x1=cut),
                    dict(w, text=m.group(2), x0=cut)]
        return [w]
    m = NAME_THEN_CODE.match(w["text"])
    if m and abs(w["x1"] - code_at) <= EDGE_TOL:
        cut = w["x0"] + (w["x1"] - w["x0"]) * len(m.group(1)) / len(w["text"])
        return [dict(w, text=m.group(1), x1=cut),
                dict(w, text=m.group(2), x0=cut)]
    return [w]


def table_lines(rows, header: int, edges, index, code_at=None):
    live = [i for i, e in enumerate(edges) if e is not None]
    out = []
    for row in rows[header + 1:]:
        amounts, words = {}, []
        for w in [part for v in row for part in unglue_code(v, code_at)]:
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

    Column edges are clustered per file and per layout, never per edition:
    an edition published as a hundred separate dg<N>.pdf is a hundred
    typesetting runs, and even one bundle can hold several.
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
        cols = dict(enumerate(here.pop()))

        # One bundle can hold more than one typesetting of the same table:
        # the 2016-17 alldg.pdf has three, their columns a few points apart.
        # Pages are grouped by where their header sits, and each group gets
        # its own column edges, or the groups blur into each other.
        by_layout = collections.defaultdict(list)
        for page in pages:
            by_layout[tuple(round(a) for a in page[4])].append(page)
        edges, code_at = {}, {}
        for sig, group in by_layout.items():
            fitted = money_columns(group, list(group[0][4]))
            if fitted is not None:
                code_at[sig] = code_column(group, fitted)
            if fitted is None:
                problems.append("%s: %s: could not place %d money columns "
                                "on %d page(s)"
                                % (edition_fy, path.name, len(sig), len(group)))
                continue
            edges[sig] = fitted
        if not edges:
            continue

        demand_no = None
        pending = collections.defaultdict(list)
        for rows, header, _, index, anchors in pages:
            n, d, m = page_header(rows, header)
            if n is not None and n in pending:
                # Some files ship the same demand twice: dg31.pdf of 2003-04
                # is one page printed two pages long. Parsing both doubles
                # the demand, and the doubling is invisible downstream
                # because every identity within it still holds.
                problems.append("%s: %s: demand %d printed twice, "
                                "second copy ignored" % (edition_fy, path.name, n))
                demand_no = None
                continue
            if n is not None:
                demand_no = n
                demands[n] = {"department": d, "ministry": m or d}
            if demand_no is None:
                problems.append("%s: %s: a table page before any demand number"
                                % (edition_fy, path.name))
                continue
            fitted = edges.get(tuple(round(a) for a in anchors))
            if fitted is None:
                continue
            sig = tuple(round(a) for a in anchors)
            pending[demand_no] += table_lines(rows, header, fitted, index,
                                              code_at.get(sig))

        for no, lines in sorted(pending.items()):
            before = len(rows_out)
            rows_out += us.walk(
                lines, cols,
                dept=demands.get(no, {}).get("department", ""),
                edition="ExpBudget " + edition_fy,
                source_url=source_url,
                source_page="%s!dg%d" % (edition_fy, no))
            if not any(r.account == "net_total" for r in rows_out[before:]):
                # No total means the demand adds nothing to the year, which
                # is the one failure that looks like success downstream.
                problems.append("%s: %s: demand %d has no total"
                                % (edition_fy, path.name, no))

    if len(shapes) > 1:
        return [], {}, ["%s: %d different column headers in one edition: %s"
                        % (edition_fy, len(shapes), sorted(shapes)[:3])]
    return rows_out, demands, problems


# Reading 2,400 pages of PDF takes ten minutes, and parse_union.py wants the
# result on every run. Each edition is therefore cached, keyed by the source
# of the two modules that decide what the numbers mean: change either and
# every cache is stale and reparsed, so a cached run can never disagree with
# a fresh one.
CACHE = c.PROCESSED / "union_pdf_cache"


def parser_key() -> str:
    here = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for name in ("parse_union_pdf.py", "union_statement.py", "common.py"):
        h.update((here / name).read_bytes())
    return h.hexdigest()[:16]


def cached_edition(paths, edition_fy: str, source_url: str, force=False):
    key = CACHE / (edition_fy + ".key")
    table = CACHE / (edition_fy + ".csv")
    names = CACHE / (edition_fy + ".demands.json")
    want = parser_key()
    if not force and table.exists() and key.exists()             and key.read_text(encoding="utf-8").strip() == want:
        rows = []
        for d in c.read_long_table(table):
            d["occurrence"] = int(d["occurrence"] or 1)
            rows.append(c.Row(**d))
        demands = {int(k): v for k, v in c.read_json(names).items()}             if names.exists() else {}
        return rows, demands, []

    rows, demands, problems = parse_edition(paths, edition_fy, source_url)
    if rows:
        CACHE.mkdir(parents=True, exist_ok=True)
        c.write_long_table(rows, table)
        c.write_json(demands, names)
        key.write_text(want + chr(10), encoding="utf-8")
    return rows, demands, problems


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

    all_rows, problems, coverage = [], [], {}
    for ed, paths, url in todo:
        fy = ed["fiscal_year"]
        rows, demands, probs = cached_edition(paths, fy, url,
                                              force="--force" in argv)
        problems += probs
        all_rows += rows
        pages = {r.source_page for r in rows}
        coverage[fy] = {
            "files": len(paths),
            "demands_parsed": len(pages),
            "demands_with_a_total": len({r.source_page for r in rows
                                         if r.account == "net_total"}),
            "problems": probs,
        }
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
    if only is None:
        # What each edition gave up, recorded next to the edition map rather
        # than left in a console log: a year whose total is short by a demand
        # looks perfectly reasonable on a chart.
        c.write_json(coverage, c.REFERENCE / "union_pdf_coverage.json")


if __name__ == "__main__":
    main(sys.argv[1:])

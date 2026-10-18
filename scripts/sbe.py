"""The Statements of Budget Estimates: find them, fetch them, read them.

    python scripts/sbe.py fetch-education     # every edition's education SBEs
    python scripts/sbe.py fetch-all 2011-12   # every demand of one edition

`sbe<N>` is the Statement of Budget Estimates for demand N, printed in the
Expenditure Budget as "Notes on Demands for Grants". Where the Demands for
Grants stop at the major head, the SBE goes down to the scheme: Sarva Shiksha
Abhiyan, the Mid Day Meal, Mahila Samakhya, DPEP. It is also, it turns out,
the only budget document of the Plan era that prints **actuals**: from the
2011-12 edition each SBE carries an "Actual" column for the year before last,
which the Demands for Grants of the same editions do not.

This module is the shared reader. parse_schemes.py and parse_sbe_actuals.py
are its two consumers.

Formats, as served (verified by magic number, never by status code -- the
site returns a 200 HTML page for a file that does not exist):

    1998-99 .. 2010-11   PDF only
    2011-12 .. 2013-14   .xls  (BIFF, read with xlrd)
    2014-15              PDF only (the .xls 404s)
    2015-16 .. 2016-17   .xls
    2017-18 .. 2020-21   .xlsx
    2021-22 .. 2023-24   .xls  (the .xlsx 404s)
    2024-25 ..           .xlsx

The edition map (union_editions.json) records `sbe_excel` only where an .xlsx
exists, because discover_union.py never probed .xls. That is why the PDF era
looked longer than it is.

Two layouts, one model:

*   Plan era (to 2016-17): money columns split Plan / Non-Plan / Total, and a
    scheme is printed one line per major head (2202, 3601, 3602 ...) followed
    by a `Total` line. A scheme can recur in the same statement: the Sarva
    Shiksha Abhiyan of 2010-11 is item 7 (gross budgetary support), item 10.2
    (financed from the Prarambhik Shiksha Kosh) and item 34.4 (the North East
    provision), and only their sum is the scheme.
*   From 2017-18: columns split Revenue / Capital / Total, schemes printed as
    a parent item with numbered sub-items and a `Net` or `Total - <name>`.

Either way only the Total sub-column of each year is read, which is Plan plus
Non-Plan, or revenue plus capital -- one figure per scheme per year, as
parse_union.py does for the demands.

The model is deliberately dumb: every printed line with figures is either a
*leaf* (a line under a major head, or an item with no children) or a printed
total of leaves. Item values are always the sum of their own leaves; printed
totals are only ever used to check. The invariant that makes the parse safe:

    sum of every leaf == the statement's Grand Total == its top-block total

per year, in every statement read. A dropped line, a misread column or a
total mistaken for a leaf breaks it, and the consumer refuses to write.
"""

from __future__ import annotations

import logging
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

logging.getLogger("pdfminer").setLevel(logging.ERROR)

SBE_REF = c.REFERENCE / "union_sbe.json"

FORMAT_ORDER = (".xlsx", ".xls", ".pdf")
MAGIC = {".xlsx": (b"PK",), ".xls": (b"\xd0\xcf\x11\xe0",), ".pdf": (b"%PDF",)}

LEAF_TOL = 1.0          # Rs crore; leaves are printed to two decimals


# --------------------------------------------------------------------------- #
# Discovery and fetching
# --------------------------------------------------------------------------- #


def probe(url: str) -> bool:
    """True if url really serves the file type its suffix claims."""
    suffix = "." + url.rsplit(".", 1)[-1].lower()
    try:
        req = urllib.request.Request(
            c.safe_url(url), headers={"User-Agent": c.UA,
                                      "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            if resp.status not in (200, 206):
                return False
            head = resp.read(1024)
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return head.lstrip()[:8].startswith(MAGIC[suffix])


def editions():
    """Full-budget editions with an Expenditure Budget directory, oldest first."""
    return [e for e in c.read_json(c.REFERENCE / "union_editions.json")
            if not e.get("interim") and e.get("eb_base")
            and not e.get("archive_scan")]


def edition(fy: str) -> dict:
    fy = c.fy_normalise(fy)
    for e in editions():
        if e["fiscal_year"] == fy:
            return e
    raise SystemExit("no edition %s in union_editions.json" % fy)


def load_ref() -> dict:
    ref = c.read_json(SBE_REF) if SBE_REF.exists() else {}
    ref.setdefault("files", {})
    ref.setdefault("education", {})
    return ref


def save_ref(ref: dict) -> None:
    files = {fy: {n: ref["files"][fy][n] for n in sorted(ref["files"][fy], key=int)}
             for fy in sorted(ref["files"], key=c.fy_start)}
    edu = {fy: ref["education"][fy]
           for fy in sorted(ref["education"], key=c.fy_start)}
    c.write_json({
        "note": ("sbe<N> per edition, resolved by trying .xlsx, .xls and .pdf "
                 "in that order and checking the magic number of the first "
                 "kilobyte. url '' means no format exists. `education` is "
                 "the education departments' demand numbers, each confirmed "
                 "by the statement's own title."),
        "files": files, "education": edu}, SBE_REF)


def local_path(fy: str, n: int, suffix: str) -> Path:
    return c.RAW / "union" / fy / "sbe" / ("sbe%d%s" % (n, suffix))


def resolve(ed: dict, n: int, ref: dict, *, refresh=False):
    """-> (url, suffix) of the best format of sbe<n>, or None if none exists."""
    fy = ed["fiscal_year"]
    known = ref["files"].get(fy, {}).get(str(n))
    if known and not refresh:
        return (known["url"], known["format"]) if known["url"] else None
    for suffix in FORMAT_ORDER:
        url = ed["eb_base"] + "sbe%d%s" % (n, suffix)
        if probe(url):
            ref["files"].setdefault(fy, {})[str(n)] = {
                "url": url, "format": suffix,
                "checked": time.strftime("%Y-%m-%d", time.gmtime())}
            return url, suffix
    ref["files"].setdefault(fy, {})[str(n)] = {
        "url": "", "format": "",
        "checked": time.strftime("%Y-%m-%d", time.gmtime())}
    return None


def fetch(ed: dict, n: int, ref: dict):
    """Local path of sbe<n> for this edition, downloading it if need be."""
    got = resolve(ed, n, ref)
    if not got:
        return None
    url, suffix = got
    dest = local_path(ed["fiscal_year"], n, suffix)
    c.fetch(url, dest, pause=0.2)
    head = dest.read_bytes()[:8]
    if not head.startswith(MAGIC[suffix]):
        dest.unlink()
        raise SystemExit("%s: downloaded bytes are not a %s" % (url, suffix))
    return dest


# --------------------------------------------------------------------------- #
# The line model
# --------------------------------------------------------------------------- #

YEAR_GROUP = re.compile(
    r"(actuals?|budget|revised)\W*(?:estimates?\W*)?((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})",
    re.I)
ITEM_NO = re.compile(
    r"^(\d{1,3}(?:\s*\.\s*\d{1,3})*)\s*(?:([a-z])\b)?\s*\.*(?=\s|$|[A-Za-z(])",
    re.I)
CODE = re.compile(r"^\d{4}$")
TOP_LABELS = {"revenue", "capital", "total", "gross", "recoveries",
              "receipts", "net"}


@dataclass
class Line:
    item: str            # '7.02.01', '12a', or '' for a continuation line
    label: str
    code: str            # major head, 'Total' for a scheme's total line, or ''
    values: dict         # {(fy, etype): float} from the Total sub-column
    kind: str = ""       # leaf | item_total | group_total | net | parent | heading
    owner: int = -1      # index of the item a continuation line belongs to
    x0: float = None     # PDF only: where the line's first word starts
    tx: float = None     # PDF only: where the name starts, after any number


@dataclass
class Statement:
    edition: str
    demand: int
    ministry: str
    dept: str
    columns: list                    # [(fy, etype)]
    top: dict                        # {label: {(fy, etype): value}}
    lines: list = field(default_factory=list)
    grand_total: dict = field(default_factory=dict)
    source_url: str = ""
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def normalise_item(text: str) -> str:
    m = ITEM_NO.match(text.strip())
    if not m:
        return ""
    num = re.sub(r"\s+", "", m.group(1)).rstrip(".")
    return num + (m.group(2) or "").lower()


def split_item(text: str):
    """'7.02.01 National Programme' -> ('7.02.01', 'National Programme')."""
    s = text.strip()
    m = ITEM_NO.match(s)
    if not m:
        return "", s
    rest = s[m.end():].lstrip(" .")
    # A label that is only a number ('6000 Model Schools' never starts a
    # line, but a page number or a lone year might) is not an item.
    num = re.sub(r"\s+", "", m.group(1)).rstrip(".")
    if not rest and "." not in m.group(0):
        return "", s
    if re.fullmatch(r"(?:19|20)\d{2}", num):
        return "", s
    return num + (m.group(2) or "").lower(), rest


def expected_columns(edition_fy: str, groups: int):
    shape = {3: ((-1, "BE"), (-1, "RE"), (0, "BE")),
             4: ((-2, "A"), (-1, "BE"), (-1, "RE"), (0, "BE"))}.get(groups)
    if shape is None:
        return None
    return [(c.fy_shift(edition_fy, d), e) for d, e in shape]


def etype_of(word: str) -> str:
    w = word.lower()
    return "A" if w.startswith("actual") else "RE" if w.startswith("revised") else "BE"


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #


def _grid(path: Path):
    """Rows of cell values, whatever the workbook format. First sheet only."""
    if path.suffix == ".xls":
        import xlrd
        book = xlrd.open_workbook(str(path), logfile=open("nul" if sys.platform
                                  == "win32" else "/dev/null", "w"))
        sh = book.sheet_by_index(0)
        return [[sh.cell_value(r, col) for col in range(sh.ncols)]
                for r in range(sh.nrows)]
    import openpyxl
    # Not read_only: some of the 2019-20 and 2020-21 workbooks declare a
    # one-cell dimension, and a read-only sheet trusts it and reads nothing.
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%d" % v) if v.is_integer() else repr(v)
    return c.squeeze(str(v).replace("\xa0", " "))


def _title(rows_text):
    """(ministry, department) from the lines above the table."""
    ministry, dept = "", ""
    for t in rows_text:
        t = c.latin_part(str(t).replace("\n", " ~ "))
        for part in re.split(r"\s*~\s*|\s{3,}", t):
            p = re.split(r"(?i)\s+demand\b|\s+A\.\s", part.strip(" :-"))[0]
            m = re.search(r"(?i)\b((?:department|ministry) of [A-Za-z ,&'()-]+)", p)
            if not m:
                continue
            name = m.group(1).strip(" ,-")
            if re.match(r"(?i)^ministry", name):
                ministry = ministry or name
            else:
                dept = dept or name
    return ministry, dept or ministry


def read_excel(path: Path, edition_fy: str, demand: int, url: str) -> Statement:
    grid = _grid(path)
    texts = [[_text(v) for v in row] for row in grid]

    # The year row: three or four cells naming an estimate and a year.
    header = None
    for i, row in enumerate(texts[:20]):
        hits = [(j, YEAR_GROUP.search(t)) for j, t in enumerate(row) if t]
        hits = [(j, m) for j, m in hits if m]
        if len(hits) >= 3:
            header = (i, hits)
            break
    if header is None:
        raise ValueError("no year header")
    hi, hits = header
    cols = expected_columns(edition_fy, len(hits))
    if cols is None:
        raise ValueError("%d year groups" % len(hits))
    for (j, m), (fy, etype) in zip(hits, cols):
        if (c.fy_normalise(m.group(2) + "-" + m.group(3)) != fy
                or etype_of(m.group(1)) != etype):
            raise ValueError("header %r disagrees with the %s shape"
                             % (m.group(0), edition_fy))
    # The sub-column row under it: the Total of each group.
    sub = None
    for i in range(hi, min(hi + 3, len(texts))):
        totals = [j for j, t in enumerate(texts[i]) if t.lower() == "total"]
        if len(totals) >= len(hits):
            sub = i
            break
    if sub is None:
        raise ValueError("no Plan/Non-Plan/Total or Revenue/Capital/Total row")
    starts = [j for j, _ in hits] + [10 ** 6]
    total_col = []
    for g in range(len(hits)):
        js = [j for j, t in enumerate(texts[sub])
              if t.lower() == "total" and starts[g] <= j < starts[g + 1]]
        if not js:
            raise ValueError("group %d has no Total column" % g)
        total_col.append(js[0])
    money_from = min(starts[:-1])

    ministry, dept = _title([v for r in grid[:hi] for v in r
                             if isinstance(v, str) and v.strip()])
    st = Statement(edition=edition_fy, demand=demand, ministry=ministry,
                   dept=dept, columns=cols, top={}, source_url=url)

    for i in range(sub + 1, len(grid)):
        row = grid[i]
        values = {}
        for (fy, etype), j in zip(cols, total_col):
            if j < len(row):
                v = c.num(row[j])
                if v is not None:
                    values[(fy, etype)] = v
        cells = [t for t in texts[i][:money_from] if t]
        item, code, words = "", "", []
        for t in cells:
            if not item and not words and normalise_item(t) and \
                    re.fullmatch(r"[\d\s.]+[a-z]?\.?", t, re.I):
                item = normalise_item(t)
            elif not code and CODE.match(t):
                code = t
            elif not code and t.lower() == "total" and not words:
                code = "Total"
            else:
                words.append(t)
        label = c.squeeze(" ".join(words))
        if not item:
            item, label = split_item(label)
        if not item and _section_end(label, st):
            break
        st.lines.append(Line(item=item, label=label, code=code, values=values))
    classify(st)
    return st


def _section_end(label: str, st: Statement) -> bool:
    """Part B (developmental heads) and C (plan outlay) restate part A."""
    if any(re.match(r"(?i)^grand\s*total", ln.label) for ln in st.lines):
        return True
    if not any(ln.item for ln in st.lines):
        return False
    # 'B. Developmental Heads', 'C.Plan Outlay' -- but not 'B.E. 2016-2017',
    # the 2016-17 statements' heading for their restructured scheme list.
    return bool(re.match(r"^[BC]\s*\.\s*[A-Z][a-z]", label) or re.match(
        r"(?i)^plan outlay|^dev\.?\s*support|^central plan$|^head of budget",
        label))


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

FOOTER = re.compile(r"(?i)^(no\.?\s*\d+\s*/|https?://|www\.|indiabudget|notes on "
                    r"demands|\d{1,4}$|statement of budget estimates)")
MARK = re.compile(r"^[*@#$]+\)?$")
SUB_COLUMN = re.compile(r"^(non\s*-?\s*plan|plan|total|revenue|capital)$", re.I)


def _pdf_header(rows, edition_fy):
    """-> (header row index, columns, Total-anchor x per group) or None."""
    import parse_union_pdf as P
    for j, row in enumerate(rows[:30]):
        sub = [w for w in row if SUB_COLUMN.match(w["text"])]
        tot = [n for n, w in enumerate(sub) if w["text"].lower() == "total"]
        if len(tot) < 3 or len(sub) != 3 * len(tot):
            continue
        if any(not sub[n]["text"].lower() == "total" for n in range(2, len(sub), 3)):
            continue
        cols = expected_columns(edition_fy, len(tot))
        if cols is None:
            return None
        # Check whatever years the header did extract against the shape.
        anchors = [P.centre(w) for w in sub]
        groups = [sum(anchors[g:g + 3]) / 3 for g in range(0, len(anchors), 3)]
        for k in range(max(0, j - 4), j + 1):
            for w in rows[k]:
                m = P.FY_TOKEN.match(w["text"])
                if not m:
                    continue
                try:
                    fy = c.fy_normalise(w["text"])
                except ValueError:
                    continue
                g = P.nearest(P.centre(w), groups)
                if sum(1 for x in rows[k] if P.FY_TOKEN.match(x["text"])) >= 2 \
                        and fy != cols[g][0]:
                    return None
        return j, cols, anchors
    return None


def _has_grand_total(rows) -> bool:
    return any(re.match(r"(?i)^grand\s*total", " ".join(w["text"] for w in r))
               for r in rows)


def read_pdf(path: Path, edition_fy: str, demand: int, url: str) -> Statement:
    import pdfplumber
    import parse_union_pdf as P

    pages, first_text, done = [], "", False
    with pdfplumber.open(path) as pdf:
        for k, page in enumerate(pdf.pages):
            if k == 0:
                first_text = page.extract_text() or ""
            rows = P.page_lines(page)
            h = _pdf_header(rows, edition_fy)
            if h is None:
                # The older editions print the column header on the first
                # page only; a continuation page is the same table.
                if pages and not done:
                    prev = pages[-1]
                    pages.append((rows, -1, prev[2], prev[3], prev[4]))
                    done = _has_grand_total(rows)
                continue
            header, cols, anchors = h
            index = list(range(2, len(anchors), 3))
            pages.append((rows, header, cols, index, anchors))
            done = _has_grand_total(rows[header + 1:])
    if not pages:
        raise ValueError("no page with a Plan/Non-Plan/Total header")
    cols = pages[0][2]
    if any(p[2] != cols for p in pages):
        raise ValueError("pages disagree on the columns")
    # Item numbers ('34.10', '10.1') look exactly like amounts, and in a
    # statement with a long North East block there are enough of them to
    # form a column of their own at the left margin, which money_columns
    # then rejects as one column too many. Nothing left of the first money
    # column is money, so the clustering never sees it; the words stay in
    # the rows for the labels.
    margin = min(pages[0][4]) - 45.0
    clustered = [([[w for w in r if w["x1"] >= margin or not P.is_amount(w["text"])]
                   for r in rows], h, cl, ix, an)
                 for rows, h, cl, ix, an in pages]
    edges = P.money_columns(clustered, pages[0][4])
    if edges is None:
        raise ValueError("could not place the money columns")
    code_at = P.code_column(clustered, edges)
    index = pages[0][3]

    ministry, dept = _title(first_text.splitlines()[:8])
    st = Statement(edition=edition_fy, demand=demand, ministry=ministry,
                   dept=dept, columns=cols, top={}, source_url=url)
    live = [i for i, e in enumerate(edges) if e is not None]
    stop = False
    for rows, header, _, _, _ in pages:
        for row in rows[header + 1:]:
            amounts, words = {}, []
            for w in [part for v in row for part in P.unglue_code(v, code_at)]:
                if P.is_amount(w["text"]) and live:
                    col = live[P.nearest(w["x1"], [edges[i] for i in live])]
                    tol = P.NIL_TOL if P.NIL.match(w["text"]) else P.EDGE_TOL
                    if abs(w["x1"] - edges[col]) <= tol:
                        v = c.num(w["text"])
                        if v is not None and col not in amounts:
                            amounts[col] = v
                        continue
                if MARK.match(w["text"]):
                    continue
                words.append(w)
            code = ""
            if code_at is not None:
                for w in words:
                    if CODE.match(w["text"]) and abs(w["x1"] - code_at) <= P.EDGE_TOL:
                        code = w["text"]
                        break
            else:
                code = next((w["text"] for w in words
                             if CODE.match(w["text"]) and w is not words[0]), "")
            label_words = [w for w in words if not (code and w["text"] == code)]
            label = c.squeeze(" ".join(w["text"] for w in label_words))
            values = {cols[n]: amounts[i] for n, i in enumerate(index)
                      if i in amounts}
            if not values and FOOTER.match(label):
                continue
            # A lone 'Total' at the major-head column is a scheme's total line.
            if label.lower() == "total" and code_at is not None and label_words \
                    and label_words[0]["x0"] > code_at - 60:
                code, label = "Total", ""
            item, rest = split_item(label)
            if not item and _section_end(rest, st):
                stop = True
                break
            x0 = label_words[0]["x0"] if label_words else None
            named = [w for w in label_words
                     if sum(ch.isalpha() for ch in w["text"]) >= 2]
            tx = named[0]["x0"] if named else x0
            st.lines.append(Line(item=item, label=rest, code=code, values=values,
                                 x0=x0, tx=tx))
        if stop:
            break
    classify(st, wrapped=True)
    return st


# --------------------------------------------------------------------------- #
# Classification: which lines are leaves
# --------------------------------------------------------------------------- #


def classify(st: Statement, wrapped: bool = False) -> None:
    """Mark every line, attach continuations to their item, check the sums.

    `wrapped` is for PDFs, where a scheme's name runs over several printed
    lines and its tail can sit on the line of its second major head
    ('Institutions 3601 428.70') or on a line of its own below its figures
    ('5. National Programme of Mid Day 2202 14.77' / 'Meals in Schools', the
    2014-15 layout). In a workbook the name is one cell.

    What decides it in a PDF is where the line starts. A wrapped name
    continues at its item's text indent, the x where the name begins after
    the number. A section heading ('General Education') starts at the number
    column instead. So does an unnumbered item: the 2008-09 to 2010-11
    statements print 'Amount met from Prarambhik Shiksha' with no number,
    and its figures on the next line, at the text indent. Folded into the
    item above it, that line nets the whole Kosh off the Sarva Shiksha
    Abhiyan. So a figureless line at the number column is held as a heading
    until a wrap arrives for it, which makes it an item of its own.
    """
    TOL = 3.5
    lines = st.lines
    # 1. The top block: Revenue/Capital/Total (Plan era) or
    #    Gross/Recoveries/Receipts/Net, printed before the first item.
    first_item = next((k for k, ln in enumerate(lines) if ln.item), len(lines))
    for ln in lines[:first_item]:
        key = (ln.label or ln.code).lower()
        if key in TOP_LABELS and ln.values:
            st.top[key] = ln.values
            ln.kind = "top"
    # 2. Items with children are parents; their own figures (where printed)
    #    restate their children.
    items = [ln.item for ln in lines if ln.item]
    parents = {i for i in items if any(o.startswith(i + ".") for o in items)}
    numbered_x = sorted(ln.x0 for ln in lines if ln.item and ln.x0 is not None)
    num_col = numbered_x[len(numbered_x) // 2] if numbered_x else None
    text_x = sorted(ln.tx for ln in lines if ln.item and ln.tx is not None
                    and ln.x0 is not None and abs(ln.x0 - (num_col or 0)) <= TOL)
    text_col = text_x[len(text_x) // 2] if text_x else None

    def at(x, ref):
        return x is not None and ref is not None and abs(x - ref) <= TOL

    current, held = -1, -1
    for k, ln in enumerate(lines):
        if ln.kind == "top":
            continue
        lab = ln.label.lower()
        if ln.item:
            current, held = k, -1
            ln.kind = "parent" if ln.item in parents else (
                "leaf" if ln.values else "item")
            continue
        if re.match(r"^grand\s*total", lab):
            ln.kind = "grand_total"
            if not st.grand_total:
                st.grand_total = ln.values
            held = -1
            continue
        if ln.code == "Total" or lab == "total":
            ln.kind, ln.owner = "item_total", current
            held = -1
            continue
        if re.match(r"^total\b", lab):
            ln.kind, held = "group_total", -1
            continue
        if lab == "net":
            ln.kind, ln.owner = "net", current
            held = -1
            continue
        if wrapped and ln.label and held >= 0 and at(ln.x0, text_col):
            # The wrap that turns a held heading into an unnumbered item.
            h = lines[held]
            h.item, h.kind = "u%d" % held, "item"
            h.label = c.squeeze(h.label + " " + ln.label)
            current, held = held, -1
            if not ln.values:
                ln.kind = "wrap"
                continue
            ln.kind, ln.owner = "leaf", current
            if not ln.code:
                ln.kind = "orphan_total"
            elif h.kind == "item":
                h.kind = "head"
            continue
        if wrapped and ln.label and current >= 0 and at(ln.x0, lines[current].tx):
            # The next line of the current item's name.
            owner = lines[current]
            owner.label = c.squeeze(owner.label + " " + ln.label)
            if not ln.values:
                ln.kind = "wrap"
                continue
            if not ln.code:
                ln.kind = "orphan_total"
                continue
            ln.kind, ln.owner = "leaf", current
            if owner.kind == "item":
                owner.kind = "head"
            continue
        if not ln.values:
            if wrapped and ln.label and at(ln.x0, num_col):
                held = k
            ln.kind = "heading"
            continue
        held = -1
        if not wrapped and not ln.label and not ln.code:
            # A workbook row of figures with no label at all is a line of its
            # own whose label cell is empty, never a part of the item above:
            # under 'Transfer to Prarambhik Shiksha Kosh' it is the 'Amount
            # met from' line that cancels it (2023-24), under National Bal
            # Bhawan a block of recoveries (2026-27). Each is followed by its
            # own 'Net'. Credited to the item above, it made National Bal
            # Bhawan's 2024-25 actual -525.42 instead of 24.33.
            ln.item, ln.kind, current = "u%d" % k, "leaf", k
            continue
        if wrapped and ln.label and ln.code and at(ln.x0, num_col):
            # An unnumbered item printed with its figures on its first line:
            # 'Amount met from Prarambhik Shiksha 2202 -6560.00' (2007-08).
            ln.item, ln.kind, current = "u%d" % k, "leaf", k
            continue
        if wrapped and not ln.code:
            # In a PDF every real leaf carries its major head. A line of
            # figures without one is a wrapped total whose figures landed on
            # the next printed line: 'Total-Information and' / 'Communication
            # Technology' / then the figures, joined by page_lines to the
            # heading 'Development of Languages' below them.
            ln.kind = "orphan_total"
            continue
        # A line with figures and no number of its own: the next major head of
        # the current item, or an unlabelled recovery under it.
        ln.kind, ln.owner = "leaf", current
        if current >= 0:
            owner = lines[current]
            if ln.label:
                owner.label = c.squeeze(owner.label + " " + ln.label)
            if owner.kind == "item":
                owner.kind = "head"
    # 3. The invariant.
    if not st.grand_total:
        # The 1998-99 to 2002-03 statements often print no Grand Total: the
        # table runs out on its last section total and part C begins. The
        # top block is then the only statement of the whole, and the leaves
        # are checked against it.
        st.grand_total = dict(st.top.get("net") or st.top.get("total") or {})
    leaf_sum = {}
    for ln in lines:
        if ln.kind == "leaf":
            for k, v in ln.values.items():
                leaf_sum[k] = leaf_sum.get(k, 0.0) + v
    top_total = st.top.get("net") or st.top.get("total") or {}
    for col in st.columns:
        gt = st.grand_total.get(col)
        ls = leaf_sum.get(col, 0.0)
        if gt is None:
            st.problems.append("%s %s: no Grand Total" % col)
            continue
        tt = top_total.get(col)
        if (tt is not None and abs(ls - tt) <= LEAF_TOL
                and abs(tt - gt) > LEAF_TOL):
            # Two independent statements of the whole agree and the third,
            # the printed Grand Total, does not: a misprint in the document.
            # Demand 47 of 1999-00 prints 7934.74 under a top block and a
            # column of schemes that both come to 7936.74.
            st.notes.append("%s %s: printed Grand Total %.2f disagrees with "
                            "the top block and the schemes, both %.2f"
                            % (col[0], col[1], gt, tt))
            continue
        if abs(ls - gt) > LEAF_TOL:
            st.problems.append("%s %s: leaves %.2f != Grand Total %.2f"
                               % (col[0], col[1], ls, gt))
        if tt is not None and abs(tt - gt) > LEAF_TOL:
            st.problems.append("%s %s: top block %.2f != Grand Total %.2f"
                               % (col[0], col[1], tt, gt))


def item_values(st: Statement):
    """{line index of an item: {(fy, etype): sum of its own leaves}}.

    A parent's value includes its children's leaves; an item's includes the
    leaves on its continuation lines.
    """
    lines = st.lines
    own = {}
    for k, ln in enumerate(lines):
        if ln.kind == "leaf":
            key = k if ln.item else ln.owner
            if key < 0:
                continue
            d = own.setdefault(key, {})
            for col, v in ln.values.items():
                d[col] = d.get(col, 0.0) + v
    by_item = {ln.item: k for k, ln in enumerate(lines) if ln.item}
    out = {}
    for k, ln in enumerate(lines):
        if not ln.item:
            continue
        total = dict(own.get(k, {}))
        if ln.kind == "parent":
            for other, j in by_item.items():
                if other.startswith(ln.item + "."):
                    for col, v in own.get(j, {}).items():
                        total[col] = total.get(col, 0.0) + v
        out[k] = total
    return out


def parent_of(item: str, items) -> str:
    """The nearest enclosing item number that the statement actually prints."""
    parts = item.split(".")
    for n in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:n])
        if cand in items:
            return cand
    return ""


def read(path: Path, edition_fy: str, demand: int, url: str) -> Statement:
    if path.suffix == ".pdf":
        return read_pdf(path, edition_fy, demand, url)
    return read_excel(path, edition_fy, demand, url)


def title_of(path: Path) -> str:
    """The department or ministry a statement is for, without parsing it all."""
    if path.suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""
        return " | ".join(_title(text.splitlines()[:8]))
    grid = _grid(path)
    return " | ".join(_title([v for r in grid[:12] for v in r
                              if isinstance(v, str) and v.strip()]))


# --------------------------------------------------------------------------- #
# CLI: fetching
# --------------------------------------------------------------------------- #

EDU = re.compile(r"(?i)\b(school education|elementary education|secondary "
                 r"education|higher education|department of education)\b")
NOT_EDU = re.compile(r"(?i)agricultur")


def seeds(fy: str):
    """{demand: (department, net total for the budget year)} for the education
    departments, as the demands table has them for this edition. Only a
    starting point: each is confirmed against the statement itself."""
    import csv
    out = {}
    for name in ("union_demands.csv", "union_demands_pdf.csv"):
        path = c.PROCESSED / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["source_edition"] != "ExpBudget " + fy:
                    continue
                d = r["ministry_or_dept"]
                if not EDU.search(d) or NOT_EDU.search(d):
                    continue
                n = int(r["source_page"].split("!dg")[-1])
                net = out.get(n, (d, None))[1]
                if (r["fiscal_year"] == fy and r["estimate_type"] == "BE"
                        and not r["major_head"] and r["account"] in
                        ("net_total", "gross_total")):
                    if r["account"] == "net_total" or net is None:
                        net = float(r["amount_cr"])
                out[n] = (d, net)
    return out


def education_demands(ed: dict, ref: dict):
    """{demand number: department} of the education departments in one edition.

    Each is confirmed from the statement itself, not by trusting a demand
    number from another edition: the numbering is re-cut every few years (see
    FINDINGS.md, "Demand numbers are not identifiers"). The confirmation is
    the statement's own title where it prints one. The 2019-20 and 2020-21
    workbooks print none, so there the statement's net total for the budget
    year has to equal the net total of the same demand in the Demands for
    Grants, to the paisa.
    """
    fy = ed["fiscal_year"]
    if fy in ref["education"]:
        return {int(n): t for n, t in ref["education"][fy].items()}
    seed = seeds(fy)

    def look(n):
        path = fetch(ed, n, ref)
        if path is None:
            return None
        title = title_of(path)
        ref["files"][fy][str(n)]["title"] = title
        if title.strip(" |"):
            ok = EDU.search(title) and not NOT_EDU.search(title)
            return title.split(" | ")[-1] if ok else None
        if n not in seed or seed[n][1] is None:
            return None
        try:
            st = read(path, fy, n, "")
        except ValueError:
            return None
        net = (st.top.get("net") or st.top.get("total") or {}).get((fy, "BE"))
        if net is not None and abs(net - seed[n][1]) < 0.01:
            ref["files"][fy][str(n)]["title"] = "(no title; net %.2f = dg%d) | %s" % (
                net, n, seed[n][0])
            return seed[n][0]
        return None

    found = {}
    if seed:
        # The neighbours too: 2008-09's Higher Education demand is missing
        # from the demands table because its dg58.pdf is encrypted.
        for n in sorted(set(seed) | {s + d for s in seed for d in (-1, 1)}):
            t = look(n)
            if t:
                found[n] = t
    if not found:
        misses = 0
        for n in list(range(40, 75)) + list(range(1, 40)) + list(range(75, 121)):
            t = look(n)
            if t:
                found[n], misses = t, 0
            elif found:
                misses += 1
                if misses >= 3:
                    break
    ref["education"][fy] = {str(n): t for n, t in sorted(found.items())}
    return found


def all_demands(ed: dict, ref: dict, max_n: int = 120, stop_after: int = 4):
    got, misses = {}, 0
    for n in range(1, max_n + 1):
        path = fetch(ed, n, ref)
        if path is None:
            misses += 1
            if misses >= stop_after and got:
                break
            continue
        misses = 0
        got[n] = path
    return got


def main(argv) -> None:
    if not argv:
        raise SystemExit(__doc__)
    cmd, years = argv[0], [c.fy_normalise(a) for a in argv[1:]]
    ref = load_ref()
    eds = [e for e in editions() if c.fy_start(e["fiscal_year"]) >= 1998
           and (not years or e["fiscal_year"] in years)]
    try:
        for ed in eds:
            if cmd == "fetch-education":
                found = education_demands(ed, ref)
                print("  %-9s %s" % (ed["fiscal_year"],
                                     "; ".join("%d %s" % kv for kv in sorted(found.items()))))
            elif cmd == "fetch-all":
                got = all_demands(ed, ref)
                print("  %-9s %d statements" % (ed["fiscal_year"], len(got)))
            else:
                raise SystemExit("unknown command %r" % cmd)
    finally:
        save_ref(ref)


if __name__ == "__main__":
    main(sys.argv[1:])

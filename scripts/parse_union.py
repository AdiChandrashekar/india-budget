"""Parse the Union alldg workbooks into the long table.

Each edition's alldg.xlsx holds one sheet per Demand for Grants. A sheet looks
like this (column letters as the site ships them):

      C                              D            E       F       G       H
      REVENUE SECTION                Major Head   t-2 A   t-1 BE  t-1 RE  t BE
      General Education              2202          ...     ...     ...    ...
      Grants-in-aid to State Govts   3601          ...     ...     ...    ...
      Total-Revenue Section                        ...
      CAPITAL SECTION
      Capital Outlay on ...          4202          ...
      Total-Capital Section                        ...
      GRAND TOTAL                                  ...          <- gross
      Revenue Section                              ...          <- recoveries,
      General Education              2202         -...             already
      Total-Revenue Section                       -...             negative
                                     Total        ...           <- net of them

Three things matter and are easy to get wrong:

1.  Row offsets differ between sheets, so every landmark is found by its text,
    never by a fixed row number.
2.  The block after GRAND TOTAL repeats the section headings, but those rows
    are receipts netted against expenditure. They are tagged basis=recovery;
    gross + recovery = net.
3.  One edition gives four fiscal years: actuals for t-2, BE and RE for t-1,
    and BE for t. Stitching editions is what produces a long series, and it is
    also why the same (year, estimate_type) can arrive from two editions. The
    later edition wins; see pick_best().

    python scripts/parse_union.py

Writes data/processed/union_demands.csv and data/reference/union_ministries.json.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

try:
    import openpyxl
except ImportError:
    raise SystemExit("openpyxl is required: python -m pip install openpyxl")

ESTIMATE_WORDS = [
    (re.compile(r"\bactual", re.I), "A"),
    (re.compile(r"\brevised\s+estimate", re.I), "RE"),
    (re.compile(r"\bbudget\s+estimate", re.I), "BE"),
]

FY_IN_TEXT = re.compile(r"((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})")
MAJOR_HEAD = re.compile(r"^(\d{4})$")

SECTION_HEAD = re.compile(r"^(revenue|capital)\s+section$", re.I)
SECTION_TOTAL = re.compile(r"^total\s*-?\s*(revenue|capital)\s+section$", re.I)
GRAND_TOTAL = re.compile(r"^grand\s+total$", re.I)
NET_LABEL = re.compile(r"^(revenue|capital|total)$", re.I)
DEMAND_NO = re.compile(r"(?:DEMAND\s+)?NO\.?\s*(\d+)", re.I)

# The two departments that make up the Ministry of Education. Kept as a
# reference list because the demand numbers move between editions and the
# ministry was MHRD until 2020.
MOE_DEPARTMENTS = (
    "school education",
    "higher education",
    "elementary education",      # pre-2018 department names
    "secondary education",
)


def year_columns(rows):
    """Find the year header row; return {column index: (fiscal_year, type)}."""
    for idx, row in enumerate(rows):
        cols = {}
        for j, raw in enumerate(row):
            text = c.latin_part(raw)
            if not text:
                continue
            m = FY_IN_TEXT.search(text)
            if not m:
                continue
            etype = next((tag for pat, tag in ESTIMATE_WORDS if pat.search(text)), None)
            if not etype:
                continue
            try:
                fy = c.fy_normalise(m.group(0))
            except ValueError:
                continue
            cols[j] = (fy, etype)
        if len(cols) >= 3:
            return idx, cols
    return None, {}


def sheet_header(rows):
    """Demand number, department name and whether this is an Appropriation.

    Appropriation sheets (interest payments, the Supreme Court, repayment of
    debt) are headed only 'NO. 39 (APPROPRIATION)' in English, because the
    word for Demand appears there only in Devanagari. They are part of the
    budget and must not be skipped.
    """
    demand_no, dept, appropriation = None, "", False
    for row in rows:
        for raw in row:
            text = c.latin_part(raw)
            if not text:
                continue
            if "APPROPRIATION" in text.upper():
                appropriation = True
            m = DEMAND_NO.search(text)
            if m and demand_no is None:
                demand_no = int(m.group(1))
                continue
            if demand_no is not None and not dept:
                letters = re.sub(r"[^A-Za-z]", "", text)
                if len(letters) > 5 and letters.isupper():
                    dept = re.sub(r"\(.*?\)", "", text).strip().title()
    return demand_no, dept, appropriation


# Rows that break a head down by who authorises it, repeating the amount above.
SUBTOTAL_LABEL = re.compile(r"^(charged|voted)$", re.I)


def parse_sheet(ws, edition_fy: str, source_url: str):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr_idx, cols = year_columns(rows)
    if not cols:
        return [], "no year header"

    # Everything left of the first amount column is label or code; everything
    # from it rightwards is money. Anchoring on this is the only reliable way
    # to tell a head name from a number, because a numeric cell stringifies
    # into something that looks like text.
    first_amt = min(cols)
    demand_no, dept, appropriation = sheet_header(rows[:hdr_idx])
    if demand_no is None:
        return [], "no demand number"

    out = []
    section = ""
    basis = "gross"
    edition = "ExpBudget " + edition_fy
    seen = {}

    def emit(account, amounts, *, major_head="", head_name="", definition):
        slot = (account, major_head, head_name)
        seen[slot] = seen.get(slot, 0) + 1
        nth = seen[slot]
        for j, (fy, etype) in cols.items():
            v = c.num(amounts[j]) if j < len(amounts) else None
            if v is None:
                continue
            out.append(c.Row(
                fiscal_year=fy, govt="union", estimate_type=etype,
                source_edition=edition, definition=definition,
                major_head=major_head, ministry_or_dept=dept,
                scheme=head_name, account=account, amount_cr=v,
                occurrence=nth, source_url=source_url,
                source_page="%s!dg%d" % (edition_fy, demand_no),
            ))

    for row in rows[hdr_idx + 1:]:
        head = [c.latin_part(v) for v in row[:first_amt]]
        code = next((t for t in head if MAJOR_HEAD.match(t)), "")
        named = [t for t in head if re.search(r"[A-Za-z]", t)]
        label = max(named, key=len) if named else ""

        if not label:
            continue
        if SUBTOTAL_LABEL.match(label):
            continue                    # repeats the head above it
        if SECTION_TOTAL.match(label):
            section = SECTION_TOTAL.match(label).group(1).lower()
            emit("%s_%s" % (basis, section), row, definition="whole")
            continue
        if SECTION_HEAD.match(label):
            section = SECTION_HEAD.match(label).group(1).lower()
            continue
        if GRAND_TOTAL.match(label):
            emit("gross_total", row, definition="whole")
            basis = "recovery"          # everything below is netted-off receipts
            continue
        if code:
            emit("%s_%s" % (basis, section or "revenue"), row,
                 major_head=code, head_name=label, definition="functional")
            continue
        # The closing block, after the recoveries: bare Revenue / Capital /
        # Total, which is the demand net of them.
        if NET_LABEL.match(label) and basis == "recovery":
            emit("net_" + label.lower(), row, definition="whole")

    # A demand with nothing netted against it prints no closing block, because
    # its gross *is* its net. Say so explicitly rather than leaving every
    # consumer to rediscover the rule: without this, summing net_total across
    # demands silently drops the 8 demands that have no recoveries, and the
    # Union total comes out about 5% light.
    if not any(r.account.startswith("net_") for r in out):
        for r in list(out):
            # Section and grand totals only: a major-head line shares the
            # account name but is a component, not a total.
            if r.definition == "whole" and not r.major_head and \
                    r.account in ("gross_total", "gross_revenue", "gross_capital"):
                clone = c.Row(**{k: v for k, v in r.__dict__.items()})
                clone.account = "net_" + r.account.split("_", 1)[1]
                out.append(clone)

    return out, ""


def has_name(text) -> bool:
    """Does this cell hold a real name, or just punctuation?

    Several rows in the summary workbook are Devanagari only. Stripping the
    Devanagari leaves a stray '-' or ',', which is not a department name and
    must not be allowed to overwrite the one on the demand's own sheet.
    """
    return len(re.sub(r"[^A-Za-z]", "", str(text))) >= 3


def parse_ministries(path: Path, edition_fy: str):
    """demand number -> {department, ministry} from dgsum.xlsx."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    mapping, ministry = {}, ""
    for row in ws.iter_rows(values_only=True):
        cells = [c.latin_part(v) for v in row]
        serial = next((t for t in cells[:1] if t), "")
        texts = [t for t in cells[1:] if t]
        if not texts:
            continue
        # A ministry heading: no serial number, one piece of text, no amounts.
        nums = [c.num(v) for v in row]
        has_amount = any(v is not None for v in nums[6:])
        if not serial.strip().isdigit() and len(texts) == 1 and not has_amount:
            if has_name(texts[0]) and len(texts[0]) >= 4:
                ministry = texts[0]
            continue
        if serial.strip().isdigit():
            demand = next((int(t) for t in texts if t.strip().isdigit()), None)
            name = next((t for t in texts if not t.strip().isdigit()), "")
            if demand is not None and has_name(name):
                mapping[demand] = {"department": name,
                                   "ministry": ministry or name}
    wb.close()
    return mapping


def pick_best(rows):
    """Resolve the overlap between editions, one whole demand-year at a time.

    Editions overlap by design: each reports four years, so up to three of them
    describe the same (year, estimate_type) for the same demand. The later
    edition is the more revised, so it wins.

    The unit of choice is the whole (year, estimate_type, demand) group, not
    the individual line. Matching line by line looks tidier but is wrong: the
    documents do not always lay a demand out the same way twice. Demand 40
    (Repayment of Debt) nets its receipts off under one note in the 2026-27
    edition and two in the 2025-26 one, so a line-level merge kept a line from
    each and double-counted Rs 90 lakh crore. Taking the group whole means a
    demand-year is always internally consistent, because it comes from a
    single published statement.
    """
    owner = {}
    for r in rows:
        key = (r.fiscal_year, r.estimate_type, r.source_page.split("!")[-1])
        edition = c.fy_start(r.source_edition.split()[-1])
        if key not in owner or edition > owner[key]:
            owner[key] = edition
    return [r for r in rows
            if owner[(r.fiscal_year, r.estimate_type,
                      r.source_page.split("!")[-1])]
            == c.fy_start(r.source_edition.split()[-1])]


def main(argv) -> None:
    editions = c.read_json(c.REFERENCE / "union_editions.json")
    have = []
    for ed in editions:
        path = c.RAW / "union" / ed["fiscal_year"] / "alldg.xlsx"
        if path.exists() and not ed["interim"]:
            have.append((ed, path))
    if not have:
        raise SystemExit("no raw workbooks; run scripts/fetch_union.py first")

    all_rows, ministries, problems = [], {}, []
    for ed, path in have:
        fy = ed["fiscal_year"]
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        url = ed["eb_base"] + "alldg.xlsx"
        n_before = len(all_rows)
        names = list(wb.sheetnames)
        for name in names:
            rows, why = parse_sheet(wb[name], fy, url)
            if why:
                problems.append("%s %s: %s" % (fy, name, why))
            all_rows += rows
        wb.close()

        dgsum = path.parent / "dgsum.xlsx"
        if dgsum.exists():
            ministries[fy] = parse_ministries(dgsum, fy)

        print("  %-9s %3d sheets  %6d rows" % (
            fy, len(names), len(all_rows) - n_before))

    if problems:
        print("\n%d sheets could not be parsed:" % len(problems))
        for p in problems[:12]:
            print("   ", p)

    # Prefer the department name from that edition's own summary, which is
    # cleaner than the all-caps sheet heading. The ministry a demand belongs to
    # lives in union_ministries.json, keyed by edition and demand number, so
    # the site can group demands without duplicating the string on every row.
    for r in all_rows:
        edition_fy = r.source_edition.split()[-1]
        demand = r.source_page.split("!dg")[-1]
        if demand.isdigit():
            info = ministries.get(edition_fy, {}).get(int(demand))
            if info and has_name(info["department"]):
                r.ministry_or_dept = info["department"]

    rows = pick_best(all_rows)
    rows.sort(key=lambda r: (r.fiscal_year, r.source_page, r.account, r.major_head))
    c.write_long_table(rows, c.PROCESSED / "union_demands.csv")

    if ministries:
        c.write_json(ministries, c.REFERENCE / "union_ministries.json")

    years = sorted({r.fiscal_year for r in rows})
    print("\nfiscal years covered: %s .. %s (%d)" % (years[0], years[-1], len(years)))
    for etype in ("A", "RE", "BE"):
        ys = sorted({r.fiscal_year for r in rows if r.estimate_type == etype})
        print("  %-3s %s" % (etype, ", ".join(ys) if ys else "-"))


if __name__ == "__main__":
    main(sys.argv[1:])

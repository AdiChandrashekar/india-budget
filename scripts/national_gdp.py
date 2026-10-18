"""National GDP at current prices, one segment per base year, never spliced.

    python scripts/national_gdp.py            # discover + fetch + parse
    python scripts/national_gdp.py --offline  # parse what is already in data/raw/gdp

Writes data/reference/gdp_editions.json (the verified edition map),
data/raw/gdp/ (the workbooks + manifest.csv) and data/gdp.json.

Source: RBI's Handbook of Statistics on the Indian Economy, Table 1,
"Macro-Economic Aggregates (At Current Prices)", which reprints the National
Statistics Office's national accounts. One edition is not enough, and the
reason is the whole design of this script:

*   Since 2018 each edition carries only the latest seven years. The 2026
    edition starts at 2020-21; 2011-12 is last printed by the 2018 edition.
*   The 2017 edition is the last to carry the long 2004-05-base table, which
    runs from 1966-67 to 2011-12.
*   India's national accounts have been rebased twice in the span the site
    covers: to 2011-12 (released January 2015) and to 2022-23 (released
    February 2026). A rebasing is not a revision of a few numbers. It changes
    the methodology, the data sources and the level: 2011-12 is Rs 90.10 lakh
    crore on the old base and Rs 87.36 lakh crore on the new one, and 2022-23
    is Rs 268.90 lakh crore on the 2011-12 base and Rs 261.18 lakh crore on
    the 2022-23 one. A ratio computed on one base and compared with a ratio on
    another moves for reasons that have nothing to do with the numerator.

So the output keeps each base as its own segment. The overlap years (2011-12
and 2022-23) carry both values; a `preferred` series picks the newest base
for each year and records the break, so a chart can draw a gap or a marker
there instead of a line that pretends the series is one. Nothing is chained
or rescaled.

Within a base, each year is taken from the newest edition that prints it,
because national accounts estimates are revised for three years after first
release (provisional -> first, second, third revised). The edition and the
estimate's vintage are recorded per year.

Discovery reads the live Handbook index and its year archive, which is an
ASP.NET postback rather than a link, and verifies each workbook by magic
number before fetching -- see FINDINGS.md for why status codes are not
trusted on rbidocs.rbi.org.in.
"""

from __future__ import annotations

import argparse
import html as htmllib
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

INDEX = ("https://rbi.org.in/Scripts/AnnualPublications.aspx"
         "?head=Handbook+of+Statistics+on+Indian+Economy")
RAW = c.RAW / "gdp"
EDITIONS_REF = c.REFERENCE / "gdp_editions.json"
OUT = c.ROOT / "data" / "gdp.json"

# Publication years of the Handbook to read. 2017 is the last edition with
# the 2004-05-base long table; from 2018 every edition carries seven years.
# Each later edition is needed for exactly the years it is the newest source
# of, so none of these can be dropped without a hole appearing.
EDITION_YEARS = list(range(2017, 2027))
CURRENT_YEAR = 2026      # the edition the index serves without a postback

FIRST_NEEDED = "1990-91"  # the state series starts here

ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
LINK = re.compile(r"""href\s*=\s*["']?([^"' >]+\.(?:xlsx|xls))["' >]""", re.I)
TABLE1 = re.compile(r"(?i)^Table 1\s*:\s*Macro-Economic Aggregates.*Current Prices")

BASES = ("2004-05", "2011-12", "2022-23")


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def _hidden_fields(page: str) -> dict:
    fields = {}
    for tag in re.findall(r"<input[^>]*>", page, re.I):
        if not re.search(r'type="hidden"', tag, re.I):
            continue
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = htmllib.unescape(value.group(1) if value else "")
    return fields


def index_for_year(year: int, base_page: str) -> str:
    """The index as it stands for one publication year.

    The year tree on the page is `onclick=GetYear("2017")`, which sets a
    hidden field and clicks a hidden submit button: an ASP.NET postback. There
    is no URL for an older edition, so the form is posted back exactly as the
    page's own script would.
    """
    if year == CURRENT_YEAR:
        return base_page
    fields = _hidden_fields(base_page)
    if "hdnYear" not in fields:
        raise SystemExit("the Handbook index has no hdnYear field; the archive "
                         "mechanism has changed")
    fields["hdnYear"] = str(year)
    fields["UsrFontCntr$btn"] = ""
    req = urllib.request.Request(
        INDEX, data=urllib.parse.urlencode(fields).encode(),
        headers={"User-Agent": c.BROWSER_UA, "Referer": INDEX,
                 "Content-Type": "application/x-www-form-urlencoded"})
    with c._OPENER.open(req, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")


def table1_link(page: str):
    for m in ROW.finditer(page):
        row = m.group(1)
        label = c.squeeze(TAG.sub(" ", htmllib.unescape(row)))
        label = re.sub(r"(\s*\d+\s*kb\s*)+$", "", label, flags=re.I).strip()
        if TABLE1.match(label):
            link = LINK.search(row)
            if link:
                return label, link.group(1)
    return None, None


def discover() -> dict:
    base_page = c.warm(INDEX)
    if not base_page:
        raise SystemExit("could not read %s" % INDEX)
    editions = {}
    for year in EDITION_YEARS:
        page = index_for_year(year, base_page)
        label, url = table1_link(page)
        if not url:
            raise SystemExit("the %d Handbook lists no Table 1 workbook" % year)
        ok = c.doc_ok(url, referer=INDEX)
        print("  %d  %-4s %s" % (year, "ok" if ok else "FAIL", label[:70]))
        if not ok:
            raise SystemExit("%s does not serve a workbook" % url)
        editions[str(year)] = {
            "label": label, "url": url,
            "checked": time.strftime("%Y-%m-%d", time.gmtime()),
        }
    payload = {
        "generated": time.strftime("%Y-%m-%d", time.gmtime()),
        "index": INDEX,
        "note": ("Handbook of Statistics on the Indian Economy, Table 1, one "
                 "workbook per publication year. Older years are reached by "
                 "the index's ASP.NET postback (hdnYear), not by URL. Every "
                 "url was verified by a ranged GET and a magic-number check."),
        "editions": editions,
    }
    c.write_json(payload, EDITIONS_REF)
    return payload


def fetch(ref: dict) -> None:
    for year, ed in ref["editions"].items():
        ext = ".xls" if ed["url"].lower().endswith(".xls") else ".xlsx"
        c.fetch_doc(ed["url"], RAW / ("hbie%s_table1%s" % (year, ext)),
                    referer=INDEX)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

UNIT = re.compile(r"(?i)\(\s*amount in\s*(?:₹|`|rs\.?)?\s*(crore|billion)\s*\)")
BASE = re.compile(r"(?i)base\s*year\s*:?\s*((?:19|20)\d{2}-\d{2})")
STATUS = re.compile(
    r"(?i)((?:(?:19|20)\d{2}-\d{2}(?:\s*,\s*|\s+and\s+)?)+)\s+(?:is|are)\s+"
    r"(third revised|second revised|first revised|provisional)")
FY_CELL = re.compile(r"^\s*((?:19|20)\d{2}-\d{2})\s*$")


def _grid(path: Path):
    """The first sheet as {(row, col): value}, 1-based, whatever the format."""
    if path.suffix.lower() == ".xls":
        raise SystemExit("%s: .xls is not expected for the editions read; "
                         "add xlrd support before using it" % path.name)
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    grid = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                grid[(cell.row, cell.column)] = cell.value
    return grid


def _text(grid) -> str:
    return " ".join(str(v) for v in grid.values() if isinstance(v, str))


def _statuses(text: str) -> dict:
    out = {}
    for m in STATUS.finditer(text.replace("\n", " ")):
        for fy in re.findall(r"(?:19|20)\d{2}-\d{2}", m.group(1)):
            out[c.fy_normalise(fy)] = m.group(2).lower() + " estimate"
    return out


def _amount(v):
    n = c.num(v)
    return None if n is None else n


def parse_edition(path: Path, edition: str, url: str):
    """[{fy, base, gdp, gva_or_fc, net_taxes, population, ...}] for one workbook."""
    grid = _grid(path)
    text = _text(grid)
    um = UNIT.search(text)
    if not um:
        raise SystemExit("%s: no '(Amount in ...)' unit line" % path.name)
    unit = um.group(1).lower()
    statuses = _statuses(text)
    rows = max(r for r, _ in grid)
    cols = max(col for _, col in grid)

    def cell(r, col):
        return grid.get((r, col))

    def label(r):
        for col in range(1, 4):
            v = cell(r, col)
            if isinstance(v, str) and v.strip():
                return c.squeeze(v)
        return ""

    out = []
    # Layout A (2018 on): items down the side, years across the top.
    header = None
    for r in range(1, min(rows, 15) + 1):
        if re.match(r"(?i)item\s*/\s*year", label(r)):
            header = r
            break
    if header is not None:
        years = {col: c.fy_normalise(cell(header, col))
                 for col in range(1, cols + 1)
                 if isinstance(cell(header, col), str)
                 and FY_CELL.match(cell(header, col))}
        # Base: a "(Base Year: ...)" cell in the rows under the header applies
        # from its own column rightwards until the next one; otherwise the
        # title carries a single base for the whole table.
        markers = sorted((col, BASE.search(str(cell(r, col))).group(1))
                         for r in range(header + 1, header + 3)
                         for col in range(1, cols + 1)
                         if cell(r, col) is not None
                         and BASE.search(str(cell(r, col))))
        title_base = None
        for r in range(1, header):
            for col in range(1, cols + 1):
                m = BASE.search(str(cell(r, col) or ""))
                if m:
                    title_base = m.group(1)
        if not markers and not title_base:
            # 2020-2022 editions print no base anywhere; their notes say
            # nothing either. They sit wholly inside the 2011-12 base era
            # (Jan 2015 - Feb 2026), which the cross-edition agreement check
            # below confirms value by value against the editions that do
            # state it.
            title_base = "2011-12"
        rows_by = {}
        for r in range(header + 1, rows + 1):
            lab = label(r).lower()
            for key, pat in (("gdp", r"^gross domestic product"),
                             ("gva", r"^gva at basic prices"),
                             ("net_taxes", r"^net taxes on products"),
                             ("population", r"^population"),
                             ("per_capita_gdp", r"^per capita gdp")):
                if re.match(pat, lab) and key not in rows_by:
                    rows_by[key] = r
        if "gdp" not in rows_by:
            raise SystemExit("%s: no Gross Domestic Product row" % path.name)
        for col, fy in years.items():
            base = title_base
            for mc, mb in markers:
                if col >= mc:
                    base = mb
            rec = {"fy": fy, "base": base, "edition": edition, "url": url,
                   "unit": unit, "status": statuses.get(fy, "")}
            for key, r in rows_by.items():
                rec[key] = _amount(cell(r, col))
            if rec["gdp"] is None:
                continue
            out.append(rec)
        return out, unit

    # Layout B (2016-2017): years down the side, one block per base year.
    r = 1
    while r <= rows:
        m = BASE.search(label(r))
        if not m:
            r += 1
            continue
        base = m.group(1)
        head = r + 1
        colmap = {}
        for col in range(1, cols + 1):
            v = c.squeeze(cell(head, col) or "").lower()
            if v == "gdp at market prices":
                colmap["gdp"] = col
            elif v in ("gdp at factor cost", "gva at basic prices"):
                colmap["gva"] = col
            elif v == "indirect taxes less subsidies":
                colmap["net_taxes"] = col
            elif v.startswith("population"):
                colmap["population"] = col
        if "gdp" not in colmap:
            raise SystemExit("%s: base %s block has no GDP at Market Prices "
                             "column" % (path.name, base))
        r = head + 1
        while r <= rows and not BASE.search(label(r)):
            lab = label(r)
            fm = FY_CELL.match(lab) if lab else None
            if fm:
                fy = c.fy_normalise(fm.group(1))
                rec = {"fy": fy, "base": base, "edition": edition, "url": url,
                       "unit": unit, "status": statuses.get(fy, "")}
                for key, col in colmap.items():
                    rec[key] = _amount(cell(r, col))
                if rec["gdp"] is not None:
                    out.append(rec)
            r += 1
    return out, unit


def to_crore(rec):
    out = dict(rec)
    for key in ("gdp", "gva", "net_taxes"):
        if out.get(key) is not None:
            out[key] = round(c.to_crore(out[key], out["unit"]), 2)
    return out


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


def check(records, chosen) -> list:
    problems = []
    # 1. GDP = GVA (or GDP at factor cost) + net taxes, as printed. The tables
    #    round each line independently, so allow a few units of the table's
    #    own rounding.
    for rec in records:
        if rec.get("gva") is None or rec.get("net_taxes") is None:
            continue
        tol = 2.0 if rec["unit"] == "crore" else 0.03 * 100
        gap = rec["gdp"] - rec["gva"] - rec["net_taxes"]
        if abs(gap) > tol:
            problems.append("%s %s base %s: GDP %.2f != GVA %.2f + taxes %.2f"
                            % (rec["edition"], rec["fy"], rec["base"],
                               rec["gdp"], rec["gva"], rec["net_taxes"]))
    # 2. Every base is printed under the years its era allows, and nowhere else.
    era = {"2004-05": ("1950-51", "2013-14"), "2011-12": ("2004-05", "2024-25"),
           "2022-23": ("2022-23", "2099-00")}
    for rec in records:
        if rec["base"] not in era:
            problems.append("%s: unknown base %r" % (rec["edition"], rec["base"]))
            continue
        lo, hi = era[rec["base"]]
        if not c.fy_start(lo) <= c.fy_start(rec["fy"]) <= c.fy_start(hi):
            problems.append("%s: %s printed on base %s, outside its era"
                            % (rec["edition"], rec["fy"], rec["base"]))
    # 3. A year whose estimate is final (third revised) does not move between
    #    editions of the same base. This is also what confirms the 2020-22
    #    editions, which print no base, really are on 2011-12.
    final = {}
    for rec in records:
        if rec["status"].startswith("third revised"):
            final[(rec["base"], rec["fy"])] = rec
    for rec in records:
        f = final.get((rec["base"], rec["fy"]))
        if f and int(rec["edition"]) > int(f["edition"]):
            if abs(rec["gdp"] - f["gdp"]) > 1.0:
                problems.append(
                    "%s base %s: final in the %s edition at %.2f but %.2f in "
                    "the %s edition" % (rec["fy"], rec["base"], f["edition"],
                                        f["gdp"], rec["gdp"], rec["edition"]))
    # 4. Coverage: every year from 1990-91 to the newest is on some base, and
    #    each base is one unbroken run of years.
    years_by_base = {}
    for (base, fy) in chosen:
        years_by_base.setdefault(base, set()).add(c.fy_start(fy))
    for base, ys in years_by_base.items():
        missing = set(range(min(ys), max(ys) + 1)) - ys
        if missing:
            problems.append("base %s has holes: %s" % (base, sorted(missing)))
    allyears = set().union(*years_by_base.values())
    want = set(range(c.fy_start(FIRST_NEEDED), max(allyears) + 1))
    if want - allyears:
        problems.append("no GDP on any base for %s" % sorted(want - allyears))
    # 5. The overlap years really do carry both bases.
    for base in ("2011-12", "2022-23"):
        prev = BASES[BASES.index(base) - 1]
        if (prev, base) not in chosen or (base, base) not in chosen:
            problems.append("the %s rebasing year is not printed on both "
                            "%s and %s" % (base, prev, base))
    return problems


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip discovery and fetching")
    args = ap.parse_args()

    if args.offline:
        ref = c.read_json(EDITIONS_REF)
    else:
        print("Handbook of Statistics on the Indian Economy, Table 1")
        ref = discover()
        fetch(ref)

    records = []
    units = {}
    for year, ed in sorted(ref["editions"].items()):
        ext = ".xls" if ed["url"].lower().endswith(".xls") else ".xlsx"
        path = RAW / ("hbie%s_table1%s" % (year, ext))
        if not path.exists():
            raise SystemExit("%s missing; run without --offline" % path)
        recs, unit = parse_edition(path, year, ed["url"])
        units[year] = unit
        records.extend(to_crore(r) for r in recs)
        print("  %s edition: %d year-values, %s" % (year, len(recs), unit))

    # Newest edition wins within a base.
    chosen = {}
    revised = 0
    for rec in sorted(records, key=lambda r: int(r["edition"])):
        key = (rec["base"], rec["fy"])
        if key in chosen and abs(chosen[key]["gdp"] - rec["gdp"]) > 1.0:
            revised += 1
        chosen[key] = rec

    problems = check(records, chosen)
    if problems:
        print("\nrefusing to write data/gdp.json:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)

    segments = []
    series = {}
    status = {}
    vintage = {}
    for base in BASES:
        ys = sorted((fy for b, fy in chosen if b == base), key=c.fy_start)
        if not ys:
            continue
        series[base] = {fy: chosen[(base, fy)]["gdp"] for fy in ys}
        status[base] = {fy: chosen[(base, fy)]["status"] for fy in ys
                        if chosen[(base, fy)]["status"]}
        vintage[base] = {fy: chosen[(base, fy)]["edition"] for fy in ys}
        eds = sorted({chosen[(base, fy)]["edition"] for fy in ys})
        segments.append({
            "base": base, "first": ys[0], "last": ys[-1], "n_years": len(ys),
            "editions": eds,
            "source_urls": {e: ref["editions"][e]["url"] for e in eds},
        })

    preferred = {}
    for base in BASES:
        for fy, v in series.get(base, {}).items():
            preferred[fy] = {"base": base, "value": v}   # later base overwrites
    pref_years = sorted(preferred, key=c.fy_start)
    breaks = [fy for prev, fy in zip(pref_years, pref_years[1:])
              if preferred[fy]["base"] != preferred[prev]["base"]]

    payload = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "measure": "Gross Domestic Product at market prices",
            "prices": "current",
            "unit": "Rs crore",
            "source": ("RBI, Handbook of Statistics on the Indian Economy, "
                       "Table 1: Macro-Economic Aggregates (At Current "
                       "Prices), reprinting the National Statistics Office "
                       "(earlier the Central Statistics Office)."),
            "source_index": INDEX,
            "published_units": units,
            "bases": list(series),
            "breaks": breaks,
            "rule": ("Never chain, splice or rescale across bases. A share "
                     "of GDP is numerator / series[base][year] on one base; "
                     "compare shares across a break only with the break "
                     "shown. Overlap years carry both bases so the size of "
                     "each break can be read off directly."),
            "within_base": ("Each year is from the newest Handbook edition "
                            "that prints it on that base; `vintage` records "
                            "which, and `status` the estimate's revision "
                            "stage where that edition's notes state it. An edition "
                            "names only the years it is still revising, so a "
                            "blank status is a year it no longer names, not "
                            "an unknown one."),
            "notes": [
                "2004-05 base: CSO's series as last printed in the 2017 "
                "Handbook, 1966-67 to 2011-12. Years before 2004-05 are "
                "CSO's own back-series on that base. Population on this "
                "base is from the 2001 census.",
                "2011-12 base: released January 2015. 2011-12 itself was "
                "revised in 2017 for the new IIP and WPI series; the value "
                "here is the revised one. NSO's 2011-12-base back-series "
                "for 2004-05 to 2010-11 (November 2018) is not reprinted by "
                "the Handbook and is not included.",
                "2022-23 base: released February 2026. The 2026 Handbook "
                "prints 2022-23 on both bases; it carries no 2022-23-base "
                "back-series before 2022-23.",
                "No GDP outturn exists yet for the year a budget estimate "
                "is made for; the Union's 2026-27 budget estimate has no "
                "denominator in this file.",
            ],
            "revisions_superseded": revised,
        },
        "segments": segments,
        "series": series,
        "status": status,
        "vintage": vintage,
        "preferred": {fy: preferred[fy] for fy in pref_years},
    }
    c.write_json(payload, OUT, indent=1)
    for s in segments:
        print("  base %s: %s to %s (%d years) from editions %s"
              % (s["base"], s["first"], s["last"], s["n_years"],
                 ", ".join(s["editions"])))
    print("  breaks at %s; %d earlier vintages superseded"
          % (", ".join(breaks), revised))


if __name__ == "__main__":
    main()

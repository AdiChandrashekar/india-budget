"""Map what the Union budget site publishes, edition by edition.

indiabudget.gov.in has four generations of URL layout between 1996-97 and the
current budget, and the paths in the handoff brief are wrong for most years.
Within every generation, though, the Expenditure Budget filenames are stable:
dg<N> is Demand N, sbe<N> its Statement of Budget Estimates, stat<N> a
summary statement. Only the directory prefix moves.

So: derive the candidate prefixes, verify them with a HEAD request, and record
which file formats each edition actually serves.

    python scripts/discover_union.py            # all editions
    python scripts/discover_union.py 2019-20 2026-27

Writes data/reference/union_editions.json.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

SITE = "https://www.indiabudget.gov.in/"
INDEX = SITE + "previous_union_budget.php"

ANCHOR = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>",
                    re.I | re.S)
TAG = re.compile(r"<[^>]+>")
DATA_EXT = re.compile(r"\.(xlsx|xls|pdf)$", re.I)


COUNT_DEMANDS = False


# indiabudget.gov.in answers HEAD inconsistently: it 404s HEAD for .xlsx files
# it will happily GET, and it serves a 200 HTML page for missing files. So ask
# for the first kilobyte and check the file's magic number instead. That tells
# us the document is really there and really of the type we expect.
MAGIC = {
    ".xlsx": (b"PK",),
    ".xls": (b"PK", b"\xd0\xcf\x11\xe0"),
    ".pdf": (b"%PDF",),
}


def head_ok(url: str) -> bool:
    """True if the URL serves a real document of the type its suffix claims."""
    suffix = "." + url.rsplit(".", 1)[-1].lower()
    wanted = MAGIC.get(suffix)
    try:
        req = urllib.request.Request(
            c.safe_url(url),
            headers={"User-Agent": c.UA, "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 206):
                return False
            head = resp.read(1024)
    except (urllib.error.URLError, OSError, ValueError):
        return False
    if not head:
        return False
    if wanted:
        return head.lstrip()[:8].startswith(wanted)
    return b"<html" not in head[:200].lower()


def candidate_bases(fy: str, index_url: str):
    """Possible Expenditure Budget directories for an edition, best guess first."""
    start = c.fy_start(fy)
    short = "%d-%02d" % (start, (start + 1) % 100)      # 2010-11
    long_ = "%d-%d" % (start, start + 1)                # 2010-2011
    base = index_url.rsplit("/", 1)[0] + "/"
    out = [
        urljoin(base, "doc/eb/"),                      # 2019-20 onward
        urljoin(base, "ub%s/eb/" % short),             # 2011-12 .. 2018-19
        urljoin(base, "eb/"),                          # budget_archive/ub*/
        SITE + "budget_archive/ub%s/eb/" % short,
        SITE + "budget_archive/ub%s/eb/" % long_,
        SITE + "budget%s/ub%s/eb/" % (long_, short),
        SITE + "budget%s/doc/eb/" % short,
    ]
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


# Probe files, in the order we would rather have them.
PROBES = [
    ("alldg_excel", "alldg.xlsx"),      # every demand, one workbook
    ("alldg_pdf", "alldg.pdf"),
    ("dg_excel", "dg25.xlsx"),          # one file per demand
    ("dg_pdf", "dg25.pdf"),
    ("sbe_excel", "sbe25.xlsx"),        # scheme-level statements
    ("sbe_pdf", "sbe25.pdf"),
    ("dgsum_excel", "dgsum.xlsx"),      # demand-wise summary
    ("dgsum_pdf", "dgsum.pdf"),
]


# The edition's year must come from the href, not the link text. The index
# page also carries links like "Implementation of Budget Announcements
# 2019-2020" and "Output Outcome Framework 2020-2021", which point at the
# current year's documents. Trusting their labels silently attributes this
# year's budget to an earlier one.
HREF_YEAR = re.compile(
    r"(?:budget_archive/ub|budget|BUDGET[-\s]?|/ub)"
    r"((?:19|20)\d{2}\s*-\s*(?:19|20)?\d{2})", re.I)


def editions():
    html = c.get_text(INDEX)
    found = {}
    for m in ANCHOR.finditer(html):
        url = urljoin(INDEX, m.group(1).strip())
        label = c.squeeze(TAG.sub(" ", m.group(2)))
        if "indiabudget.gov.in" not in url:
            continue
        hm = HREF_YEAR.search(url)
        if not hm:
            continue
        try:
            fy = c.fy_normalise(hm.group(1))
        except ValueError:
            continue
        interim = "(I)" in url or "(I)" in label
        scan = bool(DATA_EXT.search(url))
        key = "%s%s%s" % (fy, "-i" if interim else "", "-scan" if scan else "")
        found.setdefault(key, {"fiscal_year": fy, "interim": interim,
                               "archive_scan": scan, "index_url": url,
                               "label": label})

    # The current edition is not listed on the "previous budgets" page. Its
    # year is the latest one the home page mentions, not the first.
    root = TAG.sub(" ", c.get_text(SITE))
    years = set()
    for m in re.finditer(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})\b", root):
        try:
            years.add(c.fy_normalise(m.group(0)))
        except ValueError:
            continue
    if years:
        fy = max(years, key=c.fy_start)
        found.setdefault(fy, {"fiscal_year": fy, "interim": False,
                              "archive_scan": False, "index_url": SITE,
                              "label": fy + " (current)"})
    return [found[k] for k in sorted(
        found, key=lambda k: (found[k]["fiscal_year"], found[k]["interim"]))]


def count_demands(base: str, ext: str) -> int:
    """How many demands this edition publishes.

    Editions have run between about 95 and 105 demands, so walk up from 88
    and stop after two consecutive misses rather than probing blind.
    """
    hi, misses = 0, 0
    for n in range(88, 130):
        if head_ok("%sdg%d.%s" % (base, n, ext)):
            hi, misses = n, 0
        else:
            misses += 1
            if misses >= 2 and hi:
                break
    return hi


def resolve(ed: dict) -> dict:
    rec = dict(ed)
    rec.update(eb_base="", formats=[], n_demands=0)
    if ed["archive_scan"]:
        rec["note"] = "pre-1996 scanned PDF of the whole budget; OCR needed"
        return rec

    for base in candidate_bases(ed["fiscal_year"], ed["index_url"]):
        hits = [name for name, probe in PROBES if head_ok(base + probe)]
        if hits:
            rec["eb_base"] = base
            rec["formats"] = hits
            if COUNT_DEMANDS:
                if "dg_excel" in hits:
                    rec["n_demands"] = count_demands(base, "xlsx")
                elif "dg_pdf" in hits:
                    rec["n_demands"] = count_demands(base, "pdf")
            break
    if not rec["eb_base"]:
        rec["note"] = "no Expenditure Budget directory found by pattern"
    return rec


def main(argv) -> None:
    global COUNT_DEMANDS
    COUNT_DEMANDS = "--count-demands" in argv
    argv = [a for a in argv if not a.startswith("--")]
    wanted = {c.fy_normalise(a) for a in argv} if argv else None
    eds = [e for e in editions() if not wanted or e["fiscal_year"] in wanted]
    print("resolving %d editions" % len(eds))

    out = []
    for ed in eds:
        rec = resolve(ed)
        out.append(rec)
        tag = "interim" if ed["interim"] else ("scan" if ed["archive_scan"] else "")
        print("  %-9s %-7s %-46s %-3s %s" % (
            rec["fiscal_year"], tag,
            rec["eb_base"].replace(SITE, "") or rec.get("note", "")[:46],
            rec["n_demands"] or "", ",".join(rec["formats"])))

    if not wanted and len(out) < 30:
        raise SystemExit("expected 30+ editions, found %d" % len(out))

    dest = c.REFERENCE / "union_editions.json"
    if wanted and dest.exists():                 # merge into the existing map
        old = {(r["fiscal_year"], r["interim"], r["archive_scan"]): r
               for r in c.read_json(dest)}
        for r in out:
            old[(r["fiscal_year"], r["interim"], r["archive_scan"])] = r
        out = [old[k] for k in sorted(old)]
    c.write_json(out, dest)

    excel = [r["fiscal_year"] for r in out if "alldg_excel" in r["formats"]]
    pdf = [r["fiscal_year"] for r in out if "dg_pdf" in r["formats"]
           and "alldg_excel" not in r["formats"]]
    print("\nalldg workbook (parse now): %d editions %s" % (len(excel), excel))
    print("per-demand PDF only (phase 2): %d editions %s" % (len(pdf), pdf))


if __name__ == "__main__":
    main(sys.argv[1:])

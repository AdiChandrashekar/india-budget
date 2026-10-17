"""Download the Union Expenditure Budget documents named in union_editions.json.

    python scripts/discover_union.py     # first, to build the map
    python scripts/fetch_union.py        # then this

Raw files land in data/raw/union/<fiscal-year>/ with a manifest.csv recording
the URL, fetch time, byte count and sha256 of every one. Downloads are cached,
so re-running is cheap; pass --force to refetch.

Two kinds of document, because the site changed container twice:

*   ``alldg.xlsx`` - every demand as one workbook. Only 2019-20, 2024-25,
    2025-26 and 2026-27 ship it.
*   ``alldg.pdf`` - every demand as one PDF, from the 2011-12 edition onwards,
    and ``dg<N>.pdf`` - one PDF per demand, from 2003-04 onwards. These are the
    same statements in another container; see scripts/parse_union_pdf.py.

Pass --excel or --pdf to limit it to one of them. The per-demand PDFs are
fetched only for the editions that have no alldg.pdf, because that is a
hundred requests per edition and the bundle is the same document.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

# What we need per edition, and whether its absence is fatal.
WANTED = [
    ("alldg.xlsx", "alldg_excel", True),    # every demand, by major head
    ("dgsum.xlsx", "dgsum_excel", False),   # ministry -> department -> demand
]

# No edition publishes more than ~110 demands; stop early once the numbering
# runs out. The site answers a missing file with a 200 HTML page, so existence
# is decided by the PDF magic number, exactly as discover_union.py does.
MAX_DEMANDS = 120
MISSES_BEFORE_STOP = 4


def is_pdf(url: str) -> bool:
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
    return head.lstrip()[:8].startswith(b"%PDF")


def fetch_excel(ed: dict, force: bool) -> int:
    got = 0
    dest_dir = c.RAW / "union" / ed["fiscal_year"]
    for name, fmt, required in WANTED:
        if fmt not in ed["formats"]:
            if required:
                raise SystemExit("%s: %s missing from the edition map"
                                 % (ed["fiscal_year"], name))
            continue
        url = ed["eb_base"] + name
        try:
            path = c.fetch(url, dest_dir / name, force=force)
        except RuntimeError as exc:
            if required:
                raise SystemExit("%s: %s" % (ed["fiscal_year"], exc))
            c.eprint("  %s: optional %s unavailable" % (ed["fiscal_year"], name))
            continue
        size = path.stat().st_size
        if required and size < 50_000:
            raise SystemExit("%s: %s is only %d bytes, looks like an error page"
                             % (ed["fiscal_year"], name, size))
        print("  %-9s %-12s %8d bytes" % (ed["fiscal_year"], name, size))
        got += 1
    return got


def fetch_pdf(ed: dict, force: bool) -> int:
    """The bundle if the edition has one, otherwise every demand separately."""
    fy = ed["fiscal_year"]
    dest_dir = c.RAW / "union" / fy

    if "alldg_pdf" in ed["formats"]:
        url = ed["eb_base"] + "alldg.pdf"
        path = c.fetch(url, dest_dir / "alldg.pdf", force=force)
        size = path.stat().st_size
        if size < 100_000:
            raise SystemExit("%s: alldg.pdf is only %d bytes, looks like an "
                             "error page" % (fy, size))
        print("  %-9s %-12s %8d bytes" % (fy, "alldg.pdf", size))
        return 1

    if "dg_pdf" not in ed["formats"]:
        return 0

    # Per-demand PDFs. The map records how many demands discover_union.py
    # found, but it does not always count them, so probe and stop on a run of
    # misses rather than trusting a number.
    out = dest_dir / "dg"
    got, misses = 0, 0
    for n in range(1, MAX_DEMANDS + 1):
        dest = out / ("dg%d.pdf" % n)
        if dest.exists() and dest.stat().st_size > 0 and not force:
            got, misses = got + 1, 0
            continue
        url = ed["eb_base"] + "dg%d.pdf" % n
        if not is_pdf(url):
            misses += 1
            if misses >= MISSES_BEFORE_STOP and got:
                break
            continue
        try:
            c.fetch(url, dest, force=force, pause=0.2)
        except RuntimeError as exc:
            c.eprint("  %s: %s" % (fy, exc))
            misses += 1
            continue
        got, misses = got + 1, 0
    print("  %-9s %-12s %3d demands" % (fy, "dg<N>.pdf", got))
    return got


def main(argv) -> None:
    force = "--force" in argv
    only_excel = "--excel" in argv
    only_pdf = "--pdf" in argv
    years = [a for a in argv if not a.startswith("--")]
    wanted = {c.fy_normalise(y) for y in years} if years else None

    editions = [e for e in c.read_json(c.REFERENCE / "union_editions.json")
                if not e["interim"] and (not wanted
                                         or e["fiscal_year"] in wanted)]

    excel = [e for e in editions if "alldg_excel" in e.get("formats", [])]
    pdf = [e for e in editions
           if {"alldg_pdf", "dg_pdf"} & set(e.get("formats", []))]
    if not excel and not pdf:
        raise SystemExit("nothing to fetch; run discover_union.py first")

    got = 0
    if not only_pdf:
        print("workbooks: %d editions" % len(excel))
        for ed in excel:
            got += fetch_excel(ed, force)
    if not only_excel:
        print("PDFs: %d editions" % len(pdf))
        for ed in pdf:
            got += fetch_pdf(ed, force)

    print("\n%d files in data/raw/union/" % got)


if __name__ == "__main__":
    main(sys.argv[1:])

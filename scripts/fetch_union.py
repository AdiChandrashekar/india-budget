"""Download the Union Expenditure Budget workbooks named in union_editions.json.

    python scripts/discover_union.py     # first, to build the map
    python scripts/fetch_union.py        # then this

Raw files land in data/raw/union/<fiscal-year>/ with a manifest.csv recording
the URL, fetch time, byte count and sha256 of every one. Downloads are cached,
so re-running is cheap; pass --force to refetch.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

# What we need per edition, and whether its absence is fatal.
WANTED = [
    ("alldg.xlsx", "alldg_excel", True),    # every demand, by major head
    ("dgsum.xlsx", "dgsum_excel", False),   # ministry -> department -> demand
]


def main(argv) -> None:
    force = "--force" in argv
    years = [a for a in argv if not a.startswith("--")]
    wanted = {c.fy_normalise(y) for y in years} if years else None

    editions = c.read_json(c.REFERENCE / "union_editions.json")
    todo = [e for e in editions
            if "alldg_excel" in e.get("formats", [])
            and not e["interim"]
            and (not wanted or e["fiscal_year"] in wanted)]

    if not todo:
        raise SystemExit(
            "no editions with an alldg workbook; run discover_union.py first")

    print("fetching %d editions: %s" % (
        len(todo), ", ".join(e["fiscal_year"] for e in todo)))

    got = 0
    for ed in todo:
        dest_dir = c.RAW / "union" / ed["fiscal_year"]
        for name, fmt, required in WANTED:
            if fmt not in ed["formats"] and required:
                raise SystemExit("%s: %s missing from the edition map"
                                 % (ed["fiscal_year"], name))
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

    print("\n%d files in data/raw/union/" % got)


if __name__ == "__main__":
    main(sys.argv[1:])

"""Download the state finance workbooks discover_states.py resolved.

Cached: a file already on disk is left alone unless --force. Every download is
appended to data/raw/states/manifest.csv with its URL, fetch time, byte count
and sha256, so any figure on the site can be traced back to the exact bytes it
came from.

    python scripts/fetch_states.py
    python scripts/fetch_states.py --force
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

DEST = c.RAW / "states"

# Local file name per document key. Stable, unlike RBI's own file names, which
# embed a publication date and a content hash and so change every edition.
NAMES = {
    "estates": "estates.xlsx",
    "statement_26": "statement_26.xlsx",
    "statement_31": "statement_31.xlsx",
    "appendix_7": "appendix_7.xlsx",
    "gsdp_current": "handbook_t21_gsdp_current.xlsx",
    "social_sector": "handbook_t175_social_sector.xlsx",
}

# Without these two there is no state layer at all; the rest are cross-checks.
REQUIRED = ("estates", "statement_26")


def main(argv) -> None:
    force = "--force" in argv
    path = c.REFERENCE / "state_editions.json"
    if not path.exists():
        raise SystemExit("no %s; run scripts/discover_states.py first"
                         % path.name)
    editions = c.read_json(path)

    docs = {}
    for block in ("state_finances", "handbook"):
        docs.update(editions[block]["documents"])

    print("edition: State Finances: A Study of Budgets of %s"
          % (editions.get("edition") or "unknown"))
    got, skipped = [], []
    for key, name in NAMES.items():
        rec = docs.get(key)
        if not rec or not rec.get("ok"):
            skipped.append(key)
            print("  %-14s skipped, not verified by discover_states.py" % key)
            continue
        dest = DEST / name
        cached = dest.exists() and dest.stat().st_size > 0 and not force
        c.fetch_doc(rec["url"], dest, referer=rec.get("referer", ""),
                    force=force)
        size = dest.stat().st_size
        got.append(key)
        print("  %-14s %9s bytes  %s%s"
              % (key, format(size, ","), name, "  (cached)" if cached else ""))

    for key in REQUIRED:
        if key not in got:
            raise SystemExit(
                "%s is required and was not downloaded; nothing downstream "
                "can run" % key)

    print("\n%d of %d documents in %s"
          % (len(got), len(NAMES), DEST.relative_to(c.ROOT)))
    if skipped:
        print("not available this run: %s" % ", ".join(skipped))
    print("manifest: %s" % (DEST / "manifest.csv").relative_to(c.ROOT))


if __name__ == "__main__":
    main(sys.argv[1:])

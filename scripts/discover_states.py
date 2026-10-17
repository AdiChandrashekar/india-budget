"""Find what RBI actually publishes for state finances, and prove it is there.

The handoff brief's URL for Statement 26 redirects to the RBI home page, so
nothing here is guessed from a documented path. Instead we read the two live
publication indexes and take the document links out of the HTML, then verify
each one by asking for its first two kilobytes and checking the file's magic
number.

That last step is not optional. RBI's documents live on rbidocs.rbi.org.in
behind a bot defence that answers an unprepared request with HTTP 200, a
Content-Type of text/html and a page of obfuscated JavaScript. See the long
comment in common.py for how that is dealt with; the short version is that
you have to read the index page first and then check the bytes.

    python scripts/discover_states.py

Writes data/reference/state_editions.json.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

# The old-style ASPX indexes. RBI's newer website.rbi.org.in pages build their
# document lists in the browser, so there is nothing in their HTML to read;
# these still ship the links in the markup.
SF_INDEX = ("https://rbi.org.in/Scripts/AnnualPublications.aspx"
            "?head=State+Finances+%3A+A+Study+of+Budgets")
HB_INDEX = ("https://rbi.org.in/Scripts/AnnualPublications.aspx"
            "?head=Handbook+of+Statistics+on+Indian+States")

ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
HREF = re.compile(r"""href\s*=\s*["']([^"']+\.(?:XLSX|xlsx|XLS|xls))["']""")
TAG = re.compile(r"<[^>]+>")

# What we need, and the label that identifies it in the index. Everything else
# RBI publishes in these volumes is recorded but not fetched.
WANTED_SF = [
    ("estates", re.compile(r"(?i)^e-STATES Database")),
    ("statement_26", re.compile(r"(?i)^Statement 26\b")),
    ("statement_31", re.compile(r"(?i)^Statement 31\b")),
    ("appendix_7", re.compile(r"(?i)^Appendix Table 7\b")),
]
WANTED_HB = [
    ("gsdp_current", re.compile(r"(?i)^Table 21\b")),
    ("social_sector", re.compile(r"(?i)^Table 175\b")),
]


def label_of(row_html: str) -> str:
    """The table row's own text, with the file-size spans squeezed out.

    A row links both a workbook and a PDF, so it carries two "15 kb" spans;
    strip every trailing one, not just the last.
    """
    text = c.squeeze(TAG.sub(" ", row_html))
    return re.sub(r"(\s*\d+\s*kb\s*)+$", "", text, flags=re.I).strip()


def index_rows(html: str, index_url: str):
    """[(label, first xlsx url)] for every row of an index that links a workbook."""
    out = []
    for m in ROW.finditer(html):
        row = m.group(1)
        link = HREF.search(row)
        if not link:
            continue
        out.append((label_of(row), link.group(1)))
    if not out:
        raise SystemExit(
            "%s served %d characters but no workbook links; the index layout "
            "has changed" % (index_url, len(html)))
    return out


def pick(rows, wanted, index_url: str) -> dict:
    """Resolve each wanted document to a verified URL."""
    found = {}
    for key, pattern in wanted:
        hits = [(lab, url) for lab, url in rows if pattern.match(lab)]
        if not hits:
            found[key] = {"ok": False, "url": "", "label": "",
                          "note": "no row in the index matched"}
            continue
        label, url = hits[0]
        ok = c.doc_ok(url, referer=index_url)
        found[key] = {
            "ok": ok,
            "url": url,
            "label": label,
            "referer": index_url,
            "checked": time.strftime("%Y-%m-%d", time.gmtime()),
            "note": "" if ok else "the index links this, but it does not serve a workbook",
        }
        print("  %-14s %-5s %s" % (key, "ok" if ok else "FAIL", label[:66]))
    return found


def read_index(index_url: str) -> str:
    """The index HTML. Also warms the cookie jar, which the fetches depend on."""
    html = c.warm(index_url)
    if not html:
        raise SystemExit("could not read the index at %s" % index_url)
    return html


def main() -> None:
    print("State Finances: A Study of Budgets")
    sf_html = read_index(SF_INDEX)
    sf_rows = index_rows(sf_html, SF_INDEX)
    print("  %d rows link a workbook" % len(sf_rows))
    sf = pick(sf_rows, WANTED_SF, SF_INDEX)

    print("\nHandbook of Statistics on Indian States")
    hb_html = read_index(HB_INDEX)
    hb_rows = index_rows(hb_html, HB_INDEX)
    print("  %d rows link a workbook" % len(hb_rows))
    hb = pick(hb_rows, WANTED_HB, HB_INDEX)

    # The edition's own year is not printed in a machine-readable place, but
    # the title row carries it, e.g. "State Finances: A Study of Budgets of
    # 2025-26". Take it from there rather than from the file name's date stamp,
    # which is the day of publication, not the year being budgeted.
    edition = ""
    m = re.search(r"(?i)Study of Budgets of\s*((?:19|20)\d{2}\s*-\s*\d{2,4})",
                  TAG.sub(" ", sf_html))
    if m:
        try:
            edition = c.fy_normalise(m.group(1))
        except ValueError:
            edition = ""

    payload = {
        "generated": time.strftime("%Y-%m-%d", time.gmtime()),
        "edition": edition,
        "note": ("Resolved from the live indexes, not from documented paths: "
                 "the brief's Statement 26 URL now redirects to the RBI home "
                 "page. Every url below was verified with a ranged GET and a "
                 "magic-number check on the day shown. The file names carry a "
                 "publication date and a content hash, so they change with "
                 "every edition -- re-run this script rather than editing "
                 "them by hand."),
        "state_finances": {"index": SF_INDEX, "documents": sf},
        "handbook": {"index": HB_INDEX, "documents": hb},
    }

    missing = [k for block in (sf, hb) for k, v in block.items() if not v["ok"]]
    if missing:
        print("\nunverified: %s" % ", ".join(missing))
    c.write_json(payload, c.REFERENCE / "state_editions.json", indent=1)

    if not sf["estates"]["ok"]:
        raise SystemExit(
            "the e-STATES workbook did not verify; it is the only source for "
            "the state education series, so there is nothing to parse")
    print("\nedition: State Finances: A Study of Budgets of %s"
          % (edition or "unknown"))


if __name__ == "__main__":
    main()

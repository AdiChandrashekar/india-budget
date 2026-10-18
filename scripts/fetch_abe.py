"""Find and fetch the Ministry of Education's Analysis of Budgeted Expenditure.

    python scripts/fetch_abe.py

Writes data/reference/abe_editions.json and data/raw/abe/ (+ manifest.csv).

The *Analysis of Budgeted Expenditure on Education* (ABE) is the only
publication that splits state education spending by sub-sector and adds the
Centre and the states together without double counting the transfers. Every
education.gov.in URL for it now returns 404 -- the ministry's statistics
pages were rebuilt -- and the Wayback Machine's *availability* endpoint
reports no snapshot for the URLs the brief had.

The Wayback *CDX* API is a different index and does have them: a prefix
query over the two upload directories the ministry has used,
`.../files/statistics/` and `.../files/statistics-new/`, on both mhrd.gov.in
and education.gov.in, lists eleven editions captured with HTTP 200 and
application/pdf. They are fetched from the raw-capture form of the archive
URL (`/web/<timestamp>id_/<url>`), which serves the original bytes rather
than the archive's HTML frame, and kept only if the bytes start %PDF.

Several of the CDX keys are junk -- URLs with text glued on after '.pdf'
('ABE2014-17.pdfBordoloi'), captured as 301 redirects. Only exact '.pdf'
keys with status 200 and a PDF mime type are taken.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

CDX = "http://web.archive.org/cdx/search/cdx"
PREFIXES = [
    "education.gov.in/sites/upload_files/mhrd/files/statistics*",
    "mhrd.gov.in/sites/upload_files/mhrd/files/statistics*",
]
RAW = c.RAW / "abe"
REF = c.REFERENCE / "abe_editions.json"
NAME = re.compile(r"(?i)/(abe[-_]?\d{4}-\d{2}(?:_\d)?|analysis_of_budgeted_expenditure"
                  r"_on_education_\d{4}-\d{4}|budget_exp_\d{4}_\d{2}|budget_exp"
                  r"|budget_expenditure|budget%20exp%20\d{4}-\d{2}[^/]*)\.pdf$")


def cdx(prefix: str):
    q = urllib.parse.urlencode({"url": prefix, "output": "txt",
                                "fl": "original,timestamp,statuscode,mimetype,length",
                                "filter": "statuscode:200", "limit": "20000"})
    req = urllib.request.Request(CDX + "?" + q, headers={"User-Agent": c.UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read().decode("utf-8", "replace").splitlines()
        except OSError as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    raise SystemExit("CDX query failed for %s: %s" % (prefix, last))


def years_of(name: str):
    """'ABE_2010-13' -> ('2010-11', '2012-13'): the span an edition covers."""
    m = re.search(r"(\d{4})[-_](\d{2,4})", name)
    if not m:
        return None, None
    a, b = int(m.group(1)), m.group(2)
    b = int(b) if len(b) == 4 else (a // 100) * 100 + int(b)
    if b < a:
        b += 100
    return "%d-%02d" % (a, (a + 1) % 100), "%d-%02d" % (b - 1, b % 100)


def cover_span(path: Path):
    """('2019-20', '2021-22') from the edition's own title page, or (None, None)
    for a scan with no text layer."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = " ".join((p.extract_text() or "") for p in pdf.pages[:4])
    m = re.search(r"(?i)EXPENDITURE\s+ON\s+EDUCATION\s+((?:19|20)\d{2}\s*-\s*\d{2,4})"
                  r"\s+to\s+((?:19|20)\d{2}\s*-\s*\d{2,4})", " ".join(text.split()))
    if not m:
        return None, None
    return c.fy_normalise(m.group(1)), c.fy_normalise(m.group(2))


def main() -> None:
    found = {}
    for prefix in PREFIXES:
        for line in cdx(prefix):
            parts = line.split(" ")
            if len(parts) < 4:
                continue
            original, ts, status, mime = parts[:4]
            if status != "200" or "pdf" not in mime:
                continue
            m = NAME.search(original.split("?")[0])
            if not m:
                continue
            fname = urllib.parse.unquote(m.group(0).lstrip("/"))
            key = re.sub(r"_\d\.pdf$", ".pdf", fname.lower())  # _0, _1 copies
            # Keep the most recent capture of each document.
            if key not in found or ts > found[key]["timestamp"]:
                found[key] = {"original": original.split("?")[0], "timestamp": ts,
                              "file": fname}
    if not found:
        raise SystemExit("the CDX index lists no ABE capture")
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, d in sorted(found.items()):
        url = "https://web.archive.org/web/%sid_/%s" % (d["timestamp"], d["original"])
        dest = RAW / re.sub(r"[^A-Za-z0-9_.-]", "_", d["file"])
        if not dest.exists():
            try:
                c.fetch(url, dest, pause=2.0)
            except RuntimeError as exc:
                print("  ! %s: %s" % (d["file"], exc))
                continue
        head = dest.read_bytes()[:8]
        ok = head.startswith(b"%PDF")
        if not ok:
            dest.unlink()
        # The span comes from the cover, never the file name: the names do
        # not say which edition they are. budget_exp_2020_22.pdf is the
        # 2019-20 to 2021-22 edition, ..._2017-2019.pdf is 2016-17 to
        # 2018-19, and budget_exp.pdf (2018-19 to 2020-21) has no year at all.
        first, last = cover_span(dest) if ok else (None, None)
        out[key] = dict(d, archive_url=url, path=dest.name if ok else "",
                        ok=ok, first=first, last=last,
                        name_says="%s..%s" % years_of(d["file"]),
                        text_layer=first is not None,
                        bytes=dest.stat().st_size if ok else 0)
        print("  %-62s %s %s" % (d["file"][:62], d["timestamp"][:8],
                                 "ok" if ok else "NOT A PDF"))
    c.write_json({
        "generated": time.strftime("%Y-%m-%d", time.gmtime()),
        "note": ("Analysis of Budgeted Expenditure on Education, every edition "
                 "the Wayback CDX index holds with HTTP 200 and a PDF mime "
                 "type, under the ministry's two upload directories on both "
                 "of its domains. archive_url is the raw-capture form."),
        "editions": out,
    }, REF)


if __name__ == "__main__":
    main()

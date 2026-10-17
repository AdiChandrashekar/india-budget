"""Shared helpers for the India Budget Explorer pipeline.

Every script in this directory validates its own output and refuses to write if
an invariant fails. Nothing here depends on anything outside the standard
library except openpyxl, which only the workbook parsers need.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

# The budget workbooks carry Devanagari and the rupee sign; Windows consoles
# default to cp1252, and `python -I` ignores PYTHONUTF8. Force it here so every
# script in this directory can print what it reads.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REFERENCE = ROOT / "data" / "reference"

UA = "Mozilla/5.0 (compatible; india-budget-explorer/0.1; static research tool)"


def safe_url(url: str) -> str:
    """Percent-encode spaces and other literal characters the site serves."""
    scheme, _, rest = url.partition("://")
    if not rest:
        return urllib.parse.quote(url, safe="/:?&=#%+,()[]~@!$'*;-_.")
    host, _, path = rest.partition("/")
    return "%s://%s/%s" % (
        scheme, host, urllib.parse.quote(path, safe="/:?&=#%+,()[]~@!$'*;-_."))

# --------------------------------------------------------------------------- #
# Fiscal years
# --------------------------------------------------------------------------- #

FY_RE = re.compile(r"^(\d{4})-(\d{2}|\d{4})$")


def fy_normalise(text) -> str:
    """'2026-2027', '2026-27', '202627' -> '2026-27'. Raises on nonsense."""
    s = re.sub(r"[^\d-]", "", str(text).strip())
    m = FY_RE.match(s)
    if m:
        start, end = m.group(1), m.group(2)
    else:
        m2 = re.match(r"^(\d{4})(\d{2})$", s)
        if not m2:
            raise ValueError("not a fiscal year: %r" % (text,))
        start, end = m2.group(1), m2.group(2)
    start_i = int(start)
    end_i = int(end) if len(end) == 4 else (start_i // 100) * 100 + int(end)
    if end_i < start_i:          # century rollover, e.g. 1999-00
        end_i += 100
    if end_i != start_i + 1:
        raise ValueError("fiscal year must span one year: %r" % (text,))
    return "%d-%02d" % (start_i, end_i % 100)


def fy_start(fy) -> int:
    return int(fy_normalise(fy).split("-")[0])


def fy_shift(fy, years: int) -> str:
    s = fy_start(fy) + years
    return "%d-%02d" % (s, (s + 1) % 100)


# --------------------------------------------------------------------------- #
# Units. Everything in the long table is Rs crore.
# --------------------------------------------------------------------------- #

TO_CRORE = {
    "crore": 1.0,
    "lakh": 0.01,
    "thousand": 1e-5,
    "rupee": 1e-7,
    "million": 0.1,
    "billion": 100.0,
}


def to_crore(value, unit: str) -> float:
    if unit not in TO_CRORE:
        raise ValueError("unknown unit %r; known: %s" % (unit, sorted(TO_CRORE)))
    return float(value) * TO_CRORE[unit]


# --------------------------------------------------------------------------- #
# Fetching, with a manifest so every raw byte is traceable
# --------------------------------------------------------------------------- #


def fetch(url: str, dest, *, force: bool = False, retries: int = 3,
          pause: float = 0.5) -> Path:
    """Download url to dest, recording it in the sibling manifest.csv.

    Cached by default: an existing non-empty file is reused untouched.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest

    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
            if not body:
                raise OSError("empty response")
            dest.write_bytes(body)
            _record(dest, url, body)
            time.sleep(pause)
            return dest
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("could not fetch %s: %s" % (url, last))


def _record(dest: Path, url: str, body: bytes) -> None:
    manifest = dest.parent / "manifest.csv"
    new = not manifest.exists()
    with manifest.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["path", "url", "fetched_at", "bytes", "sha256"])
        w.writerow([
            dest.name, url,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            len(body), hashlib.sha256(body).hexdigest(),
        ])


def get_text(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            for enc in ("utf-8", "cp1252", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("could not fetch %s: %s" % (url, last))


# --------------------------------------------------------------------------- #
# The long table: one row per published number
# --------------------------------------------------------------------------- #

COLUMNS = [
    "fiscal_year",       # the year the money refers to, e.g. 2024-25
    "govt",              # union | state
    "state_code",        # blank for union
    "estimate_type",     # A (actuals) | BE | RE
    "source_edition",    # the document the number was read from
    "definition",        # moe | abe_all_depts | functional | whole
    "major_head",        # 4-digit LMMHA major head, e.g. 2202
    "sub_major_head",    # 2-digit, e.g. 01 Elementary
    "ministry_or_dept",
    "scheme",
    "account",           # basis_section, e.g. gross_revenue, net_total
    "occurrence",        # 1, or 2+ where a statement repeats a head (see below)
    "amount_cr",         # Rs crore, always
    "source_url",
    "source_page",
]

ESTIMATE_TYPES = {"A", "BE", "RE"}
DEFINITIONS = {"moe", "abe_all_depts", "functional", "whole"}


@dataclass
class Row:
    fiscal_year: str
    govt: str
    estimate_type: str
    source_edition: str
    definition: str
    account: str
    amount_cr: float
    source_url: str
    state_code: str = ""
    major_head: str = ""
    sub_major_head: str = ""
    ministry_or_dept: str = ""
    scheme: str = ""
    source_page: str = ""
    # A statement can list the same head twice and mean two different numbers.
    # Demand 40 (Repayment of Debt), for instance, nets receipts off under two
    # separate notes, both against major head 6001. Numbering the repeats keeps
    # them apart without inventing account names, and the index is stable
    # across editions because the document's structure is.
    occurrence: int = 1

    def validate(self) -> None:
        self.fiscal_year = fy_normalise(self.fiscal_year)
        if self.govt not in ("union", "state"):
            raise ValueError("govt must be union|state, got %r" % (self.govt,))
        if self.estimate_type not in ESTIMATE_TYPES:
            raise ValueError("bad estimate_type %r" % (self.estimate_type,))
        if self.definition not in DEFINITIONS:
            raise ValueError("bad definition %r" % (self.definition,))
        if self.govt == "state" and not self.state_code:
            raise ValueError("state rows need a state_code")
        if self.major_head and not re.fullmatch(r"\d{4}", self.major_head):
            raise ValueError("major_head must be 4 digits, got %r" % (self.major_head,))
        if self.amount_cr is None:
            raise ValueError("amount_cr is required")
        float(self.amount_cr)


def write_long_table(rows, dest) -> None:
    """Validate every row, then write atomically. Never writes a partial table."""
    if not rows:
        raise SystemExit("refusing to write an empty table: " + str(dest))
    for i, r in enumerate(rows):
        try:
            r.validate()
        except ValueError as exc:
            raise SystemExit("row %d invalid: %s\n  %r" % (i, exc, asdict(r)))

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="raise")
        w.writeheader()
        for r in rows:
            d = asdict(r)
            d["amount_cr"] = round(float(d["amount_cr"]), 2)
            w.writerow({k: d[k] for k in COLUMNS})
    tmp.replace(dest)
    print("wrote %s rows -> %s" % (format(len(rows), ","), dest.relative_to(ROOT)))


def read_long_table(path):
    with Path(path).open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["amount_cr"] = float(r["amount_cr"])
    return rows


def write_json(obj, dest, *, indent: int = 1) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(dest)
    print("wrote %s" % (dest.relative_to(ROOT),))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Text cleaning. The Union workbooks are bilingual: Devanagari and English in
# the same cell, separated by runs of non-breaking spaces.
# --------------------------------------------------------------------------- #

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def latin_part(text) -> str:
    """Keep the Latin-script half of a bilingual cell, squeezing whitespace."""
    if text is None:
        return ""
    s = str(text).replace("\xa0", " ")
    s = DEVANAGARI.sub(" ", s)
    s = re.sub(r"[‐-―]", "-", s)
    s = re.sub(r"\s+", " ", s)
    # Removing the Devanagari half can leave its punctuation behind, e.g.
    # ', Department Of Agriculture, Cooperation ...' from a bilingual cell.
    return s.strip(" ._,;:")


DEPT_ALIASES = {
    # Renames that would otherwise break a series in two. The Ministry of
    # Human Resource Development became the Ministry of Education in 2020;
    # its two departments were renamed in 2018.
    "department of elementary education and literacy":
        "department of school education and literacy",
    "department of secondary education and higher education":
        "department of higher education",
    "ministry of human resource development": "ministry of education",
}


def dept_key(name) -> str:
    """A stable key for a ministry or department across editions.

    Needed because the same department is printed differently in different
    places: the sheet heading is all caps, the summary workbook is mixed case,
    and some years carry stray punctuation from the Devanagari half of a cell.
    """
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    s = re.sub(r"\s+", " ", s).strip()
    return DEPT_ALIASES.get(s, s)


def squeeze(text) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def num(value):
    """Parse a budget cell to a float. '...' means nil, not missing."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("\xa0", " ").strip()
    if s in ("", "-", "--"):
        return None
    if s and set(s) <= {".", " "}:      # '...' is the budget docs' nil marker
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("*", "").replace("@", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def eprint(*a) -> None:
    print(*a, file=sys.stderr)

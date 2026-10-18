"""State GSDP at current prices back to 1990-91, one segment per base year.

    python scripts/state_gsdp_series.py            # discover, fetch, parse
    python scripts/state_gsdp_series.py --offline

Writes data/raw/states/handbook2018_t15_gsdp_fc.xlsx (+ manifest),
data/reference/gsdp_editions.json and data/gsdp.json.

The state layer's GSDP (data/reference/state_gsdp.json, from Table 21 of the
current Handbook of Statistics on Indian States) starts in 2011-12, because
that table carries only the 2011-12 base. The 2018 edition of the same
Handbook, Table 15, is the last to print every older base side by side:

    base 1980-81   1990-91 .. 1992-93
    base 1993-94   1993-94 .. 1999-00
    base 1999-00   1999-00 .. 2004-05
    base 2004-05   2004-05 .. 2014-15
    base 2011-12   2011-12 .. (taken from the current Handbook instead)

Three things are kept apart rather than chained:

1.  **Base years.** Each base is its own segment. Where two bases print the
    same year (1999-00, 2004-05, 2011-12) both values are kept, so the size
    of every break can be read. Nothing is rescaled.
2.  **The measure.** The older bases are GSDP *at factor cost*; the 2011-12
    base is GSDP at current (market) prices, which adds product taxes net of
    subsidies. That is a second break at 2011-12 on top of the rebasing, and
    it is recorded per segment.
3.  **Boundaries.** Back-cast series put a parent state on its post-split
    boundary: the 2004-05 base prints residual Andhra Pradesh and a separate
    Telangana for 2004-05, although Andhra Pradesh's *budget* for that year
    is the undivided state's. Dividing an undivided budget by a residual
    GSDP overstates the share. So alongside the series as printed,
    `budget_boundary` gives the GSDP on the territory of that state's budget
    in each year: parent plus successor where the successor is printed for a
    year before it existed, the parent alone where it is not.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import national_gdp as ng  # noqa: E402  (the year-archive postback)
import parse_states as ps  # noqa: E402

HB_INDEX = ("https://rbi.org.in/Scripts/AnnualPublications.aspx"
            "?head=Handbook+of+Statistics+on+Indian+States")
EDITION_YEAR = 2018
LABEL = re.compile(r"(?i)^Table\s*15\s*:\s*Gross State Domestic Product at Factor "
                   r"Cost \(Current Prices\)")
RAW = c.RAW / "states" / "handbook2018_t15_gsdp_fc.xlsx"
REF = c.REFERENCE / "gsdp_editions.json"
OUT = c.ROOT / "data" / "gsdp.json"
CURRENT = c.RAW / "states" / "handbook_t21_gsdp_current.xlsx"

MEASURE = {
    "1980-81": "GSDP at factor cost",
    "1993-94": "GSDP at factor cost",
    "1999-00": "GSDP at factor cost",
    "2004-05": "GSDP at factor cost",
    "2011-12": "GSDP at current prices (market prices)",
}


def discover() -> dict:
    """The 2018 edition's Table 15, found in the index and verified."""
    base_page = c.warm(HB_INDEX)
    # national_gdp.index_for_year posts to its own INDEX; do the same here.
    import html as htmllib
    import urllib.parse
    import urllib.request
    fields = ng._hidden_fields(base_page)
    fields["hdnYear"] = str(EDITION_YEAR)
    fields["UsrFontCntr$btn"] = ""
    req = urllib.request.Request(
        HB_INDEX, data=urllib.parse.urlencode(fields).encode(),
        headers={"User-Agent": c.BROWSER_UA, "Referer": HB_INDEX,
                 "Content-Type": "application/x-www-form-urlencoded"})
    with c._OPENER.open(req, timeout=120) as resp:
        page = resp.read().decode("utf-8", "replace")
    for m in ng.ROW.finditer(page):
        row = m.group(1)
        label = c.squeeze(ng.TAG.sub(" ", htmllib.unescape(row)))
        label = re.sub(r"(\s*\d+\s*kb\s*)+$", "", label, flags=re.I).strip()
        if LABEL.match(label):
            link = ng.LINK.search(row)
            if link and c.doc_ok(link.group(1), referer=HB_INDEX):
                payload = {"generated": time.strftime("%Y-%m-%d", time.gmtime()),
                           "index": HB_INDEX, "edition": EDITION_YEAR,
                           "label": label, "url": link.group(1),
                           "note": "Reached by the index's year postback "
                                   "(hdnYear=%d); verified by magic number."
                                   % EDITION_YEAR}
                c.write_json(payload, REF)
                return payload
    raise SystemExit("the %d Handbook lists no verified Table 15 workbook"
                     % EDITION_YEAR)


def read_2018(path: Path, by_rbi):
    """{base: {state code: {fy: crore}}} from the all-bases sheet."""
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    grid = {(cell.row, cell.column): cell.value for row in ws.iter_rows()
            for cell in row if cell.value is not None}
    unit = next((str(v) for v in grid.values()
                 if isinstance(v, str) and re.search(r"(?i)lakh", v)), "")
    if not unit:
        raise SystemExit("%s: no unit line; expected lakh" % path.name)
    base_row = next(r for (r, col), v in grid.items()
                    if isinstance(v, str) and v.startswith("Base:"))
    year_row = base_row + 1
    markers = sorted((col, re.search(r"(\d{4}-\d{2})", v).group(1))
                     for (r, col), v in grid.items()
                     if r == base_row and isinstance(v, str) and v.startswith("Base:"))
    years = {col: c.fy_normalise(v) for (r, col), v in grid.items()
             if r == year_row and isinstance(v, str)
             and re.fullmatch(r"(19|20)\d{2}-\d{2}", v.strip())}
    out = {}
    names = ps.GSDP_NAMES
    for r in range(year_row + 1, max(rr for rr, _ in grid) + 1):
        label = grid.get((r, 2))
        if not isinstance(label, str):
            continue
        label = c.squeeze(label)
        meta = by_rbi.get(names.get(label, label))
        if meta is None:
            if label in ps.GSDP_SKIP or label in ("A & N Islands", "Andaman and Nicobar Islands") or label.startswith(("‘", "'", "Source")):
                continue
            if r < year_row + 40:
                raise SystemExit("unknown state %r in %s" % (label, path.name))
            continue
        for col, fy in years.items():
            base = [b for mc, b in markers if mc <= col][-1]
            v = ps.money(grid.get((r, col)))
            if v is None:
                continue
            out.setdefault(base, {}).setdefault(meta["code"], {})[fy] = round(
                c.to_crore(v, "lakh"), 2)
    return out


def budget_boundary(series, ref):
    """GSDP on the territory of each state's own budget, year by year."""
    states = {s["code"]: s for s in ref["states"]}
    out = {}
    notes = []
    for base, by_state in series.items():
        for code, ys in by_state.items():
            s = states[code]
            for fy, v in ys.items():
                if c.fy_start(fy) < c.fy_start(s["formed"]):
                    continue            # no budget of its own yet
                total, parts = v, [code]
                for succ in s.get("successors", []):
                    formed = states[succ]["formed"]
                    if c.fy_start(fy) >= c.fy_start(formed):
                        continue        # successor has its own budget now
                    sv = by_state.get(succ, {}).get(fy)
                    if sv is not None:  # successor back-cast: parent is residual
                        total += sv
                        parts.append(succ)
                out.setdefault(code, {}).setdefault(base, {})[fy] = round(total, 2)
                if len(parts) > 1:
                    notes.append((base, fy, "+".join(parts)))
    return out, notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    ref_states, by_rbi = ps.load_states()
    if args.offline:
        ed = c.read_json(REF)
    else:
        ed = discover()
        c.fetch_doc(ed["url"], RAW, referer=HB_INDEX)

    series = read_2018(RAW, by_rbi)
    series.pop("2011-12", None)          # the current Handbook's vintage wins
    current, unit, cur_notes = ps.read_gsdp(CURRENT, by_rbi)
    series["2011-12"] = {k: dict(v) for k, v in current.items()}
    editions = c.read_json(c.REFERENCE / "state_editions.json")
    cur_doc = editions["handbook"]["documents"]["gsdp_current"]

    problems = []
    bases = sorted(series, key=c.fy_start)
    for base in bases:
        for code, ys in series[base].items():
            yrs = sorted(ys, key=c.fy_start)
            if any(v <= 0 for v in ys.values()):
                problems.append("%s %s: a non-positive GSDP" % (base, code))
            gaps = set(range(c.fy_start(yrs[0]), c.fy_start(yrs[-1]) + 1)) - \
                {c.fy_start(y) for y in yrs}
            if gaps:
                problems.append("%s %s: holes at %s" % (base, code, sorted(gaps)))
    # Overlap years: the same state and year on two adjacent bases. A
    # rebasing moves the level by a few per cent to a few tens of per cent;
    # a misaligned column or a lakh/crore slip moves it by an order of
    # magnitude, so anything outside 0.6-1.6 is a parse error, not a break.
    # Compared on the budget's territory, so that a parent printed undivided
    # on one base and residual on the next is not mistaken for either a
    # rebasing or a parse error.
    bb, bnotes = budget_boundary(series, ref_states)
    breaks = []
    for prev, nxt in zip(bases, bases[1:]):
        for code in series[nxt]:
            a = bb.get(code, {}).get(prev, {})
            b = bb.get(code, {}).get(nxt, {})
            for fy in set(a) & set(b):
                r = b[fy] / a[fy]
                breaks.append((prev, nxt, fy, code, r))
                if not 0.6 <= r <= 1.6:
                    problems.append("%s->%s %s %s: new/old = %.2f"
                                    % (prev, nxt, fy, code, r))
    if not breaks:
        problems.append("no overlap years at all; the base markers were misread")
    # Every year 1990-91 onward is on some base for the large states.
    for code in ("UP", "MH", "WB", "TN", "KA", "GJ"):
        have = {c.fy_start(fy) for b in series for fy in series[b].get(code, {})}
        want = set(range(1990, max(have) + 1))
        if want - have:
            problems.append("%s: no GSDP on any base for %s" % (code, sorted(want - have)))
    if problems:
        print("refusing to write data/gsdp.json:")
        for p in problems[:30]:
            print("  -", p)
        raise SystemExit(1)

    segments = []
    for base in bases:
        ys = sorted({fy for v in series[base].values() for fy in v}, key=c.fy_start)
        segments.append({
            "base": base, "first": ys[0], "last": ys[-1],
            "measure": MEASURE[base],
            "source": (cur_doc["label"] + " (current Handbook)" if base == "2011-12"
                       else ed["label"] + " (Handbook of Statistics on Indian "
                       "States, %d)" % ed["edition"]),
            "source_url": cur_doc["url"] if base == "2011-12" else ed["url"],
            "n_states": len(series[base]),
        })
    med = {}
    for prev, nxt, fy, code, r in breaks:
        med.setdefault((prev, nxt, fy), []).append(r)
    break_list = [{"from": p, "to": n, "year": fy,
                   "median_new_over_old": round(sorted(rs)[len(rs) // 2], 3),
                   "states": len(rs)} for (p, n, fy), rs in sorted(med.items())]

    c.write_json({
        "meta": {
            "generated": time.strftime("%Y-%m-%d", time.gmtime()),
            "unit": "Rs crore, current prices",
            "rule": ("Never chain across bases or measures. A share of GSDP "
                     "is a state's own budget figure over budget_boundary"
                     "[state][base][year], on one base; show the break "
                     "wherever a chart crosses a segment boundary."),
            "budget_boundary": ("GSDP on the territory of the state's budget "
                                "that year. Equal to the printed series except "
                                "where a back-cast puts the parent on its "
                                "post-split boundary before the successor had "
                                "a budget; there it is parent + successor, both "
                                "as printed on the same base."),
            "known_issue": ("data/reference/state_gsdp.json, which feeds "
                            "data/states.json, pairs undivided Andhra "
                            "Pradesh budgets for 2011-12 to 2013-14 with "
                            "residual Andhra Pradesh GSDP (Telangana is "
                            "back-cast from 2011-12). budget_boundary here "
                            "is the corrected denominator."),
            "boundary_adjusted": sorted({"%s %s (%s)" % n for n in bnotes}),
            "notes": cur_notes,
        },
        "segments": segments,
        "breaks": break_list,
        "series": {code: {b: series[b][code] for b in bases if code in series[b]}
                   for code in sorted({k for b in series for k in series[b]})},
        "budget_boundary": {code: bb[code] for code in sorted(bb)},
    }, OUT)
    for s in segments:
        print("  base %s: %s to %s, %d states, %s" % (s["base"], s["first"],
                                                     s["last"], s["n_states"],
                                                     s["measure"]))
    for b in break_list:
        print("  break %s -> %s at %s: median new/old %.3f over %d states"
              % (b["from"], b["to"], b["year"], b["median_new_over_old"], b["states"]))
    print("  %d state-years boundary-adjusted" % len(bnotes))


if __name__ == "__main__":
    main()

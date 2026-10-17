"""The layout of a Demand for Grants statement, independent of its container.

A demand is published as a spreadsheet sheet (``alldg.xlsx``, 2019-20 onwards)
or as a PDF table (``alldg.pdf`` and ``dg<N>.pdf``, every edition from
2003-04). Those are two containers for one statement, and it always reads:

    REVENUE SECTION
      <head name>        <major head>   <amount per column ...>
      Total-Revenue Section
    CAPITAL SECTION
      ...
      Total-Capital Section
    GRAND TOTAL                                       <- gross
    Note: ... recoveries ... adjusted in reduction of expenditure
    Revenue Section
      <head name>        <major head>   <negative amounts>
      Total-Revenue Section
    The expenditure provisions, net of the above recoveries, will be as under
    Revenue / Capital / Total                         <- net

So the rules for walking it live here, and each parser only has to turn its
own container into ``Line`` records. Keeping one copy matters because the
rules are the part that is easy to get wrong: see docs/FINDINGS.md.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

MAJOR_HEAD = re.compile(r"^(\d{4})$")

SECTION_HEAD = re.compile(r"^(revenue|capital)\s+section$", re.I)
SECTION_TOTAL = re.compile(r"^total\s*-?\s*(revenue|capital)\s+section$", re.I)
GRAND_TOTAL = re.compile(r"^grand\s+total$", re.I)
NET_LABEL = re.compile(r"^(revenue|capital|total)$", re.I)
DEMAND_NO = re.compile(r"(?:DEMAND\s+)?NO\.?\s*(\d+)", re.I)

# Rows that break a head down by who authorises it, repeating the amount above.
SUBTOTAL_LABEL = re.compile(r"^(charged|voted)$", re.I)

# A running subtotal of the recovery block. It repeats what its section totals
# already say, so emitting it would double count the recoveries.
RECOVERY_TOTAL = re.compile(r"^total\s+recover(y|ies)$", re.I)

ESTIMATE_WORDS = [
    (re.compile(r"\bactual", re.I), "A"),
    (re.compile(r"\brevised", re.I), "RE"),
    (re.compile(r"\bbudget", re.I), "BE"),
]

FY_IN_TEXT = re.compile(r"((?:19|20)\d{2})\s*-\s*((?:19|20)?\d{2})")


def estimate_type(text):
    """'2016-2017 Revised' -> 'RE'. None if the words do not say."""
    return next((tag for pat, tag in ESTIMATE_WORDS if pat.search(text)), None)


def tidy_label(text: str) -> str:
    """Strip the punctuation a stripped Devanagari half leaves behind.

    Both containers print the head name twice, once in each script. Removing
    the Devanagari can leave a lone dash or comma stuck to the English, and
    'Total- Revenue Section' (2003-04) has to read the same as
    '- Total-Revenue Section' (2021-22) for the landmark patterns to fire.
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s.strip(" -‐–—._,;:")


@dataclass
class Line:
    """One printed row: its name, its major head if any, its amounts."""
    label: str
    code: str
    amounts: dict          # column key -> float, for the columns it fills


def walk(lines, cols, *, dept, edition, source_url, source_page):
    """Turn the rows of one demand statement into long-table rows.

    ``cols`` maps a column key to (fiscal_year, estimate_type); ``lines`` is
    the statement in printed order. Returns a list of common.Row.
    """
    out = []
    section = ""
    basis = "gross"
    seen = {}

    def emit(line, account, *, major_head="", head_name="", definition):
        slot = (account, major_head, head_name)
        seen[slot] = seen.get(slot, 0) + 1
        nth = seen[slot]
        for key, (fy, etype) in cols.items():
            v = line.amounts.get(key)
            if v is None:
                continue
            out.append(c.Row(
                fiscal_year=fy, govt="union", estimate_type=etype,
                source_edition=edition, definition=definition,
                major_head=major_head, ministry_or_dept=dept,
                scheme=head_name, account=account, amount_cr=v,
                occurrence=nth, source_url=source_url,
                source_page=source_page,
            ))

    for line in lines:
        label = tidy_label(line.label)
        if not label:
            continue
        if SUBTOTAL_LABEL.match(label):
            continue                    # repeats the head above it
        if RECOVERY_TOTAL.match(label):
            continue                    # repeats the recovery section totals
        m = SECTION_TOTAL.match(label)
        if m:
            section = m.group(1).lower()
            emit(line, "%s_%s" % (basis, section), definition="whole")
            continue
        m = SECTION_HEAD.match(label)
        if m:
            section = m.group(1).lower()
            continue
        if GRAND_TOTAL.match(label):
            emit(line, "gross_total", definition="whole")
            basis = "recovery"          # everything below is netted-off receipts
            continue
        if line.code:
            emit(line, "%s_%s" % (basis, section or "revenue"),
                 major_head=line.code, head_name=label, definition="functional")
            continue
        # The closing block, after the recoveries: bare Revenue / Capital /
        # Total, which is the demand net of them.
        if NET_LABEL.match(label) and basis == "recovery":
            emit(line, "net_" + label.lower(), definition="whole")

    return out + implied_net(out)


def implied_net(rows):
    """A demand with nothing netted against it prints no closing block.

    Its gross *is* its net. Say so explicitly rather than leaving every
    consumer to rediscover the rule: without this, summing net_total across
    demands silently drops the demands that have no recoveries, and the Union
    total comes out about 5% light.
    """
    if any(r.account.startswith("net_") for r in rows):
        return []
    extra = []
    for r in rows:
        # Section and grand totals only: a major-head line shares the account
        # name but is a component, not a total.
        if r.definition == "whole" and not r.major_head and \
                r.account in ("gross_total", "gross_revenue", "gross_capital"):
            clone = c.Row(**dict(r.__dict__))
            clone.account = "net_" + r.account.split("_", 1)[1]
            extra.append(clone)
    return extra

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
TOTAL_ONLY = re.compile(r"^total$", re.I)
DEMAND_NO = re.compile(r"(?:DEMAND\s+)?NO\.?\s*(\d+)", re.I)

# Rows that restate the head above them rather than adding to it: Charged
# and Voted split it by who authorises it, and 'Net Expenditure' closes the
# little sum that demand 25 of 2011-12 (Defence Ordnance Factories) prints
# in place of a single figure - gross expenditure, supplies deducted, net.
# Counted as heads of their own they double the section.
SUBTOTAL_LABEL = re.compile(r"^(charged|voted|net expenditure)$", re.I)

# The note that introduces the netted-off receipts. Usually it follows the
# GRAND TOTAL, which is landmark enough; but an appropriation of a single
# head prints no GRAND TOTAL at all - interest payments, demand 34 of
# 2003-04 - and without this the receipts below it are added to the
# expenditure above instead of being netted off it.
RECOVERY_NOTE = re.compile(
    r"(recoveries|receipts).{0,80}?(shown below|are netted|netted for)", re.I)

# A Union Territory's demand is laid out as one block per ministry, each
# with its own section totals, and then repeats them for the demand as a
# whole: demand 93 of 2003-04 (Andaman and Nicobar Islands) runs to sixteen
# blocks. The block totals are recorded under their own account so that a
# consumer can see the statement is nested - summing its section totals
# counts every head twice.
BLOCK_TOTAL = re.compile(r"^total\s*-?\s*(ministry|department|deptt?)", re.I)

# The sentence that closes the recoveries and opens the net block. It has to
# be a landmark of its own, because the recovery block has a bare 'Total' of
# its own - demand 70 of 2003-04 - and read without this it is taken for the
# demand's net total and the demand ends up with two.
NET_NOTE = re.compile(r"net of .{0,80}?as under", re.I)

# A running subtotal of the recovery block. It repeats what its section totals
# already say, so emitting it would double count the recoveries.
RECOVERY_TOTAL = re.compile(r"^total\s*-?\s*recover(y|ies)$", re.I)

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
    closed = set()      # sections whose total has already been printed

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
            # A head whose English name did not extract is still a head.
            # Demand 70 of 2003-04 nets Rs 1,050.81 crore off under a line
            # printed only in Devanagari, and dropping it leaves the demand
            # Rs 1,050.81 crore larger than the document says it is.
            if line.code and line.amounts:
                emit(line, "%s_%s" % (basis, section or "revenue"),
                     major_head=line.code, definition="functional")
            continue
        if SUBTOTAL_LABEL.match(label):
            continue                    # repeats the head above it
        if RECOVERY_TOTAL.match(label):
            continue                    # repeats the recovery section totals
        if BLOCK_TOTAL.match(label):
            emit(line, basis + "_block", definition="whole")
            continue
        if NET_NOTE.search(label):
            basis = "net"               # what follows is the demand net of them
            continue
        if RECOVERY_NOTE.search(label):
            basis = "recovery"          # everything below is netted-off receipts
            continue
        m = SECTION_TOTAL.match(label)
        if m:
            section = m.group(1).lower()
            emit(line, "%s_%s" % (basis, section), definition="whole")
            closed.add((basis, section))
            continue
        m = SECTION_HEAD.match(label)
        if m:
            section = m.group(1).lower()
            continue
        if GRAND_TOTAL.match(label):
            emit(line, "gross_total", definition="whole")
            basis = "recovery"          # everything below is netted-off receipts
            continue
        # Some statements label a section total with a bare 'Total' rather
        # than 'Total-Revenue Section': demand 64 of the 2007-08 edition
        # (Ministry of Minority Affairs) does, and demand 61 of 2003-04 (the
        # Election Commission), a single head in a single section, has
        # nothing else in it at all. The same word also ends a statement, as
        # the grand total, where there is no GRAND TOTAL line - demand 91 of
        # 2003-04. Which it is depends on whether the section it closes has
        # been totalled already.
        if basis == "gross" and not line.code and TOTAL_ONLY.match(label):
            here = section or "revenue"
            if (basis, here) in closed:
                emit(line, "gross_total", definition="whole")
                basis = "recovery"
            else:
                emit(line, "gross_" + here, definition="whole")
                closed.add((basis, here))
            continue
        if line.code:
            emit(line, "%s_%s" % (basis, section or "revenue"),
                 major_head=line.code, head_name=label, definition="functional")
            continue
        # The closing block, after the recoveries: bare Revenue / Capital /
        # Total, which is the demand net of them.
        if NET_LABEL.match(label) and basis == "net":
            emit(line, "net_" + label.lower(), definition="whole")

    out += implied_gross(out)
    return out + implied_net(out)


def implied_gross(rows):
    """A demand of one head prints no total, because the head is the total.

    Defence Pensions is one: demand 21 of 2010-11 is a single line against
    major head 2071 and stops there, with no Total-Revenue Section and no
    GRAND TOTAL. Read strictly it adds nothing to the year, and Rs 25,000
    crore goes missing. The total is therefore added up from the components
    the document does print - its own section totals where it gives them,
    otherwise its major heads.
    """
    if any(r.account == "gross_total" for r in rows):
        return []
    parts = [r for r in rows if r.definition == "whole" and not r.major_head
             and r.account in ("gross_revenue", "gross_capital")]
    if not parts:
        parts = [r for r in rows if r.definition == "functional"
                 and r.account.startswith("gross_")]
    if not parts:
        return []
    total = {}
    for r in parts:
        key = (r.fiscal_year, r.estimate_type)
        total[key] = total.get(key, 0.0) + r.amount_cr
    first = parts[0]
    return [c.Row(**dict(first.__dict__, fiscal_year=fy, estimate_type=etype,
                         definition="whole", major_head="", scheme="",
                         occurrence=1, account="gross_total", amount_cr=v))
            for (fy, etype), v in total.items()]


def implied_net(rows):
    """Add the closing block where the statement does not print one.

    A demand with nothing netted against it prints no closing block, because
    its gross *is* its net. Say so explicitly rather than leaving every
    consumer to rediscover the rule: without this, summing net_total across
    demands silently drops the demands that have no recoveries, and the
    Union total comes out about 5% light.

    Where a demand does net something off but the sentence that introduces
    its closing block cannot be read, the recoveries are subtracted here
    instead, so that net always means net. Demand 22 of the 2007-08 edition
    (Defence Services - Army) is such a case: the sentence is printed twice,
    a few points apart, and extracts as the two copies interleaved letter by
    letter.
    """
    if any(r.account.startswith("net_") for r in rows):
        return []
    recovered = {}
    for r in rows:
        if r.major_head and r.account.startswith("recovery_"):
            section = r.account.split("_", 1)[1]
            for part in (section, "total"):
                key = (r.fiscal_year, r.estimate_type, part)
                recovered[key] = recovered.get(key, 0.0) + r.amount_cr
    extra = []
    for r in rows:
        # Section and grand totals only: a major-head line shares the account
        # name but is a component, not a total.
        if r.definition == "whole" and not r.major_head and                 r.account in ("gross_total", "gross_revenue", "gross_capital"):
            part = r.account.split("_", 1)[1]
            clone = c.Row(**dict(r.__dict__))
            clone.account = "net_" + part
            clone.amount_cr += recovered.get(
                (r.fiscal_year, r.estimate_type, part), 0.0)
            extra.append(clone)
    return extra

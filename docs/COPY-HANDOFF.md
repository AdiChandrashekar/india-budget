# Copy handoff: what needs writing, and the numbers behind it

Every block of text on the page, with the data it has to be true to. Written
for someone drafting the explainer copy away from the codebase.

**The rule.** A number is either computed from the pipeline, in which case it
is injected at render time and must not be typed into prose, or it is cited
from outside, in which case it needs a source in the footer's claims list.
Nothing in between. If a sentence needs a number that is in neither category,
it cannot be written yet — say so and it will be sourced.

**What the current copy gets wrong.** It describes the instrument rather than
the subject: how a definition was computed, why an edition was chosen, what a
dashed line means. That belongs in captions and footnotes at most. The body
text should be about Indian education finance, not about this tool.

Placeholders below are the exact template slots. `{moe_be}` etc. are filled
from the data at render time; write around them, don't substitute numbers.

---

## 1. Masthead

**Needs:** a standfirst of 40-60 words that states the argument of the whole
piece and makes someone want to read it.

**The argument to land:** India set itself a 6%-of-GDP education target in
1966 and has never hit it; it cannot even agree how far short it is; and the
tier of government that does most of the spending is the one nobody argues
about.

**Data available:** `{union_first_year}`–`{union_last_year}` (2002-03 to
2026-27), states 1990-91 to 2025-26.

---

## 2. Section: the three definitions

**Needs:** 60-90 words explaining why three defensible definitions exist and
why the choice is political rather than technical. Then a short note under the
chart on what each definition is *for* — who uses it and to argue what.

**The substance:** these are not three attempts at the same number. The
ministry figure is an accountability measure (what this ministry was given).
The functional figure is a comparability measure (what any government spent on
this function, in a classification the Union and every state share). The
narrow functional figure strips out sports and culture, which the shared
classification bundles with education.

**Numbers (2026-27 BE):**

| Definition | Rs crore | % of Union spending |
| --- | --- | --- |
| Ministry of Education | 1,39,289.48 | 2.60% |
| Functional, incl. sports and culture | 1,16,883.59 | 2.19% |
| Functional, education only | 1,09,519.85 | 2.05% |

Spread between widest and narrowest: **Rs 29,770 crore**.

**Worth saying:** that spread is larger than the entire budget of several
ministries. It is also larger than the year-on-year increase that gets
reported as the headline each February.

---

## 3. Section: the 6% target

**Needs:** 80-120 words on the history of the target and why sixty years of
restating it has not moved it. Then a note on why the measurements disagree.

**The substance:**
- The Education Commission of 1964-66 (Kothari) proposed 6% of national
  income by 1985-86.
- Adopted in the National Policy on Education 1968; repeated 1986; restated
  by NEP 2020, which commits centre and states to reach 6% "at the earliest".
- Published measurements today: **2.7%** (Economic Survey 2024-25, for
  2023-24, education departments only), **4.1%** (PRS citing World Bank, for
  2022), **4.6%** (Ministry of Education's broader ABE measure, 2020-21).
- The 1.9-point spread between the narrowest and broadest reading is the same
  definitional problem as section 2, applied to the most-quoted number in
  Indian education policy.

**Angle worth taking:** a target that has survived six decades and three
policy documents without being met, and which cannot be measured to better
than two percentage points, is doing political work rather than fiscal work.
Be careful not to assert motive; state what is observable.

**Now available:** the page can compute % of GDP itself (`data/gdp.json`),
and the ABE's own combined figure is in `data/abe.json`: 4.04% for 2019-20 on
the broad definition and 2.73% on education departments alone, which brackets
the Economic Survey's 2.7%. The PRS/World Bank figure stays cited. See the data
gaps at the end.

---

## 4. Section: who actually pays

**Needs:** 80-120 words on the division of responsibility, why it is
counter-intuitive, and what the ratio means for where education policy is
actually decided.

**The substance:**
- Education is on the Concurrent List: both tiers legislate and both spend.
- On the shared functional heads, 2025-26 BE: states and UTs
  **Rs 9,08,331.68 crore**, Union **Rs 1,01,xxx crore** (injected), a ratio
  of about **9 : 1**.
- Almost all national commentary concerns the Union's number.
- The Union's own money mostly leaves as grants-in-aid (head 3601) rather
  than being booked by the Union under education at all.

**Angle worth taking:** if nine rupees in ten are state rupees, then a
national debate conducted entirely over the tenth is mis-aimed. The lever that
matters is thirty-odd state budgets, not one Union budget.

**Caution:** never describe the two as additive. The grants appear in both.

---

## 5. Section: education's share of state budgets

**Needs:** 100-150 words. This is the analytical heart of the piece and
deserves the most care.

**The substance:** rupee totals always rise; the share is the choice. All
states together:

| Year | Share |
| --- | --- |
| 1990-91 | 17.4% |
| 2000-01 | 20.7% (peak) |
| 2010-11 | 16.6% |
| 2025-26 BE | 13.1% |

**Two things need explaining and I could not source either:**

1. **Why the share peaked around 2000-01 and fell.** Candidate explanations
   worth checking: the Fifth Pay Commission's effect on state salary bills in
   the late 1990s raising education's share, then its unwinding; the shift of
   elementary education funding to centrally sponsored schemes (SSA from
   2001-02) moving spending onto Union books; rising interest and pension
   commitments crowding out discretionary spending.
2. **Why it has slid since 2010-11.** Candidates: committed expenditure
   (salaries, pensions, interest) growing faster than budgets; the rise of
   cash-transfer and welfare schemes competing for the same rupee; falling
   school-age population in several states reducing demand-side pressure.

Both need a source before they go on the page. Do not assert them.

**One thing that must be flagged, not explained away:** the 2004-05 figure
(12.7%) is a break in the denominator, not a collapse in education spending.
Aggregate state expenditure jumped about 50% that year while education
spending grew normally. The debt-swap scheme running 2002-03 to 2004-05 is a
candidate cause but I could not confirm it accounts for the size of the jump.

**State spread, latest year (2025-26 BE):** Bihar 20.0%, Delhi 19.0%,
Himachal Pradesh 17.5% at the top; Punjab 9.3%, Arunachal Pradesh 8.8%,
Telangana 7.8% at the bottom. All-states 13.1%. The spread between states
(12.2 points) is far wider than the all-states movement over 35 years.

**Angle worth taking:** the variation that matters is cross-sectional, not
temporal. Something about Bihar's fiscal choices differs from Telangana's by
more than any national trend. A high share can also mean a small budget
rather than a generous one — worth noting that share and per-child spending
are different questions, and this data answers only the first.

---

## 6. Section: budgeted against spent

**Needs:** 60-90 words on why the three published versions of a year diverge
and which one a reader should believe.

**Numbers, Ministry of Education (Rs crore):**

| Year | BE | RE | Actual | Actual as % of BE |
| --- | --- | --- | --- | --- |
| 2015-16 | 69,074.76 | 67,585.50 | 67,239.15 | 97.3% |
| 2016-17 | 72,394.00 | 73,599.24 | 72,015.76 | 99.5% |
| 2017-18 | 79,685.95 | 81,868.71 | 80,214.67 | 100.7% |
| 2018-19 | 85,010.29 | 83,625.86 | 80,344.84 | 94.5% |
| 2019-20 | 94,853.64 | 94,853.64 | 89,436.56 | 94.3% |
| 2020-21 | 99,311.52 | 85,089.07 | 84,219.40 | 84.8% |
| 2021-22 | 93,224.31 | 88,001.52 | 80,352.42 | 86.2% |
| 2022-23 | 1,04,277.72 | 99,881.13 | 97,196.36 | 93.2% |
| 2023-24 | 1,12,899.47 | 1,29,718.28 | 1,23,364.96 | 109.3% |
| 2024-25 | 1,20,627.87 | 1,14,053.55 | 1,10,735.77 | 91.8% |

**Worth saying:** the two pandemic years are the clear underspend (84.8% and
86.2%). 2023-24 is the one year spending exceeded the opening estimate, by
9%. Otherwise the pattern is a consistent few points of shortfall.

**Cross-check available:** PRS reports Samagra Shiksha utilisation averaging
86% a year, and only 47% of higher-education research and innovation funds
used on average between 2017-18 and 2024-25. Useful for a line about where
the shortfall concentrates.

---

## 7. Section: where the money sits in the accounts

**Needs:** 60-90 words. This is the double-counting trap and the reason the
Union number understates the centre's role.

**Numbers (2026-27 BE, Ministry of Education gross, Rs crore):** grants-in-aid
to states (3601) 1,07,877.77; general education (2202) 72,068.62; technical
education (2203) 33,730.38; North Eastern Areas (2552) 12,384.64;
grants-in-aid to UTs (3602) 2,500.44.

**The substance:** the ministry's largest single head is not education. Money
routed as grants is spent and re-booked by states under 2202, which is why
Union and state figures cannot be summed and why the Union's functional
education figure understates what the centre funds.

**Cited context:** Samagra Shiksha is cost-shared 60:40 (90:10 for
north-eastern and Himalayan states) and is Rs 42,100 crore in 2026-27, about
30% of the ministry's budget.

---

## 8. Section: scale against the whole budget

**Needs:** 50-80 words putting 2.6% in perspective.

**Numbers (2026-27 BE):** total Union expenditure Rs 53,47,314.81 crore across
102 demands. Interest payments Rs 14,03,971.79 crore (26.3%) is the largest
single demand. Education departments together 2.60%.

**Angle worth taking:** the comparison with interest payments is the honest
one — a tenth of the budget goes on education for every quarter that goes on
servicing past borrowing.

---

## 9. The 2015-16 break

**Currently a chart annotation; deserves a paragraph.**

**Numbers:** Ministry of Education BE fell from Rs 82,771.10 crore (2014-15)
to Rs 69,074.76 crore (2015-16), a 16.5% fall, while total Union expenditure
barely moved (Rs 17,64,791.96 crore to Rs 17,37,477.04 crore).

**The substance, sourced:** the Fourteenth Finance Commission raised the
states' share of the divisible pool of central taxes from 32% to 42% with
effect from 2015-16. Centrally sponsored scheme sharing was reset at the same
time; Sarva Shiksha Abhiyan moved to 60:40.

**The honest framing:** this was not a cut in education spending, it was a
transfer of who writes the cheque. Whether total education spending rose or
fell across both tiers that year can now be answered from the ABE's
Centre-plus-states series (`data/abe.json`, `national`): Centre and states
together, all departments, rose from Rs 5,06,849 crore in 2014-15 to
Rs 5,77,793 crore in 2015-16, while the Centre's own part went from
Rs 1,33,392 crore to Rs 1,42,563 crore.

---

## Data gaps that constrain the copy

Write around the ones still open; do not paper over them. Updated 18 October
2026. How each was closed, and what is still missing, is in
`docs/FINDINGS.md` under "Closing the data gaps".

### Closed

1. **GDP series — closed.** `data/gdp.json` holds GDP at current prices from
   the RBI Handbook on three bases, kept separate and never chained: 2004-05
   (to 2011-12), 2011-12 (to 2024-25) and 2022-23 (from 2022-23). The page can
   now compute any series as a share of GDP. It must show a break at 2011-12
   and 2022-23, the two rebasings, each of which lowers the level of GDP by
   about 3 per cent and so raises any share of it. There is no GDP yet for 2026-27, the year of the
   current budget estimate.
2. **State sub-sector split — closed for 2007-08 to 2021-22.** The ministry's
   *Analysis of Budgeted Expenditure on Education* turned up in the Wayback
   Machine's CDX index (twelve editions), and `data/abe.json` has each state's
   spending on elementary, secondary, adult, university, technical, general
   and language education. Two caveats for the copy: it is *revenue*
   spending of the *education departments* only, which is the ABE's own
   definition and not the e-STATES group the rest of the state view uses;
   and four 2017-20 pages are unreadable at source, so secondary, adult,
   university and language have no 2017-18 actual.
3. **Union actuals before 2015-16 — closed back to 1997-98.** The earlier
   claim that they existed only in the accounts was wrong: Expenditure Budget
   Vol. I, Statement 2 prints them in every edition. `data/union_actuals.json`
   has total expenditure and every department's actuals, 1997-98 to 2014-15,
   and each year's total matches Budget at a Glance. The detail is the
   department, not the major head, and the documents call most of these
   actuals provisional.
4. **Centre-plus-state total — closed, from the ABE only.** `data/abe.json`
   (`national`) is the ABE's own Table 4, 2000-01 to 2021-22, which counts
   each rupee once. Section 3's figures can now be stated from the data:
   **4.04%** of GDP in 2019-20 (actual) on the broad definition (education
   and other departments), **2.73%** on education departments alone; 4.36%
   and 2.95% in 2020-21 (revised). The test that the Union and state files
   carry no combined figure still stands: never add them together.
5. **State GSDP before 2011-12 — closed back to 1990-91.** `data/gsdp.json`
   has five base segments (1980-81, 1993-94, 1999-00, 2004-05, 2011-12). The
   bases before 2011-12 measure GSDP at factor cost, so the share-of-GSDP
   ranking must show breaks rather than one line. A correction also comes
   with it: `data/states.json` currently divides undivided Andhra Pradesh's
   2011-12 to 2013-14 budgets by residual-AP GSDP. `gsdp.json`'s
   `budget_boundary` is the right denominator, and any AP share-of-GSDP
   figure for those years should be rechecked against it.
7. **Scheme-level series — closed.** `data/schemes.json` follows twelve
   schemes across renames and mergers, 1998-99 to 2026-27, from 54 Statements
   of Budget Estimates: Samagra Shiksha (with SSA, RMSA and Teacher Education
   before the 2018 merger), PM POSHAN (Mid-Day Meal), DPEP, Operation
   Blackboard, Mahila Samakhya, KGBV, adult literacy, RUSA/PM-USHA, KVS,
   NVS, NCERT and UGC. Section 7's PRS citations can now be checked: in the
   budget documents' own figures, Samagra Shiksha's actuals averaged 88.8% of
   its budget estimate over 2017-18 to 2024-25 (PRS says 86%), with lows of
   71.8% in 2020-21 and 80.7% in 2021-22. Scheme actuals exist only from
   2009-10.

### Still open

6. **No enrolment data**, so no per-child figures. UDISE+ would supply it.
   Not attempted in this round.
8. **No 2015-16 actuals in the ABE.** The edition that would carry them
   survives only as a scan without a text layer. Union and state totals for
   2015-16 exist elsewhere; the sub-sector split for that year does not.
9. **The ABE's early % of GDP is not recomputable.** For 2000-01 to 2010-11
   the ABE divides by an older GDP vintage than any in `data/gdp.json`. Quote
   those percentages as the ABE's, not as computed by the page.
10. **Union detail before 2015-16 is by department, not by major head.** The
    functional (major-head) definition of section 2 still starts in 2002-03
    for budget estimates and in 2015-16 for actuals.

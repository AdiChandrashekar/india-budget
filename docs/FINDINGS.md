# What the sources actually look like

Notes from building the pipeline, 17 October 2026. This exists because several
assumptions in the original handoff brief turned out to be wrong, and because
the next person to extend this will hit the same things.

## Corrections to the handoff brief

| Brief said | Actually |
| --- | --- |
| RBI Statement 26 at `website.rbi.org.in/documents/d/rbi/statement-26_sf2026` | Redirects to the RBI home page. The state layer needs a new entry point before work starts. |
| ABE PDF at `education.gov.in/.../budget_exp_2020_22.pdf` | 404. |
| Excel for Expenditure Budget "from about 2012-13" | Per-demand Excel starts with the **2017-18** edition. The bundled `alldg.xlsx` exists only for 2019-20, 2024-25, 2025-26 and 2026-27. Everything earlier is PDF. |
| Union data "1996-97 to 2026-27 digital" | True for documents, but 1996-97 and 1997-98 have no reachable Expenditure Budget directory. Verified coverage starts at **1998-99**. |
| "Key on ministry and department names, not on demand numbers" | Correct, and more important than it sounds — see below. |

The education fixtures in the brief were all exactly right, and all four
reproduce.

## The site has four URL generations

Only the directory prefix moves; the filenames (`dg25`, `sbe25`, `stat10a`,
`alldg`, `dgsum`) are stable across thirty years.

| Editions | Expenditure Budget directory |
| --- | --- |
| 1998-99 – 2010-11 | `budget_archive/ub<YYYY-YY>/eb/` |
| 2011-12 – 2018-19 | `budget<YYYY-YYYY>/ub<YYYY-YY>/eb/` |
| 2019-20 – 2025-26 | `budget<YYYY-YY>/doc/eb/` |
| current (2026-27) | `doc/eb/` |

Interim budgets live at their own prefix with `(I)` in it, and are recorded
but excluded from the series: they are vote-on-account documents, not full
budgets.

The resolved map, with the formats each edition serves, is
`data/reference/union_editions.json`.

## Three traps that produce plausible wrong numbers

These all pass a smell test. Each was caught by a validation check, not by
reading the output.

### 1. HEAD requests lie, and so does the 404 page

`indiabudget.gov.in` 404s a HEAD request for `.xlsx` files it will happily
serve on GET, and returns a **200 HTML page** for files that do not exist. A
naive existence check therefore reports the opposite of the truth in both
directions.

The fix is `head_ok()` in `discover_union.py`: request the first kilobyte and
check the file's magic number (`PK` for xlsx, `%PDF` for pdf). It costs one
small GET per probe and is right every time.

### 2. A year in the link text is not the year of the budget

The previous-budgets index carries links like *"Implementation of Budget
Announcements 2019-2020"* and *"Output Outcome Framework 2020-2021"* that
point at the **current** year's documents. Reading the year off the link text
attributed 2026-27's workbook to 2019-20 and 2020-21 — and because the file
downloads fine and parses fine, nothing complained. It surfaced only because
three editions produced byte-identical files.

The year now comes from the href, never the label.

### 3. Demand numbers are not identifiers

The demand list was re-alphabetised. The education departments were **Demands
57 and 58** in the 2019-20 edition and **25 and 26** from 2024-25. Of the 100
demand numbers common to both editions, 99 point at a different department.

Grouping a time series by demand number therefore splices unrelated ministries
into one line, and it looks entirely reasonable on a chart. Everything is
keyed on a normalised department name instead (`common.dept_key`), with an
alias table for genuine renames.

## Reading a demand sheet

Each sheet in `alldg.xlsx` is one demand, laid out as: gross provision by
major head, split into revenue and capital sections; then a block of receipts
netted against that expenditure; then the net. Four columns of money: actuals
for t-2, BE and RE for t-1, BE for t.

Things that bite:

- **Row offsets differ between sheets.** Every landmark has to be found by its
  text. Demand 25 starts at row 3, demand 1 at row 4.
- **Cells are bilingual**, Devanagari then English, separated by non-breaking
  spaces. Stripping the Devanagari can leave its punctuation behind, so a
  department name comes out as `-` or `,`. Guard before using such a name.
- **Appropriations are not labelled in English.** Demands 39, 40, 67, 75, 80
  and 83 are headed `NO. 39 (APPROPRIATION)` — the word "Demand" appears only
  in Devanagari. A parser looking for `DEMAND NO.` silently skips them, and
  they include Interest Payments at Rs 14.04 lakh crore.
- **A numeric cell stringifies into something that looks like a label.** The
  only reliable way to tell a head name from a number is to anchor on the
  first money column and treat everything left of it as label.
- **Charged/Voted sub-rows repeat the amount above them.** Skip them or
  double count.
- **A demand with no recoveries prints no net block**, because its gross is
  its net. Summing `net_total` without handling this drops 8 demands and the
  Union total comes out 5% light.
- **One statement can list the same head twice and mean different numbers.**
  Demand 40 nets receipts under two separate notes, both against head 6001.

## Why an edition is chosen whole

Editions overlap: up to three describe the same year and estimate type for the
same demand. The later edition wins, because it is the more revised.

The unit of choice has to be the whole `(year, estimate_type, demand)` group,
not the individual line. A line-level merge looked tidier and was wrong: the
documents do not lay a demand out the same way twice, so it kept a line from
each edition and double-counted Rs 90 lakh crore on demand 40. Taking the
group whole guarantees a demand-year comes from a single published statement.

## Next

1. **PDF era.** `dg<N>.pdf` exists for every edition from 2003-04. Parsing it
   closes the 2020-21 and 2021-22 gap and extends the series back twenty
   years. The table shape is the same as the Excel; needs `pdfplumber`, which
   is not currently installed.
2. **Statements of Budget Estimates** (`sbe<N>`) for scheme-level detail —
   Samagra Shiksha, PM POSHAN and so on, with the lineage table the brief
   asks for.
3. **Denominators.** GDP, a deflator and UDISE+ enrolment, to get off nominal
   rupees. State GSDP is now loaded, so state ratios exist from 2011-12; the
   Union half is still nominal only.

---

# The state layer

Notes from building it, 17 October 2026. The state half is a different
publisher, a different document format and a different set of traps from the
Union half.

## Corrections to the handoff brief

| Brief said | Actually |
| --- | --- |
| Statement 26 at `website.rbi.org.in/documents/d/rbi/statement-26_sf2026` | Redirects to the RBI home page. The old-style index at `rbi.org.in/Scripts/AnnualPublications.aspx?head=State+Finances+...` still ships every document link in its HTML and is what the pipeline reads. |
| "Stitch several RBI editions together for depth, checking first how many years each workbook carries" | Checked: **one** edition carries 1990-91 to 2025-26, all 36 years. The e-STATES database that ships with the current volume is a tidy 397,575-row long table, not a per-year snapshot. There is nothing to stitch, and stitching would have been actively wrong — see "Why one edition" below. |
| The MoE *Analysis of Budgeted Expenditure on Education* PDF | Still 404, and no replacement found. **So the sub-sector split is not in this repository.** See "What is missing" below. |
| RBI's Handbook "carries state-wise social sector expenditure from 1990-91 and GSDP" | Both true. GSDP (Table 21) runs 2011-12 to 2024-25 only, so GSDP ratios cannot go back further. |

The brief's two numbers for the state layer — 13.1% for 2025-26 and 16.6% for
2010-11 — are both exactly right, and are now two of 570 checked cells.

## The documents are behind a bot defence

`rbi.org.in` serves its index pages to anything. The documents those pages
link to live on `rbidocs.rbi.org.in` behind an F5/Shape defence, and asking it
for a workbook with a plain `urllib` request returns **HTTP 200, a
Content-Type of `text/html`, and 45 kB of obfuscated JavaScript**. The request
succeeds. Bytes arrive. Nothing looks wrong until `openpyxl` says "not a zip
file".

This is the same class of failure as `indiabudget.gov.in` returning a 200 HTML
page for a missing file, and it has the same fix — check the magic number,
never the status code — plus two more:

1. **Keep a cookie jar for the whole run.** The challenge is satisfied by
   cookies, not by solving anything.
2. **Read the index page first, and send it as the `Referer`.** The index on
   `rbi.org.in` sets an `f5_cspm` cookie, and a document request without it is
   challenged indefinitely. Retrying alone does *not* work: five retries with
   a warm jar but no referer were challenged five times. Fetching the index
   first turns that into a first-attempt success.

`common.warm()`, `doc_get()`, `doc_ok()` and `fetch_doc()` do this. It is also
the politer behaviour: the pipeline arrives at a document by reading the page
that links to it.

## Three traps in the state data

### 1. Pre-formation years are padded with zeros, not blanks

This is the one that would have shipped a confident lie. e-STATES carries a
row for every (appendix, state, head, year) combination in its grid, including
years before a state existed, and fills them with a literal `0` rather than
leaving them empty. Chhattisgarh has education rows for 1990-91 through
1999-2000, all zero. Telangana has them back to 1990-91.

Parse that naively and Chhattisgarh spends nothing on education for six years
before it exists, a chart draws a confident line along the axis, and any
cross-state average is diluted by states that were not there.

A zero cannot simply be dropped, because a genuine nil is common: several
states really do lend nothing for education in a given year. So the test is
applied to the **entity**, not the number. If a state's total revenue
expenditure is zero, it had no budget on that basis and the whole cell goes;
within a cell it did have, a zero on a particular head is a real nil and is
kept.

The scope test also has to run **per estimate type**, not per year. Puducherry
has published accounts for 2005-06 but zero-filled revised and budget
estimates for the same year. Keying the filter on the year alone readmits
exactly the empty cells it was meant to exclude — which it did, and which
`validate_states.py` caught.

Derived from the data, the first year each entity has a budget is:
Chhattisgarh and Uttarakhand 2000-01, Jharkhand 2001-02, Telangana 2014-15,
Delhi 1993-94, Puducherry 2005-06. Those match the reorganisation dates and
Delhi's 1993 assembly exactly, so `data/reference/states.json` records them
and `parse_states.py` refuses to write if the data stops agreeing.

### 2. "Aggregate expenditure" is not what it sounds like

Statement 26's denominator is not revenue expenditure plus capital outlay plus
loans, which is the natural reading and gives 14.3% where RBI prints 13.1%. It
is **total revenue expenditure plus total capital disbursements excluding the
public account** — the `Total$` line of Appendix 4, which is *smaller* than
the sum of that appendix's own numbered parts.

Nor is it the `Total:` line next to it, which sweeps in the public account and
runs to Rs 1.1 crore crore.

Guessing was never going to settle this. Recomputing all 570 published
percentages and requiring every one to match did: the combination above is the
only one that reproduces them, and it reproduces all of them, worst gap 0.00
percentage points. The numerator is revenue expenditure plus capital outlay,
with loans excluded — which the statement's own footnote says, and which the
arithmetic confirms.

### 3. The last column of Statement 26 is mislabelled

Its header reads `2025-26 (RE)`. There is no revised estimate for 2025-26
anywhere in e-STATES; the volume is the study of the 2025-26 *budgets*; and
the e-STATES notes say the database runs "1990-91 to 2025-26 (Budget
Estimates)". It is a typo for `(BE)`. Read as RE, the entire last column —
all 32 cells — has nothing to compare against, which is how it was noticed.

## Why one edition, and why that is better

Several editions would have given no extra years, because the current e-STATES
carries the whole span. More importantly, splicing editions would have
*damaged* the data. RBI revises a state's history: a 2015-16 figure is a
budget estimate in one volume, a revised estimate in the next and an accounts
figure two volumes later, and the accounts figure can differ from the budget
estimate by a third. Taking each year from its own edition would mix those
vintages into one line, exactly the way the Union half's line-level merge
double-counted Demand 40.

One edition means one vintage: every number here is how RBI described it in
January 2026. The `estimate_type` column says which of the three each number
is, and a share should be read as actuals-over-actuals or BE-over-BE, never an
outturn over a forecast.

## What RBI does not publish, and what is therefore missing

**The sub-major-head split is not here.** e-STATES reports the functional
group "Education, Sports, Art and Culture" — not elementary against secondary
against higher education. There is no state-wise 2202-01 / 2202-02 / 2202-03
series in either RBI volume, and the one source that would give it, the
ministry's *Analysis of Budgeted Expenditure on Education*, is the brief's
404. So the brief's sub-major-head ambition is **not met**, and no estimate of
it has been invented.

What the group does map to, exactly:

| e-STATES line | LMMHA major heads | Exact? |
| --- | --- | --- |
| Appendix 2, `I.A.1` revenue expenditure | 2202, 2203, 2204, 2205 | the group, not separable |
| Appendix 4, `I.1.a.1` capital outlay | 4202 | exact, single head |
| Appendix 4, `IV.1.a.1` loans and advances | 6202 | exact, single head |
| Appendix 1, `II.C.4.i` revenue receipts | 0202 | exact, single head |

That group is the same functional definition the Union view already computes,
which is the point: it is what makes the two halves comparable at all.

Also absent: a legitimate centre-plus-state total. Both candidate sources
(the ABE and the CAG's Combined Finance and Revenue Accounts) are unparsed, so
the repository does not publish one, and `data/states.json` deliberately
contains no combined key — there is a test asserting it does not.

## Two things that look like parser bugs and are not

- **A state's net capital outlay or net loans can be negative.** Punjab's net
  capital outlay in 1996-97 was minus Rs 239 crore, because recoveries
  exceeded fresh outlay. Education's own positive line then "exceeds" the
  state total without anything being wrong, so the containment checks skip a
  negative total and report the count instead of failing.
- **Appendix 1 repeats a head.** Jharkhand's "Other Taxes and Duties on
  Commodities and Services" appears twice for each of 2018-19 to 2021-22. The
  long table's `occurrence` column, added for Demand 40 on the Union side,
  handles it unchanged.

## Handover: what the state pipeline produces

For wiring into the page.

```
scripts/discover_states.py   resolve + verify URLs -> data/reference/state_editions.json
scripts/fetch_states.py      download + manifest   -> data/raw/states/
scripts/parse_states.py      -> data/processed/state_education.csv
                             -> data/processed/state_statement26.csv
                             -> data/reference/state_gsdp.json
scripts/build_states_site.py -> data/states.json
scripts/validate_states.py   called by scripts/validate.py
```

`data/processed/state_education.csv` is the archive, in the project's existing
long-table shape and columns, with `govt="state"` and an ISO 3166-2:IN
`state_code`. 22,644 rows. `definition` is `functional` for the education
lines and `whole` for the denominators; `account` is one of
`revenue_expenditure`, `capital_outlay`, `loans_and_advances`,
`revenue_receipts`, `capital_disbursement`; `scheme` carries RBI's own head
label and `source_page` the appendix and line it came from.

`data/states.json` is what a page should read. 647 kB, same spirit as
`union.json`:

```
meta      years[] (1990-91..2025-26), unit, edition, source, source_index,
          estimate_types{A,RE,BE}, definition, share_definition,
          never_add (the double-counting warning, as text),
          gsdp{years[],unit,source,source_url,notes[]}
states[]  code, name, kind (state|ut_with_legislature|aggregate), parent,
          successors[], formed, note, first_year, last_year, has_gsdp
series    { <state_code>: { <measure>: { <year>: { A|RE|BE: number } } } }
          measures: education_revenue, education_capital, education_loans,
                    education_receipts, education_spend, social_services,
                    total_revenue, total_capital_outlay, total_loans,
                    total_capital_disbursement, aggregate_expenditure
                    plus gsdp, which is { <year>: number } with no basis
union_functional  the Union's functional education series, for contrast
```

Three things a page has to get right:

1. **Shares are not precomputed, on purpose.** Divide `education_spend` by
   `aggregate_expenditure` *on the same estimate type*, which is the
   arithmetic checked against Statement 26. Reading the denominator with its
   own independent fallback mixes a budget estimate into an actuals share.
2. `ALL` is RBI's own aggregate, **not** a sum of the other rows: before
   2017-18 it excludes the union territories. Never recompute it, and never
   present it as a total of the rows above it.
3. Parent and successor states are separate series and must not be merged or
   added. Andhra Pradesh before 2014-15 is the undivided state; `successors`
   and `parent` mark exactly where each series breaks, and `meta.never_add`
   should be shown wherever a Union figure sits near a state one.

Shares of GSDP exist only for 2011-12 to 2024-25 and only for the 31
individual entities; `ALL` has none, because the Handbook has no all-India row
in that table. GSDP for Telangana is back-cast by the national accounts to
2011-12, three years before Telangana had a budget, so `first_year` is
computed from the budget series alone — a test asserts it.

A few figures worth knowing before designing anything: on this definition the
states and UTs budget Rs 9.08 lakh crore for 2025-26 against the Union's
Rs 1.17 lakh crore for 2026-27, a ratio of 7.8 to 1. The all-states share of
their own budgets has fallen from 20.7% in 2000-01 to 13.1%. Bihar spends the
largest share (20.0%) and Telangana the smallest (7.8%); Kerala is 24th of 31
at 11.9%. Ranking by share of GSDP roughly inverts that, with Arunachal
Pradesh at 8.3% of GSDP and Delhi and Karnataka at 1.3%.

A draft of the state section (an `index.html` block, `js/states.js` and
`css/states.css`, written against the pre-redesign page) is parked outside the
repository in this session group's shared notes folder, under
`state-view-draft/`. It is not wired in: the frontend was being redesigned at
the same time, so step 6 of the brief was handed back rather than collided
with.


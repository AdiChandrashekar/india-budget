# What the sources actually look like

Notes from building the pipeline, 17 October 2026. This exists because several
assumptions in the original handoff brief turned out to be wrong, and because
the next person to extend this will hit the same things.

## Corrections to the handoff brief

| Brief said | Actually |
| --- | --- |
| RBI Statement 26 at `website.rbi.org.in/documents/d/rbi/statement-26_sf2026` | Redirects to the RBI home page. The state layer needs a new entry point before work starts. |
| ABE PDF at `education.gov.in/.../budget_exp_2020_22.pdf` | 404. |
| Excel for Expenditure Budget "from about 2012-13" | Per-demand Excel starts with the **2017-18** edition. The bundled `alldg.xlsx` exists only for 2019-20, 2024-25, 2025-26 and 2026-27. Everything earlier is PDF, and is now read as PDF; see "The PDF era" below. |
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

Editions overlap: up to four describe the same year and estimate type. The
later edition wins, because it is the more revised — on its date alone, never
on whether it arrived as a workbook or as a PDF.

The unit of choice is the whole `(year, estimate_type)`. It began as the
`(year, estimate_type, demand)` group, because a line-level merge kept a line
from each edition and double-counted Rs 90 lakh crore on demand 40. Adding
the PDF editions made even the demand too small a unit, for the reason set
out under "Demand numbers are not identifiers" above: `(2021-22, BE)` is
published by both the 2021-22 and the 2022-23 editions, and between them
demand 1 changed from the Department of Agriculture, Cooperation and Farmers'
Welfare to the Department of Agriculture and Farmers Welfare. Keyed on the
number, a year splices two departments into one line; keyed on the name, a
rename counts the same demand twice. Taking the year whole means every figure
for a year comes from one published document, and the demand numbering
within it means one thing.

## The PDF era

`alldg.xlsx` exists for four editions. Every edition from 2003-04 publishes
the same statements as PDF — `alldg.pdf` as one bundle from 2011-12, and
`dg<N>.pdf` one file per demand from 2003-04 — and reading those closes the
2020-21 and 2021-22 hole and takes the series back to **2002-03**,
twenty-five fiscal years. `scripts/parse_union_pdf.py` does it with
`pdfplumber`.

The statement is the same statement, so the layout rules it needs are the
ones the workbook parser already had. They were moved into
`scripts/union_statement.py`, which both parsers now call, because the one
thing worse than a layout trap is two copies of the fix for it.

### What a PDF makes harder than a spreadsheet

**A PDF has no columns, only x coordinates.** A row prints only the figures
it has. Demand 25 of 2021-22 shows a single `-0.06` against
Secretariat-Social Services, and that is the 2019-20 actuals column, not the
first column of anything; reading the words in order files it under actuals
by luck and under something else the next time. Figures are therefore placed
by their right edge, against column edges clustered from every figure in the
file. Two details earn their keep:

- The nil marker `...` is clustered separately, because up to the 2010-11
  editions it is set centred rather than flush right. It still proves a
  column is there, and that matters: demand 61 of 2003-04 is wholly non-Plan
  and prints nothing but `...` in three of its nine columns, so without the
  nils the remaining six fit one column to the left — which would put its
  Non-Plan figures under Plan and leave the Total column, the only one that
  is read, empty.
- Columns are clustered per file *and per layout*. The 2016-17 bundle holds
  three typesettings of the same table, their columns a few points apart;
  clustering the bundle as a whole blurs them into each other.

**There are two header shapes, and the older one has no actuals.** From the
2017-18 edition the table is four columns — t-2 actuals, t-1 BE, t-1 RE, t BE
— exactly as the workbooks. Before that, every year is split Plan / Non-Plan
/ Total and there are only three year groups: t-1 BE, t-1 RE, t BE. The
Demands for Grants of the Plan era never print an actual at all, so 2002-03
to 2014-15 can only ever be budget and revised estimates. Of the nine columns
the Total of each group is read, which is Plan plus Non-Plan.

Because the shape is one of exactly two, it is derived from the number of
column groups and the edition's own year, and then checked against whatever
the header did extract. That is what makes the legacy files readable at all:
demand 62 of 2003-04 prints `2002-2003 Budget Revised 2003-2004 Budget`,
having lost the second year outright, and the whole 2014-15 bundle sets its
years in the legacy font, so its header extracts as the bare words `Budget
Revised Budget`. A header that contradicts the shape is rejected, so a real
change of layout still fails loudly.

**The Devanagari half is not always Devanagari.** Up to the 2018-19 edition
it is set in a legacy font with no usable encoding and extracts as Latin-1
noise. It cannot be stripped by script, so a word is kept only if it is ASCII
once the typographic quotes are folded.

**Words that should not be one word.** The legacy typesetting runs tokens
together, and every case is fatal rather than untidy, because what
disappears is always a landmark or a figure:

| Printed | Is | Found in |
| --- | --- | --- |
| `2009-2010Budget` | year + estimate | demand 2 of 2010-11 |
| `2013.432708.43` | two figures | demand 5 of 2003-04 |
| `...14318.18` | nil + figure | demand 24 of 2010-11 |
| `3452107.50` | major head + figure | demand 91 of 2003-04 |
| `Institutions3466` | head name + major head | demand 33 of 2003-04 |

The first three are split by decomposing the token; the last two only where
the part that would be the code really does end at the Major Head column,
since `123456.78` must not become head 1234 and Rs 56.78. Left alone,
`2013.432708.43` costs more than the Rs 20 lakh crore it looks like: it is
part of a `GRAND TOTAL` row, so the label becomes `GRAND TOTAL
2013.432708.43`, the landmark stops matching, the parser never learns that
the recoveries have started, and the demand reports its recoveries as its
expenditure.

**One printed row, two baselines.** The 2017-18 bundle sets a head's name a
few points above its own figures. The two are rejoined when the lower row is
nothing but figures — allowing for a stray dash left where the Devanagari
was, without which the Defence demands lose their entire recovery block.

### Three more things the documents do

- **A demand of one head prints no total**, because the head is the total.
  Defence Pensions is one: demand 21 of 2010-11 is a single line against
  major head 2071 and stops. Read strictly it adds nothing to the year and
  Rs 25,000 crore goes missing, so the total is added up from the components
  the document does print. Likewise a demand of one section closes with a
  bare `Total` rather than a `GRAND TOTAL`.
- **An appropriation of one head prints no GRAND TOTAL either**, and goes
  straight from its section total to the note introducing the receipts netted
  against it — demand 34 of 2003-04, Interest Payments. The note is therefore
  a landmark in its own right; without it the receipts below are added to the
  expenditure above instead of netted off it, and interest payments come out
  Rs 5,704 crore too small.
- **A Union Territory's demand is nested.** Demand 93 of 2003-04 (Andaman and
  Nicobar Islands) runs to sixteen blocks, one per ministry, each with its own
  revenue and capital section totals, and then totals the sections again for
  the demand as a whole. Its section totals therefore come to exactly twice
  its major heads. That is how the document reads, so the parser records the
  block totals under a `*_block` account and `validate.py` counts those
  demand-years out of the heads-sum-to-section identity rather than failing
  on them.

Four files ship the same demand twice — `dg31.pdf` of 2003-04 is one page
printed two pages long, and the 2013-14 and 2014-15 bundles repeat a page
each. The second copy is ignored, which is worth doing
explicitly: parsing both doubles the demand, and every identity inside it
still holds, so nothing downstream would complain.

### What this costs, and what is left

Reading 2,400 pages takes about ten minutes, so each edition is cached under
`data/processed/union_pdf_cache/`, keyed by a hash of the parser's own
source. Change `parse_union_pdf.py`, `union_statement.py` or `common.py` and
every cache is stale and reparsed, so a cached run cannot disagree with a
fresh one.

`data/reference/union_pdf_coverage.json` records, per edition, how many
demands were read and what was given up. The residue is small and all of it
is in the per-demand-PDF editions of 2003-04 to 2010-11:

- `dg58.pdf` of 2008-09 is encrypted with a filter pdfminer does not know.
- `dg104.pdf` of 2003-04 is not a demand at all but a statement of New
  Service.
- Four demands across four editions (94 of 2003-04, 12 of 2005-06, 17 of
  2006-07 and 17 of 2007-08) print no total this parser can find, so those
  four years are short by one demand each.

Everything else reads: 2,474 demands over twenty-four editions, and every
one of the identities in `validate.py` holds across all 6,073 demand-years.

An edition whose layout defeats the parser altogether should be marked
`"unparsed": true` in `data/reference/union_editions.json`, which
`pdf_editions()` honours; none currently needs it. A year short of a demand
looks perfectly reasonable on a chart, which is why the count is written down
rather than left in a console log.

## Next

*Update, 18 October 2026: items 1 and 2 and the GDP half of item 3 are done.
See "Closing the data gaps" below. The deflator and UDISE+ enrolment remain.*

1. **Statements of Budget Estimates** (`sbe<N>`) for scheme-level detail —
   Samagra Shiksha, PM POSHAN and so on, with the lineage table the brief
   asks for.
2. **Actuals before 2015-16.** The Demands for Grants of the Plan era print
   only estimates, so the Union series has budget and revised estimates from
   2002-03 but actuals only from 2015-16. Actuals for the earlier years are
   published, but in the Finance Accounts and in the Expenditure Budget's
   own summary statements, not in the demands.
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

*Update, 18 October 2026: the ABE has since been found in the Wayback
Machine's CDX index, and its state × sub-sector statements are now in
`data/abe.json` for 2007-08 to 2021-22. They are revenue expenditure of the
education departments, which is the ABE's definition, not e-STATES'. See
"Gap 5" below.*

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

*Update, 18 October 2026: the ABE's own Centre-plus-states series, 2000-01 to
2021-22, is now in `data/abe.json` (`national`). `data/states.json` still
carries no combined key, and the test still asserts it does not: the only
legitimate total is the ABE's, never a sum of the Union and state files.*

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

---

# Closing the data gaps

Notes from 18 October 2026. Five gaps were open (see the list in
`docs/COPY-HANDOFF.md`). All five now have pipelines. What each found is
below, and the shape of every new file is at the end of this document.

Two claims made before this work turned out to be wrong. Both are worth
knowing before anyone goes looking again:

- **Union actuals before 2015-16 are not absent from the budget documents.**
  The Plan-era Demands for Grants print none, and neither does the 2010-11
  Statement of Budget Estimates. But Expenditure Budget Vol. I, Statement 2,
  prints actuals for the year before last in every edition from 1998-99, and
  the SBEs print an Actual column from the 2011-12 edition.
- **The ABE can be obtained.** Every ministry URL returns 404, and the Wayback
  *availability* endpoint reports no snapshot. The Wayback **CDX** API is a
  different index, and it lists twelve editions.

## Gap 1: national GDP — `scripts/national_gdp.py`

RBI's Handbook of Statistics on the Indian Economy, Table 1, read from ten
editions (2017 to 2026). One edition is not enough, for two reasons:

- From 2018 each edition prints only the latest seven years. 2011-12 is last
  printed by the 2018 edition, 2012-13 by 2019, and so on.
- Older editions are not linked from the index. The year tree is an ASP.NET
  postback (`onclick=GetYear("2017")` sets `hdnYear` and clicks a hidden
  button), so the form is posted back exactly as the page's own script
  would. Reading links out of the HTML, as `discover_states.py` does, only
  ever sees the current year.

**Bases are kept apart, never chained.** India's national accounts were
rebased to 2011-12 (January 2015) and to 2022-23 (February 2026). A rebasing
moves the level. GDP for 2011-12 is Rs 90.10 lakh crore on the 2004-05 base
and Rs 87.36 lakh crore on the 2011-12 base; 2022-23 is Rs 268.90 lakh crore
on 2011-12 and Rs 261.18 lakh crore on 2022-23. The output has one series per
base, with both values in each overlap year. A `preferred` series takes the
newest base for each year and records the two breaks. Within a base, each
year comes from the newest edition that prints it.

Three things about the editions:

- The 2020 to 2022 editions print no base year anywhere. They sit inside the
  2011-12 era and agree to the crore with the editions that do state it,
  which the script checks rather than assumes.
- The unit changes from billion (the 2017 and 2018 editions) to crore (2019
  on).
- The ABE (gap 5) prints the GDP it divides by, and for 2011-12 to 2019-20 it
  is exactly this series. For 2000-01 to 2010-11 the ABE's GDP matches
  neither the 2004-05-base market-price figures here nor the factor-cost
  ones; it is an older vintage. The ABE's own percentages for those years
  therefore cannot be recomputed from `data/gdp.json`, and should be quoted
  as the ABE's.

There is no GDP outturn for the year a budget is made for, so the Union's
2026-27 budget estimate has no denominator in this file. That is by design.

## Gap 2: scheme detail — `scripts/sbe.py`, `scripts/parse_schemes.py`

The Statements of Budget Estimates of the two education departments, every
edition from 1998-99: 57 statements, 54 of which pass every check.

**The SBEs are mostly Excel, not PDF.** `union_editions.json` records
`sbe_excel` only for `.xlsx`, because `discover_union.py` never tried `.xls`.
The site serves `.xls` (BIFF) for 2011-12 to 2013-14, 2015-16, 2016-17 and
2021-22 to 2023-24. PDF is needed only for 1998-99 to 2010-11 and for
2014-15. `sbe.py` tries `.xlsx`, `.xls` and `.pdf` in that order and checks
each by magic number.

**Which statement is education** is decided from the statement itself: by
its title where it prints one. Where it prints none (the 2019-20 and 2020-21
workbooks have no title at all), its net total for the budget year must equal
that demand's net total in the Demands for Grants, to the paisa.

**The model.** Every printed line with figures is either a *leaf* (a line
under a major head, or an item with no children) or a printed total. An
item's value is always the sum of its own leaves; printed totals are used
only as checks. Four checks gate the write:

- the leaves sum to the Grand Total and to the top block in every statement;
- each statement's total equals the Demands for Grants for that demand and
  year (158 checks);
- every printed scheme total equals its lines (1,995 checks);
- every lineage pattern matches at least one line.

**Lineage** lives in `data/reference/scheme_lineage.json`, curated from every
label printed. A scheme's figure is every line the statement prints for it:
gross budgetary support, the lines financed from the Prarambhik Shiksha Kosh
or other funds, and the North East provision. It excludes the transfers into
a fund and the "amount met from" lines that cancel them. Sarva Shiksha
Abhiyan in 2010-11 is three lines (4,994.10 + 8,608.00 + 1,397.90) and comes
to Rs 15,000 crore, the published allocation.

Traps, each caught by the leaf identity:

- **Wrapped names, by position.** In a PDF a name continues at its item's
  text indent, while a section heading starts at the number column. 2014-15
  prints a name's tail on its own line *after* the figures.
- **Unnumbered items.** "Amount met from Prarambhik Shiksha Kosh" carries no
  number in 2007-08 to 2010-11. Folded into the item above, it nets the
  whole Kosh off Sarva Shiksha Abhiyan.
- **Unlabelled rows in workbooks.** Under "Transfer to PSK" in 2023-24, a row
  with an empty label cell is the "Amount met from" line; under National Bal
  Bhawan in 2026-27 it is a block of recoveries. Credited to the item above,
  it made National Bal Bhawan's 2024-25 actual −525.42 instead of 24.33.
- **Item numbers look like amounts.** "34.10" matches the money pattern, and
  a long North East block forms a spurious column at the left margin.
- **"B.E. 2016-2017" is not Part B.** The 2016-17 statements print a
  restructured scheme list for the budget year and the old list for the
  earlier years, in one table.
- **`70..`** (two full stops) is an item number.
- **An `.xlsx` can lie about its size.** Some 2019-20 and 2020-21 workbooks
  declare a one-cell dimension; openpyxl in read-only mode trusts it and
  reads nothing.

Rejected statements, with reasons in `data/reference/sbe_coverage.json`:

- Demand 48 of 1998-99: items 18 to 30 are missing from the PDF itself
  (page 2 holds 592 characters).
- Demand 56 of 2003-04: the names are set one baseline away from their
  figures throughout.

Demand 47 of 1999-00 prints a Grand Total Rs 2.00 crore below its own top
block and lines. The lines are kept, and the misprint is recorded in
`parse_schemes.MISPRINTS`.

Actuals: the SBEs carry them from the 2011-12 edition, so scheme actuals
start in 2009-10.

## Gap 3: Union actuals before 2015-16 — `scripts/parse_union_actuals.py`

Source: Expenditure Budget Vol. I, Statement 2, "Total Expenditure of
Ministries / Departments", in every edition from 1998-99 to 2016-17, with
Statement 1 as a check. It gives actuals by department for **1997-98 to
2014-15**. With the demands' own actuals from 2015-16, the Union series now
has actuals for every year from 1997-98. The detail is the department, not
the major head.

Checks:

- revenue + capital = total on every department and on the Grand Total
  (4,602 lines);
- the departments sum to the central-sector total;
- central sector + State Plans + UTs = Grand Total;
- the State Plan items sum to the State Plans total;
- the Grand Total equals Statement 1's Total Expenditure wherever Statement 1
  prints that column (49 checks);
- four Budget at a Glance totals, as fixtures in `validate.py`.

The School Education actual for 2009-10 (24,466.07) and Higher Education's
for 2013-14 (24,465.17) agree to the paisa with the SBE actuals of gap 2.

Traps:

- **The Department of Revenue is printed as "Revenue"**, exactly like every
  department's revenue sub-row. Read as a sub-row, it overwrote the
  Department of Expenditure's revenue and dropped itself from the central
  sector.
- **2016-17 restates central assistance by ministry.** Up to 2015-16,
  Section II (central assistance for State Plans) lists a few channels:
  Finance, Agriculture, Panchayati Raj. The 2016-17 edition lists it
  ministry by ministry. Its 2014-15 actuals therefore show School Education
  at Rs 5,840 crore in the central sector and Rs 39,695 crore under
  Section II. Each department carries `central_sector`, `state_plans` and
  their sum.
- **Budget at a Glance pages that belong to another edition.** The archived
  `ub2005-06/bag/bag1.htm` has 2005-06's column headings over 2003-04's
  figures, and the budget estimate in `ub2004-05/bag/bag1.htm` is the interim
  budget's. Fixtures come only from pages whose BE column equals Statement 1
  of the same edition.
- **Misprints are recorded, not fixed.** In the 2000-01 Statement 2, the
  departments' 1998-99 actuals add up to Rs 53.62 crore more than the printed
  central-sector total, and Budget at a Glance confirms the printed total.
  One department line is wrong and the document does not say which
  (`KNOWN_GAPS`). The UTs' revised capital in 2011-12 to 2014-15 is printed
  as 4,454.32 over parts of 72.00 and 722.53, which is why aggregates are
  checked by their parts.
- **One edition is excluded.** The 1998-99 Statement 2 is truncated at
  source (pages 1, 4 and 6 hold about 230 characters each), so 1996-97 has no
  department detail. The script confirms on every run that the exclusion is
  still needed.

The actuals here are "as known at budget time", and most editions call them
provisional. The audited figures are in the CGA's Finance Accounts. They were
not needed, because this route is machine-readable and validates.

## Gap 4: state GSDP back-series — `scripts/state_gsdp_series.py`

The 2018 Handbook of Statistics on Indian States, Table 15, prints every
older base side by side: 1980-81 (1990-91 to 1992-93), 1993-94 (to 1999-00),
1999-00 (to 2004-05) and 2004-05 (to 2014-15). The 2011-12 base still comes
from the current Handbook. Three kinds of break are kept, not chained:

- **base years.** Each base is its own segment and the overlaps are kept. The
  median rebasing step was +6.7% at 1999-00, +8.2% at 2004-05 and +9.5% at
  2011-12.
- **the measure.** The old bases are GSDP *at factor cost*; the 2011-12 base
  is at market prices.
- **boundaries.** Back-casts put a parent state on its post-split boundary:
  the 2004-05 base prints residual Andhra Pradesh and a separate Telangana
  for 2004-05, while the parent's budget that year is the undivided state's.
  `budget_boundary` gives GSDP on the budget's territory: parent plus
  successor wherever the successor is printed for a year before it had a
  budget. 38 state-years are adjusted.

**This exposes an error in `data/states.json`**, which is not changed here.
It divides undivided Andhra Pradesh's budgets for 2011-12 to 2013-14 by
residual-AP GSDP, because the Handbook back-casts Telangana to 2011-12.
`gsdp.json`'s `budget_boundary` is the right denominator.

The overlap check runs on boundary-consistent values and rejects only a
ratio outside 0.6 to 1.6, which would mean a unit slip or a misaligned
column. Real rebasing effects are large for some states (Karnataka rose about
30% on the 2011-12 base); they are data, not errors.

## Gap 5: the ABE — `scripts/fetch_abe.py`, `scripts/parse_abe.py`

**What did not work, and should not be retried:** every education.gov.in
and mhrd.gov.in URL, under both the `statistics` and `statistics-new`
upload directories; the Wayback *availability* endpoint for those URLs; and
the Dataful mirror, which is gated. data.gov.in and the Parliament library
(eparlib.nic.in) were not needed once the archive route worked.

**What worked:** the Wayback CDX index, queried with a prefix over the two
upload directories on both domains. It lists 15 captures with HTTP 200 and
application/pdf: 12 distinct editions, from 2007-08–2009-10 to
2019-20–2021-22. They are fetched from the raw-capture form
(`/web/<timestamp>id_/<url>`), checked for `%PDF`, and recorded in the
manifest with the archive URL. The newest edition is `budget_exp_2020_22.pdf`,
the file the original brief cited.

**The file names do not say which edition is which.**
`budget_exp_2020_22.pdf` is the 2019-22 edition, `..._2017-2019.pdf` is
2016-19, `..._2018-2020.pdf` is 2017-20, and `budget_exp.pdf` (2018-21) and
`budget_expenditure.pdf` (2016-19) carry no year at all. Each edition's span
is read from its own cover page. One capture, `Budget Exp 2017-18
-27-6-2020.pdf` (84 MB), is a scan with no text layer and is not read. It is
probably the 2015-18 edition, which is why there are no 2015-16 actuals.

**Two things are read:**

- **Table 4** of the newest edition: public expenditure on education as a
  share of GDP, 2000-01 to 2021-22, for Centre, states and total, both by
  the education departments alone and by education and other departments,
  with the GDP the ABE used. This is the legitimate Centre-plus-states total.
  On the broad definition it is 4.04% of GDP in 2019-20 (actual), 4.36% in
  2020-21 (RE) and 4.12% in 2021-22 (BE); on education departments alone,
  2.73%, 2.95% and 2.75%.
- **The sector statements**, state by state: revenue expenditure of the
  education departments on elementary, secondary, adult, university,
  technical, general and language education, for each edition's actual,
  revised and budget years. With the newest edition winning each
  (year, estimate type), the series runs from 2007-08 to 2021-22.

Checks: in every sector statement the state rows add up to TOTAL STATES, the
UT rows to TOTAL U.T., and the two to TOTAL (STATE & UTs); in the old layout
Plan + Non-Plan = Total in every cell; in Table 4 States + Centre = total and
every % of GDP equals the total over the printed GDP; and Table 4's 2010-11
figure equals Table 6 of the 2010-13 edition. Fixtures in `validate.py` add
Statement 14, a third table, which prints the all-states sector totals.

Layouts and traps. There are five typesettings in twelve editions, and every
one was caught by the identities:

- **Plan/Non-Plan with three years a page** (to 2013-16), **one year a
  page** (2014-17), and **value/% with three years a page** (from 2016-19).
  Columns are found by clustering every figure's right edge on the page.
- **A space glyph drawn over the first digit** of most numbers in the modern
  editions, so text extraction gives `9 ,57,27,800`. Space glyphs are
  dropped before words are formed.
- **Digits with no Unicode map** in 2016-19: they extract as `(cid:882)` to
  `(cid:891)` and `(cid:484)`. They are decoded as 0 to 9 and the decimal
  point; the totals, set in an ordinary font, confirm the mapping.
- **Figures about 18 points below their own names** in 2016-19 and 2017-20,
  more than a row lower, while the total rows' figures sit on their own
  baselines. Grouped as printed, every state's figures land on the next
  state's name. The page shows when this has happened, because the first
  state's row has no figures, and the offset is measured from there.
- **States and UTs move between blocks.** Jammu and Kashmir is a state to
  2018-19 and a UT from 2019-20, and the 2018-21 edition prints it twice.
  Delhi and Puducherry sit with the UTs. Membership is taken from where a row
  is printed, not from a list.
- **Misspellings**: GUJRAT, MEHGLAYA, PUDUCHEERY, MAHARAHSTRA, "A. & N.
  ISLAND".
- **Two copies of one edition** (2011-14, 2016-19) are both read, and the one
  with fewer problems is kept. The first 2016-19 copy fails on its language
  page; the second, `budget_expenditure.pdf`, passes throughout.
- **Excluded:** four 2017-20 pages (secondary, adult, university, language)
  whose text layer superimposes two tables on the same baselines, listed in
  `parse_abe.DEFECTIVE`. Those sectors therefore have no 2017-18 actual,
  2018-19 RE or 2019-20 BE. The script confirms every run that each listed
  page still fails.

**A unit bug, found by the fixtures.** `common.TO_CRORE["thousand"]` was
`1e-5`; Rs 1,000 is `1e-4` crore. The ABE is the first source in thousands,
and its figures came out ten times too small against Statement 14. It is
fixed in `common.py`. Nothing else used that unit. Because
`parse_union_pdf.py` keys its cache on `common.py`'s source, the next run of
`parse_union.py` will reparse the PDF editions (about ten minutes), with an
unchanged result.

**What the ABE does not give:** a sub-sector split of capital spending or of
other departments' education spending, by state. The split is for revenue
expenditure of the education departments only, which is what the ABE
publishes.

## Handover: the shape of the new data

Five files, each written by its own script and each refusing to write if a
check fails. None is read by the page yet; `index.html`, `css/` and `js/`
were being rewritten in parallel and were not touched.

```
scripts/national_gdp.py         -> data/gdp.json             (+ data/reference/gdp_editions.json)
scripts/sbe.py fetch-education  -> data/raw/union/<fy>/sbe/  (+ data/reference/union_sbe.json)
scripts/parse_schemes.py        -> data/schemes.json         (+ data/processed/union_schemes.csv,
                                                                 data/reference/sbe_coverage.json)
scripts/parse_union_actuals.py  -> data/union_actuals.json   (+ data/processed/union_stat2.csv)
scripts/state_gsdp_series.py    -> data/gsdp.json            (+ data/reference/gsdp_editions.json)
scripts/fetch_abe.py            -> data/raw/abe/             (+ data/reference/abe_editions.json)
scripts/parse_abe.py            -> data/abe.json             (+ data/processed/abe_states.csv)
scripts/validate_gaps.py        called by scripts/validate.py
```

New dependency: `xlrd` (for the `.xls` statements), alongside `openpyxl` and
`pdfplumber`.

### `data/gdp.json`

```
meta       measure, prices, unit ('Rs crore'), source, bases[], breaks[]
           ('2011-12', '2022-23'), rule (never chain), within_base, notes[]
segments[] base, first, last, n_years, editions[], source_urls{}
series     { <base>: { <fy>: Rs crore } }         one series per base, as printed
status     { <base>: { <fy>: 'first revised estimate' ... } }  where stated
vintage    { <base>: { <fy>: Handbook edition year } }
preferred  { <fy>: { base, value } }               newest base for each year
```

To express a budget figure as a share of GDP, divide by
`series[base][fy]` on one base and show a break where the base changes;
`preferred` is the convenience form. The Union's budget years run to 2026-27
and GDP to 2025-26, so a BE for the coming year has no denominator.

### `data/schemes.json`

```
meta       unit, source, estimate_types, actuals_from, value, family_rule, lineage
schemes[]  id, name, department ('school'|'higher'), kind ('family'|'renamed'|'single'),
           note, members[] {id, name, first, last}, years[],
           total     { <fy>: { A|RE|BE: Rs crore } }   sum of members
           by_member { <member id>: { <fy>: { A|RE|BE } } }
           source    { <fy>: { A|RE|BE: 'ExpBudget <edition>' } }
```

Twelve schemes: `samagra_shiksha` (family: SSA, RMSA, Teacher Education,
Samagra Shiksha), `pm_poshan` (Nutritional Support to Primary Education → Mid
Day Meals → PM POSHAN), `dpep`, `operation_blackboard`, `mahila_samakhya`,
`kgbv`, `adult_literacy`, `pm_usha` (RUSA → PM-USHA), `kvs`, `nvs`, `ncert`,
`ugc`. The lineage rules are in `data/reference/scheme_lineage.json`.

`data/processed/union_schemes.csv` is every printed line in the long-table
shape: `account` is `sbe_line` (a line under a major head, with
`major_head`), `sbe_item` (an item's value, the sum of its own lines) or
`sbe_grand_total`; `source_page` is `sbe<N>!<item number>`, and items whose
number starts with `u` were printed without one. **Sum only `sbe_line`
rows**; items contain lines, and parents contain children.

### `data/union_actuals.json`

```
meta       unit, estimate_type 'A', source, years[], level, provisional,
           total_definition, joins
years      { <fy>: {
             edition, source_url, provisional (bool, from the document's footnote),
             total_expenditure, central_sector, state_plans, union_territories,
             statement_1_checked (bool), known_gaps[], state_plans_by_ministry (bool),
             departments[] { name, key, central_sector, state_plans, revenue,
                             capital, total } } }
excluded_editions  { '1998-99': reason }
```

`key` is `common.dept_key`, the key `union.json` uses. `total` is
`central_sector + state_plans`. From the 2016-17 edition (2014-15 actuals)
Section II lists central assistance by ministry, so a department's
`state_plans` is large there and empty before; compare `total` across that
edition, not `central_sector`. Use these years only before 2015-16:
`union.json` has the Demands for Grants' own actuals from there on.

### `data/gsdp.json`

```
meta             unit, rule, budget_boundary, known_issue, boundary_adjusted[], notes[]
segments[]       base, first, last, measure, source, source_url, n_states
breaks[]         from, to, year, median_new_over_old, states
series           { <state>: { <base>: { <fy>: Rs crore } } }   as printed
budget_boundary  { <state>: { <base>: { <fy>: Rs crore } } }   on the budget's territory
```

State codes are `data/reference/states.json`'s. For a share of GSDP, divide
the state's budget figure by `budget_boundary[state][base][fy]` and never
compare across a base or measure without showing the break. There is no
all-India row.

### `data/abe.json`

```
meta       source, unit, national_source, national_note, national_rule,
           states_definition, sectors[], state_rows, editions{}, chosen{}
national   { <fy>: { estimate_type, gdp,
                     education_departments           { states, centre, total,
                                                       pct_gdp { states, centre, total } },
                     education_and_other_departments { ... same ... } } }
states     { <code>: { <sector>: { <fy>: { A|RE|BE: Rs crore } } } }
```

`national` is the ABE's own Table 4, one vintage, 2000-01 to 2021-22: the
only Centre-plus-states figure in the repository, counting each rupee once.
`states` is revenue expenditure of the education departments by sub-sector
(`elementary`, `secondary`, `adult`, `university`, `technical`, `general`,
`language`). It includes UTs with ISO codes and the ABE's own `total_states`,
`total_uts` and `total` rows. For each (year, estimate type) the newest
edition wins, as in every other pipeline here.

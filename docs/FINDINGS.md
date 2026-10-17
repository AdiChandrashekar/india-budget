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
3. **States.** RBI's *State Finances* workbooks, after relocating the source.
   This is the layer that makes the functional classification pay off, since
   major head 2202 means the same thing in every state.
4. **Denominators.** GDP, a deflator and UDISE+ enrolment, to get off nominal
   rupees.

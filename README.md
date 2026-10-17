# India Budget Explorer

### What the Union government budgets for education, and everything else

An interactive tool for the Union budget. It starts from education, because
that is where the definitional problem is sharpest, and carries the whole
budget behind it: all 102 demands for grants, every major head of account.

**The argument.** There is no single education budget. The Ministry of
Education's own demands come to Rs 1.39 lakh crore in 2026-27. The functional
account heads for education, sports, art and culture come to Rs 1.17 lakh
crore. Education alone, without sports and culture, comes to Rs 1.10 lakh
crore. All three are correct, all three are published by the same government
for the same year, and most writing about education spending quotes one of
them without saying which. The tool shows all three at once and labels every
series with the definition behind it.

The second thing it shows is where the money is booked. The ministry's largest
account head is not education but **3601, grants-in-aid to state governments**:
Rs 1.08 lakh crore in 2026-27, against Rs 72,069 crore under 2202, general
education. Those grants are spent and re-booked as education by the states,
which is why Union and state education budgets must never be added together.

---

## Running it

There is no build step, no bundler, no framework. HTML, CSS and ES modules,
with d3 v7 from a CDN.

```bash
python -m http.server 8124
```

Then open http://localhost:8124. `fetch()` does not work over `file://`, so it
needs a server, any server.

## Regenerating the data

Four scripts, in order. Each validates its own output and refuses to write if
an invariant fails.

```bash
python scripts/discover_union.py   # map every edition's real URLs
python scripts/fetch_union.py      # download the workbooks
python scripts/parse_union.py      # -> data/processed/union_demands.csv
python scripts/build_site.py       # -> data/union.json, what the page reads
python scripts/validate.py         # published fixtures + internal identities
```

`discover_union.py` is the slow one, a few minutes, because it verifies every
candidate URL by fetching the first kilobyte and checking the file's magic
number. It is worth it: see [docs/FINDINGS.md](docs/FINDINGS.md) for why
guessing paths and trusting HEAD requests both fail on this site.

Raw downloads land in `data/raw/`, which is gitignored, alongside a
`manifest.csv` recording the URL, fetch time, byte count and sha256 of every
file. The data is reproducible rather than committed.

## Tests

```bash
node test/run.mjs      # 38 assertions, no framework, no dependencies
```

Node 18 or newer. The tests cover the helpers in `js/data.js` and the shape
and arithmetic of the published `data/union.json`, so a broken pipeline cannot
ship a page that renders but lies.

## Validation

`scripts/validate.py` is the gate. It checks figures the government published,
not merely figures we parsed consistently:

| Check | Expected | Source |
| --- | --- | --- |
| Total Union expenditure, 2026-27 BE | Rs 53,47,315 cr | Budget at a Glance |
| Dept of School Education & Literacy | Rs 83,562.26 cr | Demand No. 25 |
| Dept of Higher Education | Rs 55,727.22 cr | Demand No. 26 |
| Ministry of Education | Rs 1,39,289.48 cr | PRS DfG analysis |

All four reproduce, the Union total to within Rs 0.19 crore of rounding across
102 demands. Two identities are also checked across all 1,420 demand-years
parsed: gross plus recoveries equals net, and major heads sum to their section
total.

## The data model

One long table, `data/processed/union_demands.csv`, one row per published
number, with the edition, URL and sheet it came from:

```csv
fiscal_year,govt,state_code,estimate_type,source_edition,definition,major_head,sub_major_head,ministry_or_dept,scheme,account,occurrence,amount_cr,source_url,source_page
2026-27,union,,BE,ExpBudget 2026-27,moe,,,Department of School Education and Literacy,,net_total,1,83562.26,https://...,2026-27!dg25
```

- `estimate_type` — `A` actuals, `RE` revised, `BE` budget estimate.
- `definition` — `whole` for a demand total, `functional` for a major-head line.
- `account` — `basis_section`: `gross_revenue`, `recovery_capital`,
  `net_total` and so on. Gross plus recoveries equals net.
- `occurrence` — 2 and up where one statement lists the same head twice and
  means two different numbers. Demand 40 does exactly this.

Everything is Rs crore, nominal, normalised at ingestion.

## What it covers

**Union, 2017-18 to 2026-27**, from four editions of the Expenditure Budget.
Each edition publishes four years at once — actuals for two years back, a
revised and a budget estimate for last year, and a budget estimate for the
year ahead — so a handful of editions covers a decade.

**2020-21 and 2021-22 are missing.** Not because the data does not exist: the
editions covering those years ship PDF only, with no Excel. Closing that gap
means parsing PDF tables, which is the next piece of work and is scoped in
[docs/FINDINGS.md](docs/FINDINGS.md).

## What it does not cover yet

- **States.** The whole second half of the question. Needs RBI's *State
  Finances: A Study of Budgets*, not this pipeline. Note that the handoff's
  RBI Statement 26 URL now redirects to the RBI home page, so the source has
  to be relocated before that work starts.
- **Real terms and % of GDP.** No deflator and no GDP series are loaded, so
  every figure here is nominal. Shares of total Union expenditure *are*
  computed and are safe to compare across years.
- **Scheme level.** The demands give major heads, not schemes. Scheme detail
  is in the Statements of Budget Estimates (`sbe*`), which this pipeline
  downloads a map of but does not yet parse.
- **Pre-1996.** Scanned PDFs needing OCR.

## Layout

```
scripts/     the pipeline, plain Python, openpyxl its only dependency
data/raw/    downloads + manifest.csv (gitignored)
data/processed/  the long table
data/reference/  the edition map, ministry mapping
data/union.json  what the page reads
js/ css/     the site: data.js, charts.js, app.js
docs/        FINDINGS.md, what the sources actually look like
```

## Sources

Everything comes from [indiabudget.gov.in](https://www.indiabudget.gov.in/).
Per-figure provenance is in the long table; the edition map with verified URLs
for every year from 1998-99 is in `data/reference/union_editions.json`. See
[SOURCES.md](SOURCES.md).

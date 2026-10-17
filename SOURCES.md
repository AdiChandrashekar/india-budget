# Sources

Every figure in this repository comes from the Union government's own budget
documents. Nothing is modelled, estimated or interpolated.

## In use

| Source | What it gives | Where it lands |
| --- | --- | --- |
| [Expenditure Budget / Demands for Grants](https://www.indiabudget.gov.in/doc/eb/alldg.xlsx), every edition | All 102 demands by major head: actuals, revised and budget estimates | `data/processed/union_demands.csv` |
| [Demands for Grants summary](https://www.indiabudget.gov.in/doc/eb/dgsum.xlsx) | Ministry → department → demand | `data/reference/union_ministries.json` |
| [Previous budgets index](https://www.indiabudget.gov.in/previous_union_budget.php) | Every edition back to 1996-97, plus the pre-1996 archive | `data/reference/union_editions.json` |

The resolved, verified URL for every edition from 1998-99 to 2026-27 is in
`data/reference/union_editions.json`, with the file formats each one serves.
Per-figure provenance — edition, URL, sheet — is on every row of the long
table.

Raw downloads are recorded in `data/raw/<year>/manifest.csv` with URL, fetch
timestamp, byte count and sha256.

## Checked against

| Figure | Value | Source |
| --- | --- | --- |
| Total Union expenditure, 2026-27 BE | Rs 53,47,315 cr | [Budget at a Glance](https://www.indiabudget.gov.in/doc/Budget_at_Glance/budget_at_a_glance.pdf) |
| Ministry of Education, 2026-27 BE | Rs 1,39,289.48 cr | [PRS, Demand for Grants 2026-27: Education](https://prsindia.org/budgets/parliament/demand-for-grants-2026-27-analysis-education) |
| Ministry of Education, 2023-24 BE | Rs 1,12,899 cr | Expenditure Budget 2024-25 |
| MoE spending as % of total Union expenditure | ~2.6% | Matches the figure in the feasibility study |

## States, in use

All six URLs below were resolved from RBI's live indexes and verified on
**17 October 2026** with a ranged GET and a magic-number check. None was taken
from a documented path: the one in the handoff brief now redirects to the RBI
home page.

**RBI's file names are not stable.** Each embeds a publication date and a
content hash (`ESTATES23012026AB13...XLSX`), so every edition changes them.
The URLs are therefore not written down here as the thing to fetch; they are
re-resolved by `scripts/discover_states.py` from the two index pages, which
*are* stable, and cached with their verification date in
`data/reference/state_editions.json`. Re-run that script rather than editing a
URL by hand.

| Source | What it gives | Where it lands |
| --- | --- | --- |
| [*State Finances: A Study of Budgets*](https://rbi.org.in/Scripts/AnnualPublications.aspx?head=State+Finances+%3A+A+Study+of+Budgets) &rarr; **e-STATES Database** (15.2 MB xlsx) | Every appendix line for 31 states and UTs and RBI's all-states aggregate, **1990-91 to 2025-26**, with accounts, revised and budget estimates | `data/processed/state_education.csv` |
| Same volume &rarr; **Statement 26**, education as a share of aggregate expenditure | 570 published percentages, 2008-09 to 2025-26 | `data/processed/state_statement26.csv`, used as fixtures |
| Same volume &rarr; **Appendix Table 7**, composition of social sector expenditure | All-states education and social services in rupees | Validation fixtures |
| Same volume &rarr; **Statement 31**, social sector expenditure | State-wise social sector totals | Cross-check |
| [*Handbook of Statistics on Indian States*](https://rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+States) &rarr; **Table 21**, GSDP at current prices | GSDP, 2011-12 to 2024-25, for ratios | `data/reference/state_gsdp.json` |
| Same volume &rarr; **Table 175**, state-wise social sector expenditure | A second social sector series | Cross-check |

The e-STATES database is in Rs crore; the Handbook's GSDP is in Rs lakh and is
normalised at ingestion. Raw downloads and their sha256 are in
`data/raw/states/manifest.csv`.

Note that **the documents live on a different host from the indexes**, behind
a bot defence that answers an unprepared request with HTTP 200, a Content-Type
of `text/html` and a page of JavaScript. See `docs/FINDINGS.md`.

## Checked against, for the states

| Figure | Value | Source |
| --- | --- | --- |
| All states, education as % of aggregate expenditure, 2010-11 | 16.6% | Statement 26 |
| All states, same, 2025-26 BE | 13.1% | Statement 26 |
| Bihar, same, 2025-26 BE | 20.0% | Statement 26 |
| Telangana, same, 2025-26 BE | 7.8% | Statement 26 |
| All states, revenue expenditure on education, 2020-21 | Rs 5,12,428.9 cr | Appendix Table 7 |
| All states, revenue expenditure on education, 2010-11 | Rs 1,87,617.3 cr | Appendix Table 7 |
| All states, revenue expenditure on social services, 2022-23 | Rs 14,84,370.9 cr | Appendix Table 7 |

**All 570 percentages** published in Statement 26 reproduce from the parsed
series, across 31 states and the aggregate and 18 years, to within RBI's own
rounding. That is what pins the definition: the numerator is revenue
expenditure plus capital outlay, and the denominator is total revenue
expenditure plus total capital disbursements *excluding the public account*.

## Not yet used

| Source | Status |
| --- | --- |
| MoE, *Analysis of Budgeted Expenditure on Education* | The brief's PDF URL **404s** and no replacement was found on education.gov.in. The only source that splits state education spending by sub-sector, and the only one that gives a legitimate centre-plus-state total. Still missing; see `docs/FINDINGS.md`. |
| RBI Handbook, Table 175 and Statement 31 | Downloaded and verified, parsed only as cross-checks so far. |
| [CAG Finance Accounts](https://cag.gov.in/en/state-accounts-report?arch=1) | Audited state actuals. For validation, not as a primary pipe. |
| [CAG Combined Finance and Revenue Accounts](https://cag.gov.in/en/combined-accounts) | The official Union + states consolidation. The **only** correct way to get a centre-plus-state total. |
| [CGA, List of Major and Minor Heads](https://cga.gov.in/Book/CorrectionSlip/Published/List-of-Major-and-Minor-Heads-of-Account-of-Union-and-States-LMMH.aspx) | The account-head reference the functional classification rests on. |
| [Open Budgets India on CKAN](https://ndp.ckan.civicdatalab.in/organization/about/open-budgets-india) | CBGA's Union series, last updated February 2022. Cross-check only. |
| Union budget archive, 1947-1995 | Scanned PDFs, OCR needed. |

## Licence of the underlying data

Union budget documents are published by the Ministry of Finance, Government of
India. Check the site's terms before redistributing the raw documents; this
repository redistributes derived figures with provenance, not the source files.

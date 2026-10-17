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

## Not yet used

Queued for the state layer and the historical extension. **Two URLs from the
original brief are dead** and need relocating before that work starts.

| Source | Status |
| --- | --- |
| RBI, *State Finances: A Study of Budgets*, Statement 26 | The brief's URL now **redirects to the RBI home page**. Relocate from the [publications index](https://rbi.org.in/Scripts/AnnualPublications.aspx?head=State+Finances+%3A+A+Study+of+Budgets). |
| MoE, *Analysis of Budgeted Expenditure on Education* | The brief's PDF URL **404s**. The only source that splits state education spending by sub-sector. |
| RBI, [Handbook of Statistics on Indian States](https://rbi.org.in/Scripts/PublicationsView.aspx?id=12309) | Social sector expenditure from 1990-91, and GSDP for ratios. |
| [CAG Finance Accounts](https://cag.gov.in/en/state-accounts-report?arch=1) | Audited state actuals. For validation, not as a primary pipe. |
| [CAG Combined Finance and Revenue Accounts](https://cag.gov.in/en/combined-accounts) | The official Union + states consolidation. The **only** correct way to get a centre-plus-state total. |
| [CGA, List of Major and Minor Heads](https://cga.gov.in/Book/CorrectionSlip/Published/List-of-Major-and-Minor-Heads-of-Account-of-Union-and-States-LMMH.aspx) | The account-head reference the functional classification rests on. |
| [Open Budgets India on CKAN](https://ndp.ckan.civicdatalab.in/organization/about/open-budgets-india) | CBGA's Union series, last updated February 2022. Cross-check only. |
| Union budget archive, 1947-1995 | Scanned PDFs, OCR needed. |

## Licence of the underlying data

Union budget documents are published by the Ministry of Finance, Government of
India. Check the site's terms before redistributing the raw documents; this
repository redistributes derived figures with provenance, not the source files.

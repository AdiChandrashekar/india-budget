# Design lock

Resolved 17 October 2026. Design-languages catalogue v1.0; charts follow the
dataviz method, palette validated with its `validate_palette.js`.

Anything added later — the state layer especially — follows this file. Don't
re-decide what it settles.

## Direction

**Editorial-statistical: FT chart style crossed with NYT Upshot.** A warm paper
ground, serif headlines that state the finding rather than name the variable,
charts annotated in place instead of explained in a caption, and axes stripped
to a hairline. The page should read as a statistical publication making an
argument, not as a dashboard reporting metrics.

Three rules carry most of the look:

1. **Titles are takeaways.** "Most of the education ministry's money is not
   booked as education", never "MoE by major head". If a chart's title could sit
   above a different chart, it is not doing its job.
2. **Annotate in the chart.** The thing the reader should notice gets a label
   and a leader line on the plot itself. Captions carry units and caveats only.
3. **Charts sit on the paper.** No cards, no panel borders, no boxes around
   plots. The data is the only ink that gets to be strong.

## Tokens

All defined in `css/style.css` on `:root`, redefined for dark under both the
`prefers-color-scheme` media query and `[data-theme="dark"]`.

### Surfaces and ink

| Role | Light | Dark |
| --- | --- | --- |
| Page ground | `#faf6f0` | `#14171a` |
| Raised (tables, controls) | `#fffdfa` | `#1a1e22` |
| Primary ink | `#15181c` | `#eceae5` |
| Secondary ink | `#4d545c` | `#aeb4bb` |
| Muted (axis, labels) | `#8a9099` | `#7e868f` |
| Hairline rule | `#e4ddd2` | `#2a3035` |
| Baseline / axis | `#c9c1b4` | `#394046` |

Charts render on the **page ground**, so that is the surface the palette was
validated against — not the raised colour.

### Categorical series (dataviz slots 1-3, fixed order, never cycled)

| Slot | Role in this project | Light | Dark |
| --- | --- | --- | --- |
| 1 blue | Ministry of Education definition; education generally | `#2a78d6` | `#3987e5` |
| 2 orange | Functional definition; grants-in-aid | `#eb6834` | `#d95926` |
| 3 aqua | Functional, narrow | `#1baf7a` | `#199e70` |

Validated all-pairs on both grounds: worst CVD ΔE 9.2 light / 9.4 dark, worst
normal-vision ΔE 24.0 / 20.9. On the light ground orange (2.97:1) and aqua
(2.61:1) fall below 3:1, so the **relief rule** applies and is satisfied: every
chart ships direct labels and a table view. Do not add a fourth series hue —
fold the tail into "other" or facet.

### Sequential (one hue, blue) — for the dumbbell

Budget estimate is the recessive step, actuals the strong one.

| | Light | Dark |
| --- | --- | --- |
| Estimate | `#86b6ef` | `#184f95` |
| Outturn | `#2a78d6` | `#3987e5` |

Ordinal floors respected: no lighter than step 250 on light, no darker than
step 600 on dark.

### Emphasis grey (the de-emphasis channel)

`#d9d2c6` light, `#2b3137` dark. Used for "everything that is not the subject"
— the 99 non-education demands in the treemap, non-education account heads.
Emphasis, not a series: it never carries identity.

## Type

| Role | Face | Notes |
| --- | --- | --- |
| Headlines, section titles | Serif (`Iowan Old Style`, `Palatino`, Georgia) | The editorial voice. Headlines only. |
| Body, UI, labels | System sans | |
| Metadata, axis ticks, codes, table numbers | Mono | `tabular-nums` |
| Hero figures, stat values | **Sans, proportional figures** | Never the serif, never `tabular-nums` — a display-size serif number reads as decoration and tabular figures look loose. |

That last row is the one exception to "serif carries the editorial voice", and
it is deliberate: it comes from the dataviz method, which the charts follow.

## Marks

Fixed, from the dataviz method:

- Lines 2px, round cap and join. Markers r≥4 with a 2px ring in the ground
  colour.
- Bars capped at 24px thick; 4px rounded data-end, square at the baseline.
- **2px gap in the ground colour** between touching fills — stacked segments
  and adjacent bars alike. Never a stroke around a mark.
- Area washes at ~10% opacity.
- Gridlines and axes: solid hairlines one step off the ground. Never dashed —
  dashing means "estimate" here and must not be spent on chrome.
- **Dashed stroke means forecast.** A line is solid where it plots audited
  actuals and dashed where it plots an estimate, and the point marker is
  filled for an outturn, hollow for an estimate. This is the page's one
  consistent visual idiom; do not reuse dashing for anything else.
- **A gap in the data is a gap in the line.** Never interpolate across the
  years the pipeline could not parse.

## Interaction

- Line charts: crosshair snapping to the nearest year, one tooltip listing
  every series at that year.
- Bars, cells, treemap tiles: the mark is the hit target, minimum ~24px,
  hovered mark lifts.
- Every figure has a **table view** toggle. Tooltips enhance and never gate;
  the table is the WCAG-clean twin and the relief for the sub-3:1 hues.
- Controls sit in one row above the content they scope.
- Series names reach the DOM via `textContent`, never `innerHTML` — they come
  from government spreadsheets.

## Checked against

`references/anti-patterns.md`: no dual axes, no recolor-on-filter, no cycled
hues, no value-ramp on nominal categories, no rainbow, no number on every
point, no borders around marks, no dashed gridlines, no serif hero figure, no
tooltip-gated values.

## Narrative rule

The page makes an argument, so two kinds of statement sit on it and they are
never blurred:

- **Computed** from the budget documents. Every rupee figure, share and ratio
  on the page is read from `data/union.json` or `data/states.json` and
  recomputed on render. None is typed into the markup.
- **Cited** from outside. The 6%-of-GDP target, the published GDP ratios, the
  devolution change and the scheme shares are not in this data. Each is
  attributed in the "Claims from outside the data" block in the footer, and
  the chart that uses them says in its caption that they are cited, not
  computed.

A caption states the unit, the definition and the caveat. It never repeats
what the title already says, and it never asserts a cause the data cannot
carry: where two things merely coincide in time, the page says so.

## Forms added for the state layer

| Figure | Form | Why |
| --- | --- | --- |
| 6% target against published measures | benchmark dot plot, one hue, target as a rule in ink | The measures differ by method, not identity, so they are not a categorical set. |
| States against Union over time | two-series line | The gap is the subject. Both read on the same estimate basis each year. |
| Education's share of state budgets | single line, annotated | One series needs no legend box, but gets one here because the dashed-estimate key still has to be explained. |
| Every state ranked | ranked bars, one hue, aggregate as a reference rule | Colouring bars by value would double-encode length. |
| The same figure as geography | choropleth, sequential blue ramp, quantized | Magnitude, not identity, so one hue light to dark. Entities with no budget of their own are left unfilled, never shaded as zero. |

## Motion

A figure draws itself in the first time it is scrolled to, and never again: a
control change redraws instantly rather than replaying. Lines draw along their
own length, bars grow from the baseline, the map settles in.

Two rules keep it honest:

- **A dashed line fades in rather than drawing.** Drawing it would have to
  overwrite its dash array, and the dash array is the estimate idiom.
- **`prefers-reduced-motion` renders the finished state immediately** rather
  than withholding it. The chart is the point; the animation is decoration,
  and decoration is what gets dropped.

Boundaries are decoded from TopoJSON to GeoJSON at build time
(`scripts/build_map.py`), so the page takes no extra script-tag dependency.
They come from the sibling delimitation project and are for reading a
choropleth, not for any question about where a border runs.

## Change log

- 2026-10-17 — Resolved: FT + NYT Upshot editorial-statistical. Replaced the
  first-pass generic dashboard look (bordered chart cards, grouped bars,
  serif stat values).
- 2026-10-17 — Added the state layer and the narrative rule above: the
  benchmark dot plot, the two-tier comparison and the ranked bars. Charts
  made responsive to series length after the Union series went from 8 years
  to 25.

# Design lock

Re-resolved 17 October 2026 at the owner's request for "a real amazing visual
style" and "a motion graphic visual experience". Design-languages catalogue
v1.0; charts follow the dataviz method, every palette validated with its
`validate_palette.js`.

Anything added later follows this file. Don't re-decide what it settles.

## Direction

Three catalogue references, each owning a layer:

| Reference | Layer it owns |
| --- | --- |
| **Data Journalism / Interactive Explainers** (The Pudding, NYT Graphics) — dominant | Structure, tone, motion. Scroll-driven chapters, a sticky graphic with steps passing it, annotation in the chart, reader participation. |
| **Swiss International Style** | Typography and grid. A neo-grotesque, enormous numerals, flush-left ragged-right, asymmetric composition on a 12-column grid, mathematical spacing, no ornament. |
| **Bloomberg Graphics** | Colour mood. Confident saturated colour on a dark ground. |

The page should read as a data-journalism feature with an argument, not as a
dashboard. Four rules carry the look:

1. **One semantic colour system, everywhere.** Coral is the Union. Blue is the
   states. Amber is the 6% promise. Grey is everything else. A reader who
   learns this in chapter one can read every later chart without its legend.
   When grants-in-aid leave the Union for the states they are drawn blue,
   because blue is the government that ends up spending them.
2. **Titles are takeaways.** The heading states the finding, not the variable.
3. **Annotate in the chart.** Captions carry units, definitions and caveats only.
4. **Charts sit on the ground.** No cards, no boxes, no panel borders.

## Tokens

All in `css/style.css`. Light on `:root`; dark under the
`prefers-color-scheme` query (guarded by `:where(:not([data-theme="light"]))`)
and again under `[data-theme="dark"]`. The page follows the system until the
reader uses the theme toggle, then remembers the choice.

### Surfaces and ink

| Role | Light | Dark |
| --- | --- | --- |
| Ground (charts render on this) | `#f6f3ed` | `#0c0f14` |
| Ground, alternate | `#efebe3` | `#11151c` |
| Raised (tooltips) | `#fbf9f5` | `#151a22` |
| Primary ink | `#111418` | `#f1eee8` |
| Secondary ink | `#464c54` | `#b3b9c2` |
| Muted | `#7c838c` | `#7b838e` |
| Rule | `#e1dbd0` | `#1f252e` |
| Rule, strong | `#c8c0b2` | `#2f3741` |

### The semantic colours

| Role | Token | Light | Dark |
| --- | --- | --- | --- |
| The Union | `--union` | `#d8501f` | `#e65d31` |
| The states | `--states` | `#2a6fe0` | `#3d8bff` |
| The 6% promise | `--target` | `#b77d06` | `#f2b02e` |
| Functional definition | `--def-functional` | `#0f8c71` | `#17a588` |
| Functional, narrow | `--def-narrow` | `#6a55d8` | `#8a78f0` |
| Everything else | `--dim` | `#d9d2c6` | `#262c35` |

The two `--def-*` colours appear only in chapter two, where the three
definitions are the subject.

**Validation, on each ground:**

- coral / functional / narrow, all pairs: worst CVD ΔE 11.9 dark / 11.2 light,
  worst normal-vision ΔE 24.7 / 25.6. All inside the lightness band, all
  ≥ 3:1 contrast.
- states / Union, all pairs: worst CVD ΔE 28.7 dark / 28.1 light.
- amber target: ≥ 3:1 on both grounds.

**No contrast warnings in either mode.** The previous palette needed the
relief rule on three hues; this one does not. Direct labels and table views
remain, but now as good practice rather than as a fix.

Two dark candidates (`#f0663a`, `#19b394`) failed the dark lightness cap at
0.676 and 0.686 and were stepped down. Do not brighten the dark accents for
more "glow" — they will leave the band.

### The map ramp (sequential, one hue)

Six steps, validated as ordinal ramps: monotone lightness, adjacent steps
≥ 0.06 apart, low end ≥ 2:1 against the ground so the lowest share still reads
as a value and never as empty.

| | low → high |
| --- | --- |
| Light | `#6aa4ea` `#418bdf` `#2b72cc` `#205ca9` `#174886` `#0e3466` |
| Dark | `#184f95` `#2266c0` `#3d8bff` `#6aa6ff` `#97c1ff` `#c6dcff` |

On the dark ground, brighter means more. A seven-step light ramp failed on the
warm ground (steps 0.047 apart, low end 1.91:1) and was replaced.

## Type

| Role | Face |
| --- | --- |
| Display: hero numeral, headlines, big chart labels | **Inter Tight** 700–800, tight tracking (−0.035 to −0.07em) |
| Body, UI | **Inter** 400–600 |
| Metadata, axis ticks, codes, table numbers | **JetBrains Mono**, `tabular-nums` |

One grotesque family for UI and display, so the dataviz rule that a hero figure
uses the same sans as everything else holds without exception. The serif is
gone. Big standalone figures use proportional numerals; only aligned columns
use tabular. Loaded from Google Fonts with `display=swap` and system
fallbacks.

## Structure

- **Hero.** Full viewport. The amber "6%" at up to 22rem, glowing on the dark
  ground, rising in on load.
- **Scrolly chapters** (`js/scrolly.js`). A sticky graphic in columns 5–12,
  steps in columns 1–4. A step activates when it crosses the middle tenth of
  the viewport. On a phone the graphic pins to the top and the steps scroll
  over it as cards.
- **Standard chapters.** Takeaway headline, lede, figure, table toggle.
- **Progress bar** in amber along the top edge.

## The motion pieces

| Chapter | Graphic | Steps |
| --- | --- | --- |
| 1 — the target | gauge: published measures against the 6% rule | target alone → 2.7% → 4.1% → 4.6% → the 1.9-point spread shaded |
| 3 — who pays | two bars on one scale | Union → states → the Union's length laid end to end along the states' bar |
| 4 — state share | choropleth with play and scrub, 1990-91 to 2025-26 | reader-driven |
| 7 — the scale | treemap of every demand | all grey → interest payments → education |

Rules each one keeps:

- **`step(n)` reaches step n from any other step**, forwards or back. Readers
  scroll both ways and skip.
- **Length, not area, for the 9-to-1.** An area or unit grid would either
  exaggerate the ratio or imply the two tiers can be summed, and they cannot.
- **The ruler numbers every segment, including a partial last one.** The ratio
  is 8.99; numbering only whole lengths would show eight against a caption
  saying nine.
- **The map's colour scale is fixed across all years.** That is what makes the
  animation honest: a colour means the same share in 1990-91 as in 2025-26.
  Its ends are the 2nd and 98th percentiles so a few small entities cannot wash
  out everyone else; values beyond take the end colours and the key says
  "≤" and "≥".
- **States that did not yet exist are grey, not zero.** Playing the map, you
  watch Chhattisgarh, Jharkhand and Uttarakhand appear in 2000 and Telangana in
  2014.

## Marks

- Lines 2.25px, round cap and join. Markers r ≥ 4 with a ring in the ground
  colour.
- Bars capped at 24px thick.
- A 2px gap in the ground colour between touching fills. Never a stroke.
- Gridlines and axes: solid hairlines. **Never dashed.**
- **Dashed stroke means estimate.** Solid where a line plots audited actuals,
  dashed where it plots an estimate; filled marker for an outturn, hollow for
  an estimate. This is the page's one recurring idiom and is spent on nothing
  else — not reference rules, not annotation leaders.
- **A gap in the data is a gap in the line.**

## Motion

- Standard figures draw in the first time they are scrolled to, once. A
  control change redraws instantly.
- **A dashed line fades in rather than drawing**, because drawing would
  overwrite the dash array that means "estimate".
- **`prefers-reduced-motion` renders the finished state immediately**, it does
  not withhold it.
- The map's fill transition belongs to the stylesheet (`.map-state`), not to
  d3, so a year change animates once rather than twice.

## A trap worth knowing

**Any CSS `fill` rule beats an SVG `fill` attribute**, however unspecific the
selector. Label classes therefore set their default fill only under
`:not([fill])`; a class-level `fill` silently overrode every label the charts
coloured, drawing the treemap's 26.3% cream-on-cream and the tier figures in
white instead of coral and blue.

## Interaction

- Line charts: crosshair to the nearest year, one tooltip for every series.
- Bars, tiles, states: the mark is the hit target and lifts on hover.
- Every standard figure has a table-view toggle. Tooltips enhance, never gate.
- Series names reach the DOM via `textContent` — they come from government
  spreadsheets.

## Narrative rule

Two kinds of statement sit on the page and are never blurred: **computed** from
the budget documents and injected at render, never typed into markup; and
**cited** from outside, each attributed in the footer's claims block. A caption
states the unit, the definition and the caveat, and never asserts a cause the
data cannot carry. The explainer copy itself is being rewritten separately; see
`docs/COPY-HANDOFF.md`.

## Checked against

`references/anti-patterns.md`: no dual axes, no recolor-on-filter, no cycled
hues, no value-ramp on nominal categories, no rainbow, no number on every
point, no borders around marks, no dashed gridlines or chrome, no serif hero
figure, no tooltip-gated values, no large saturated blocks (the treemap's large
tiles are grey; only the small subject tiles carry colour).

## Change log

- 2026-10-17 — First resolution: FT + NYT Upshot editorial-statistical.
- 2026-10-17 — State layer: benchmark plot, two-tier comparison, ranked bars,
  choropleth; charts made responsive to series length.
- 2026-10-17 — **Re-resolved** at the owner's request: data-journalism
  interactive × Swiss × Bloomberg Graphics, dark-first. New semantic colour
  system, validated in both modes with no contrast warnings. Serif dropped for
  a single grotesque family. Scrollytelling engine, hero, four motion pieces,
  animated map, theme toggle, progress bar. Fixed the CSS-fill-over-attribute
  trap above.

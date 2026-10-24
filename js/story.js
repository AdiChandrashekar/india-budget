// The scroll-driven graphics. Each is built once and then told which step is
// active; `step(n)` must reach the state for step n from any other step,
// forwards or back, because readers scroll in both directions and skip.
//
// Colour follows the page's semantic system (DESIGN.md): coral is the Union,
// blue is the states, amber is the 6% promise, grey is everything else.

import {
  cssVar, hostWidth, tooltipFor, showTip, hideTip, toHostPx, isDark,
  BLUE_RAMP_LIGHT, BLUE_RAMP_DARK,
} from "./charts.js";

const d3 = window.d3;

function reduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function dur(ms) { return reduced() ? 0 : ms; }

function frame(host, height, margin) {
  host.textContent = "";
  const width = hostWidth(host);
  const svg = d3.select(host).append("svg")
    .attr("viewBox", "0 0 " + width + " " + height)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  return {
    svg,
    width,
    inner: { w: width - margin.left - margin.right, h: height - margin.top - margin.bottom },
    g: svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")"),
  };
}

// --------------------------------------------------------------------------
// The 6% gauge. Step 0 is the target alone; steps 1-3 bring in each published
// measurement; step 4 shades the spread between them, which is the point:
// the country cannot say to within two percentage points how far short of
// its own target it is.
// --------------------------------------------------------------------------

export function gauge(host, opts) {
  if (!d3) return { step() {} };
  const { marks, target, max, format, ariaLabel } = opts;
  const narrow = hostWidth(host) < 560;
  const height = narrow ? 400 : 470;
  const margin = { top: 92, right: narrow ? 12 : 36, bottom: 48, left: narrow ? 12 : 36 };
  const { svg, g, inner } = frame(host, height, margin);
  if (ariaLabel) svg.attr("aria-label", ariaLabel);

  const ink = cssVar("--ink", "#f1eee8");
  const muted = cssVar("--ink-muted", "#7b838e");
  const amber = cssVar("--target", "#f2b02e");
  const ground = cssVar("--ground", "#0c0f14");
  const x = d3.scaleLinear().domain([0, max]).range([0, inner.w]);

  const axis = g.append("g").attr("class", "axis")
    .attr("transform", "translate(0," + inner.h + ")")
    .call(d3.axisBottom(x).ticks(narrow ? 4 : 8).tickFormat(format).tickSize(0).tickPadding(12));
  axis.select(".domain").attr("stroke", cssVar("--rule-strong", "#2f3741"));

  const rowY = (i) => 16 + i * Math.min(78, (inner.h - 30) / Math.max(marks.length, 1));

  // the spread between the published measures - shown last
  const lo = d3.min(marks, (m) => m.value);
  const hi = d3.max(marks, (m) => m.value);
  const spread = g.append("g").attr("opacity", 0);
  spread.append("rect")
    .attr("x", x(lo)).attr("width", x(hi) - x(lo))
    .attr("y", -24).attr("height", inner.h + 24)
    .attr("fill", cssVar("--wash", "rgba(241,238,232,0.07)"));
  const spreadLabel = spread.append("text").attr("class", "annot")
    .attr("x", x((lo + hi) / 2)).attr("y", -32).attr("text-anchor", "middle");
  spreadLabel.append("tspan").attr("class", "annot-strong")
    .text((hi - lo).toFixed(1) + " points of disagreement");

  // the target: the one amber mark on the chart
  const targetX = x(target.value);
  g.append("line")
    .attr("x1", targetX).attr("x2", targetX)
    .attr("y1", -44).attr("y2", inner.h)
    .attr("stroke", amber).attr("stroke-width", 3)
    .style("filter", isDark() ? "drop-shadow(0 0 8px " + amber + ")" : "none");
  g.append("text").attr("class", "big-label")
    .attr("x", targetX).attr("y", -56).attr("text-anchor", "middle")
    .attr("fill", amber)
    .style("font-size", narrow ? "34px" : "46px")
    .text(format(target.value));
  g.append("text").attr("class", "mark-label")
    .attr("x", targetX + 10).attr("y", inner.h - 10)
    .attr("fill", muted)
    .text(target.short || "target");

  const rows = marks.map((m, i) => {
    const y = rowY(i);
    const row = g.append("g").attr("opacity", 0);
    const gap = row.append("line")
      .attr("x1", x(0)).attr("x2", x(0))
      .attr("y1", y).attr("y2", y)
      .attr("stroke", cssVar("--rule-strong", "#2f3741")).attr("stroke-width", 2);
    const dot = row.append("circle")
      .attr("cx", x(0)).attr("cy", y).attr("r", narrow ? 7 : 9)
      .attr("fill", ink).attr("stroke", ground).attr("stroke-width", 3);
    const value = row.append("text").attr("class", "big-label")
      .attr("x", x(0)).attr("y", y - 16)
      .attr("text-anchor", "middle")
      .style("font-size", narrow ? "22px" : "28px")
      .text(format(m.value));
    const source = row.append("text").attr("class", "annot")
      .attr("x", x(0)).attr("y", y + 26)
      .attr("text-anchor", "middle")
      .text(narrow ? (m.short || m.label) : m.label);
    return { row, gap, dot, value, source, value_: m.value, y };
  });

  function step(n) {
    rows.forEach((r, i) => {
      const on = n >= i + 1;
      const t = d3.transition().duration(dur(on ? 900 : 300)).ease(d3.easeCubicOut);
      const vx = on ? x(r.value_) : x(0);
      r.row.transition(t).attr("opacity", on ? 1 : 0);
      r.dot.transition(t).attr("cx", vx);
      r.value.transition(t).attr("x", vx);
      r.source.transition(t).attr("x", vx);
      r.gap.transition(t).attr("x1", vx).attr("x2", on ? targetX : x(0));
    });
    spread.transition().duration(dur(600)).attr("opacity", n >= marks.length + 1 ? 1 : 0);
  }

  step(0);
  return { step };
}

// --------------------------------------------------------------------------
// Nine to one. Two bars on one scale, so length carries the comparison
// honestly - an area or a unit grid would either exaggerate it or imply the
// two tiers can be summed, and they cannot. The last step lays the Union's
// bar end to end along the states' bar, so the ratio is counted, not told.
// --------------------------------------------------------------------------

export function tierBars(host, opts) {
  if (!d3) return { step() {} };
  const { rows, format, ariaLabel } = opts;
  const narrow = hostWidth(host) < 560;
  const height = narrow ? 360 : 420;
  const margin = { top: 24, right: narrow ? 12 : 24, bottom: 24, left: narrow ? 12 : 24 };
  const { svg, g, inner } = frame(host, height, margin);
  if (ariaLabel) svg.attr("aria-label", ariaLabel);

  const max = d3.max(rows, (r) => r.value) * 1.02;
  const x = d3.scaleLinear().domain([0, max]).range([0, inner.w]);
  const barH = 24;
  const ground = cssVar("--ground", "#0c0f14");
  const track = cssVar("--dim-2", "#1b2028");
  const pitch = inner.h / rows.length;

  const drawn = rows.map((r, i) => {
    const top = i * pitch + pitch * 0.42;
    const label = g.append("text").attr("class", "mark-label")
      .attr("x", 0).attr("y", top - (narrow ? 58 : 74))
      .style("text-transform", "uppercase").style("letter-spacing", "0.12em")
      .text(r.label);
    const value = g.append("text").attr("class", "big-label")
      .attr("x", 0).attr("y", top - 14)
      .attr("fill", r.color)
      .style("font-size", narrow ? "40px" : "58px")
      .text(format(0));
    g.append("rect")
      .attr("x", 0).attr("y", top).attr("width", inner.w).attr("height", barH)
      .attr("rx", 3).attr("fill", track);
    const bar = g.append("rect")
      .attr("x", 0).attr("y", top).attr("width", 0).attr("height", barH)
      .attr("rx", 3).attr("fill", r.color);
    return { r, label, value, bar, top, shown: 0 };
  });

  // the ruler: the Union bar's length, laid along the states' bar
  const unit = rows[0].value;
  const target = rows[rows.length - 1];
  const ticks = g.append("g").attr("opacity", 0);
  const rulerTop = drawn[drawn.length - 1].top;
  // Number every segment, including a last partial one. The ratio here is
  // 8.99, so only eight whole Union-lengths fit; numbering just those would
  // have a reader count eight against a caption that says nine. The dividers
  // still sit only where a whole length ends, so the partial segment reads as
  // partial.
  const segments = Math.ceil(target.value / unit - 1e-9);
  for (let k = 1; k <= segments; k += 1) {
    const end = Math.min(unit * k, target.value);
    if (unit * k < target.value) {
      ticks.append("line")
        .attr("x1", x(end)).attr("x2", x(end))
        .attr("y1", rulerTop - 6).attr("y2", rulerTop + barH + 6)
        .attr("stroke", ground).attr("stroke-width", 3);
    }
    ticks.append("text").attr("class", "mark-label")
      .attr("x", x((unit * (k - 1) + end) / 2)).attr("y", rulerTop + barH + 22)
      .attr("text-anchor", "middle")
      .text(String(k));
  }

  function countTo(item, to) {
    const from = item.shown;
    item.shown = to;
    if (reduced()) { item.value.text(format(to)); return; }
    item.value.transition().duration(1100).ease(d3.easeCubicOut)
      .tween("text", function tween() {
        const i = d3.interpolateNumber(from, to);
        return (t) => { this.textContent = format(i(t)); };
      });
  }

  function step(n) {
    drawn.forEach((d, i) => {
      const on = n >= i;
      d.bar.transition().duration(dur(on ? 1100 : 350)).ease(d3.easeCubicOut)
        .attr("width", on ? x(d.r.value) : 0);
      countTo(d, on ? d.r.value : 0);
    });
    ticks.transition().duration(dur(600)).attr("opacity", n >= rows.length ? 1 : 0);
  }

  step(0);
  return { step };
}

// --------------------------------------------------------------------------
// The whole Union budget at true scale. Step 0 is every demand in grey; step
// 1 picks out the largest single claim on it; step 2 picks out education.
// Emphasis, not categorical: one accent at a time against the grey.
// --------------------------------------------------------------------------

export function treemapStory(host, opts) {
  if (!d3) return { step() {} };
  const { items, format, ariaLabel } = opts;
  host.textContent = "";
  const width = hostWidth(host);
  const narrow = width < 560;
  const height = narrow ? 460 : 560;
  const svg = d3.select(host).append("svg")
    .attr("viewBox", "0 0 " + width + " " + height)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  if (ariaLabel) svg.attr("aria-label", ariaLabel);
  const tip = tooltipFor(host);

  const root = d3.hierarchy({ children: items })
    .sum((d) => d.value || 0)
    .sort((a, b) => b.value - a.value);
  d3.treemap().size([width, height]).paddingInner(2).round(true)(root);
  const total = root.value || 1;

  const dim = cssVar("--dim", "#262c35");
  const coral = cssVar("--union", "#e65d31");
  const ink = cssVar("--ink", "#f1eee8");
  const ground = cssVar("--ground", "#0c0f14");

  const cells = root.leaves().map((leaf, idx) => {
    const w = leaf.x1 - leaf.x0;
    const h = leaf.y1 - leaf.y0;
    const d = leaf.data;
    const g = svg.append("g").attr("transform", "translate(" + leaf.x0 + "," + leaf.y0 + ")");
    // The tile rests at full opacity and fades in through a CSS animation,
    // not a d3 transition: step() animates `fill` on these same rects, and a
    // d3 transition there pre-empts any other unnamed one still pending,
    // which left every tile stuck at opacity 0 and the treemap blank.
    const rect = g.append("rect")
      .attr("width", Math.max(0, w)).attr("height", Math.max(0, h))
      .attr("rx", 2).attr("fill", dim)
      .attr("class", "tile-rise")
      .style("animation-delay", Math.min(idx * 9, 700) + "ms");
    const share = (100 * (d.value || 0)) / total;

    rect.on("pointerleave", () => hideTip(tip))
      .on("pointermove", (event) => {
        const [mx, my] = d3.pointer(event, svg.node());
        const pos = toHostPx(host, svg.node(), mx, my);
        showTip(tip, host, pos.x, pos.y, d.name, [
          { label: "Provision", value: format(d.value) },
          { label: "Share of Union spending", value: share.toFixed(2) + "%" },
        ]);
      });

    // big share labels, only on the tiles the story is about and only where
    // they fit - the rest is reachable by hover and in the table
    let label = null;
    if (d.group && w > 60 && h > 40) {
      label = g.append("g").attr("opacity", 0);
      label.append("text").attr("class", "big-label")
        .attr("x", 12).attr("y", Math.min(h - 14, narrow ? 34 : 50))
        .attr("fill", d.group === "education" ? "#fff" : ground)
        .style("font-size", (narrow ? 22 : Math.min(54, Math.max(22, w / 6))) + "px")
        .text(share >= 1 ? share.toFixed(1) + "%" : share.toFixed(2) + "%");
      if (h > 74 && w > 130) {
        label.append("text").attr("class", "mark-label")
          .attr("x", 13).attr("y", Math.min(h - 14, narrow ? 34 : 50) + 20)
          .attr("fill", d.group === "education" ? "#fff" : ground)
          .attr("opacity", 0.85)
          .text(d.shortName || d.name);
      }
    }
    return { rect, label, d, idx };
  });

  function fillFor(c, n) {
    if (n >= 2 && c.d.group === "education") return coral;
    if (n >= 1 && c.d.group === "interest") return ink;
    return dim;
  }

  function step(n) {
    cells.forEach((c) => {
      c.rect.transition().duration(dur(650)).ease(d3.easeCubicOut)
        .attr("fill", fillFor(c, n));
      if (c.label) {
        const on = (c.d.group === "interest" && n >= 1) || (c.d.group === "education" && n >= 2);
        c.label.transition().duration(dur(500)).attr("opacity", on ? 1 : 0);
      }
    });
  }

  step(0);
  return { step };
}

// --------------------------------------------------------------------------
// The map, as a thing that changes over time. The colour scale is fixed
// across every year, which is what makes animating it honest: a colour means
// the same share in 1990-91 as in 2025-26. Rescaling per year would make the
// map look busy while hiding the actual trend.
// --------------------------------------------------------------------------

export function mapChart(host, opts) {
  if (!d3) return { update() {} };
  const { features, format, label, domain, noDataLabel, ariaLabel } = opts;
  // The scale's ends are percentiles, so values beyond them take the end
  // colours; the key has to say "or less" and "or more" to stay true.
  const legendFormat = opts.legendFormat || ((v) => format(v));
  host.textContent = "";
  const width = hostWidth(host);
  const height = width < 560 ? 480 : 620;
  const svg = d3.select(host).append("svg")
    .attr("viewBox", "0 0 " + width + " " + height)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  if (ariaLabel) svg.attr("aria-label", ariaLabel);
  const tip = tooltipFor(host);

  const mapW = Math.min(width, height * 0.95);
  const left = (width - mapW) / 2;
  const projection = d3.geoMercator().fitExtent(
    [[left + 10, 12], [left + mapW - 10, height - 18]],
    { type: "FeatureCollection", features });
  const path = d3.geoPath(projection);

  const ramp = isDark() ? BLUE_RAMP_DARK : BLUE_RAMP_LIGHT;
  const scale = d3.scaleQuantize().domain(domain).range(ramp);
  const ground = cssVar("--ground", "#0c0f14");
  const noData = cssVar("--dim", "#262c35");
  const ink = cssVar("--ink", "#f1eee8");

  let values = new Map();
  let yearLabel = "";

  const shapes = svg.append("g").selectAll("path").data(features).join("path")
    .attr("d", path)
    .attr("class", "map-state")
    .attr("fill", noData)
    .attr("stroke", ground)
    .attr("stroke-width", 0.8)
    .on("pointerleave", function onLeave() {
      hideTip(tip);
      d3.select(this).attr("stroke-width", 0.8).attr("stroke", ground);
    })
    .on("pointermove", function onMove(event, f) {
      d3.select(this).attr("stroke-width", 2).attr("stroke", ink).raise();
      const v = values.get(f.properties.code);
      const [mx, my] = d3.pointer(event, svg.node());
      const pos = toHostPx(host, svg.node(), mx, my);
      showTip(tip, host, pos.x, pos.y, f.properties.name + (yearLabel ? " · " + yearLabel : ""), [
        v == null
          ? { label: noDataLabel || "no data", value: "—" }
          : { color: scale(v), label: label || "value", value: format(v) },
      ]);
    });

  // the key, in the space the centred map leaves free
  const legendW = Math.min(240, width - 32);
  const roomy = width > mapW + legendW + 40;
  const lg = svg.append("g").attr("transform",
    "translate(" + (roomy ? 8 : (width - legendW) / 2) + "," + (roomy ? 44 : height - 26) + ")");
  const stepW = legendW / ramp.length;
  ramp.forEach((c, i) => {
    lg.append("rect").attr("x", i * stepW).attr("y", 0)
      .attr("width", Math.max(1, stepW - 2)).attr("height", 10).attr("rx", 2)
      .attr("fill", c);
  });
  lg.append("text").attr("class", "mark-label").attr("x", 0).attr("y", 26)
    .text(legendFormat(domain[0], 0));
  lg.append("text").attr("class", "mark-label").attr("x", legendW).attr("y", 26)
    .attr("text-anchor", "end").text(legendFormat(domain[1], 1));
  if (label) {
    lg.append("text").attr("class", "mark-label").attr("x", 0).attr("y", -9)
      .style("text-transform", "uppercase").style("letter-spacing", "0.1em")
      .text(label);
  }

  // Fill is set directly and eased by the stylesheet's transition on
  // .map-state. Driving it from d3 as well would animate every frame twice,
  // and the global reduced-motion rule already turns the CSS one off.
  function update(next, year) {
    values = next;
    yearLabel = year || "";
    shapes.attr("fill", (f) => {
      const v = values.get(f.properties.code);
      return v == null ? noData : scale(v);
    });
  }

  return { update };
}

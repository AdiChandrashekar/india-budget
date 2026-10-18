// Charts, drawn with d3 v7 from a CDN global.
//
// House style is locked in DESIGN.md: charts sit on the page ground with no
// card around them, axes are hairlines, the thing worth noticing is annotated
// on the plot, and every figure has a table view behind a toggle.
//
// One idiom runs through all of it and is never spent on anything else:
// **solid stroke and filled marker mean an audited outturn; dashed stroke and
// hollow marker mean an estimate.** A budget series is part fact and part
// forecast, and a reader should be able to see where one becomes the other.

const d3 = window.d3;

const M = { top: 26, right: 132, bottom: 36, left: 72 };

// Spell the estimate basis out in tooltips. "A" is clear in a column header
// and opaque in a readout.
const BASIS_WORD = { A: "actuals", RE: "revised", BE: "budget estimate" };

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name);
  return (v || fallback).trim();
}

export function hostWidth(host) {
  return Math.max(host.clientWidth || 720, 300);
}

// Below this the right-hand label gutter costs more than it gives, so the
// legend carries identity instead. Every chart checks it the same way.
const NARROW = 560;

function frame(host, height, margin = M) {
  host.textContent = "";
  const width = Math.max(host.clientWidth || 720, 300);
  const svg = d3
    .select(host)
    .append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  const inner = {
    w: Math.max(width - margin.left - margin.right, 60),
    h: Math.max(height - margin.top - margin.bottom, 60),
  };
  return {
    svg,
    width,
    inner,
    g: svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`),
  };
}

function yAxis(g, scale, innerW, format, ticks = 5) {
  const sel = g
    .append("g")
    .attr("class", "axis")
    .call(d3.axisLeft(scale).ticks(ticks).tickFormat(format).tickSize(0).tickPadding(10));
  sel.select(".domain").remove();
  sel.selectAll(".tick").append("line")
    .attr("class", "gridline").attr("x1", 0).attr("x2", innerW);
  return sel;
}

function xAxis(g, scale, innerH, tickFormat, every = 1) {
  const axis = d3.axisBottom(scale).tickSize(0).tickPadding(10);
  if (tickFormat) axis.tickFormat(tickFormat);
  if (every > 1 && scale.domain) {
    axis.tickValues(scale.domain().filter((_, i) => i % every === 0));
  }
  const sel = g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${innerH})`).call(axis);
  sel.select(".domain").attr("stroke", cssVar("--rule-strong", "#c9c1b4"));
  return sel;
}

// --------------------------------------------------------------------------
// One tooltip per plot. Built with textContent throughout: every label here
// originates in a government spreadsheet and is untrusted input.
// --------------------------------------------------------------------------

function tooltipFor(host) {
  let tip = host.querySelector(":scope > .tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tip";
    tip.setAttribute("role", "status");
    host.appendChild(tip);
  }
  return tip;
}

function showTip(tip, host, x, y, title, rows) {
  tip.textContent = "";
  const h = document.createElement("h4");
  h.textContent = title;
  tip.appendChild(h);
  for (const r of rows) {
    const line = document.createElement("div");
    line.className = "tip-row";
    if (r.color) {
      const k = document.createElement("i");
      k.className = "line-key";
      k.style.background = r.color;
      line.appendChild(k);
    }
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = r.label;
    const v = document.createElement("span");
    v.className = "v";
    v.textContent = r.value;
    line.append(n, v);
    tip.appendChild(line);
  }
  tip.dataset.show = "true";
  const box = host.getBoundingClientRect();
  const tw = tip.offsetWidth || 170;
  const th = tip.offsetHeight || 70;
  let left = x + 16;
  if (left + tw > box.width) left = Math.max(4, x - tw - 16);
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(2, Math.min(y - th / 2, box.height - th - 2))}px`;
}

function hideTip(tip) { tip.dataset.show = "false"; }

// Convert a point in the svg's viewBox space to host pixels, so the tooltip
// lands correctly however the svg has been scaled to fit.
function toHostPx(host, svgNode, vx, vy) {
  const vb = svgNode.viewBox.baseVal;
  const box = host.getBoundingClientRect();
  return { x: (vx / vb.width) * box.width, y: (vy / vb.height) * box.height };
}

// --------------------------------------------------------------------------
// End labels. Direct labels are mandatory at this series count, so when lines
// converge the labels are spread apart and tied back with leader lines rather
// than left overlapping.
// --------------------------------------------------------------------------

function placeEndLabels(g, items, innerW, innerH) {
  const MIN = 15;
  const sorted = items.slice().sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].y - sorted[i - 1].y < MIN) sorted[i].y = sorted[i - 1].y + MIN;
  }
  let shift = sorted.length ? Math.max(0, sorted[sorted.length - 1].y - innerH) : 0;
  for (const s of sorted) s.y -= shift;

  for (const it of items) {
    if (Math.abs(it.y - it.anchorY) > 2) {
      g.append("path")
        .attr("class", "annot-leader")
        .attr("d", `M${it.anchorX + 4},${it.anchorY}L${it.anchorX + 12},${it.y}`);
    }
    const t = g.append("text")
      .attr("class", "series-label")
      .attr("x", it.anchorX + 16)
      .attr("y", it.y)
      .attr("dy", "0.34em")
      .attr("fill", it.color);
    t.text(it.label);
    if (it.sub) {
      g.append("text")
        .attr("class", "mark-label")
        .attr("x", it.anchorX + 16)
        .attr("y", it.y + 14)
        .attr("dy", "0.34em")
        .text(it.sub);
    }
  }
}

// --------------------------------------------------------------------------
// Line chart, with the spread between series drawn as a band. The band is the
// subject of the first figure: the disagreement between definitions is the
// story, so it gets ink of its own rather than being left as white space.
// --------------------------------------------------------------------------

export function lineChart(host, opts) {
  if (!d3) { host.textContent = "d3 did not load."; return; }
  const {
    series, years, format, height = 400, band = false, annotation = null,
    tipFormat = format,
  } = opts;
  const narrow = hostWidth(host) < NARROW;
  const margin = narrow
    ? { top: 20, right: 16, bottom: 34, left: 48 }
    : M;
  const { svg, g, inner } = frame(host, height, margin);
  const tip = tooltipFor(host);

  const x = d3.scalePoint().domain(years).range([0, inner.w]).padding(0.5);
  const all = series.flatMap((s) => s.points.map((p) => p.value));
  const max = d3.max(all) ?? 1;
  const min = Math.min(0, d3.min(all) ?? 0);
  const y = d3.scaleLinear().domain([min, max * 1.1]).nice().range([inner.h, 0]);

  // With a quarter-century on the axis every label collides, so thin the
  // ticks to roughly nine on a desktop and five on a phone. The crosshair
  // still reports the exact year, so nothing is lost by not printing them all.
  const every = Math.max(1, Math.ceil(years.length / (narrow ? 5 : 9)));
  yAxis(g, y, inner.w, format, narrow ? 4 : 5);
  xAxis(g, x, inner.h, null, every);

  // the spread between the highest and lowest definition, where all are known
  if (band && series.length > 1) {
    const rows = years.map((year) => {
      const vals = series
        .map((s) => s.points.find((p) => p.year === year))
        .filter(Boolean)
        .map((p) => p.value);
      return vals.length === series.length ? { year, hi: d3.max(vals), lo: d3.min(vals) } : null;
    });
    // split into runs of consecutive years so the band breaks where data does
    let run = [];
    const runs = [];
    for (const r of rows) {
      if (!r) { if (run.length > 1) runs.push(run); run = []; } else run.push(r);
    }
    if (run.length > 1) runs.push(run);
    const area = d3.area()
      .x((d) => x(d.year)).y0((d) => y(d.lo)).y1((d) => y(d.hi));
    for (const r of runs) g.append("path").attr("class", "band").attr("d", area(r));
  }

  const line = d3.line().x((p) => x(p.year)).y((p) => y(p.value));
  const ends = [];

  for (const s of series) {
    const pts = s.points.slice().sort((a, b) => years.indexOf(a.year) - years.indexOf(b.year));
    if (!pts.length) continue;

    for (let i = 0; i < pts.length - 1; i += 1) {
      const pair = [pts[i], pts[i + 1]];
      // A gap in the data is a gap in the line, never an interpolation.
      if (parseInt(pair[1].year, 10) - parseInt(pair[0].year, 10) > 1) continue;
      const estimate = pair.some((p) => p.basis !== "A");
      g.append("path")
        .attr("class", "series-line")
        .attr("d", line(pair))
        .attr("stroke", s.color)
        .attr("stroke-dasharray", estimate ? "4 4" : null);
    }

    // Markers thin out as the series lengthens; the dashed-versus-solid
    // stroke still carries estimate-versus-outturn when they get small.
    const dense = years.length > 16;
    g.selectAll(null).data(pts).join("circle")
      .attr("cx", (p) => x(p.year))
      .attr("cy", (p) => y(p.value))
      .attr("r", dense ? 2.6 : 4)
      .attr("fill", (p) => (p.basis === "A" ? s.color : cssVar("--ground", "#faf6f0")))
      .attr("stroke", s.color)
      .attr("stroke-width", dense ? 1.5 : 2);

    const last = pts[pts.length - 1];
    ends.push({
      // the short name: a full series name does not fit the right margin,
      // and the legend already carries it in full
      label: s.short || s.label, color: s.color, sub: s.sub || "",
      anchorX: x(last.year), anchorY: y(last.value), y: y(last.value),
    });
  }

  // Direct labels need a gutter to live in. On a phone there isn't one, and
  // the legend below the chart is always present, so they are dropped rather
  // than squeezed over the plot.
  if (!narrow) {
    placeEndLabels(g, ends, inner.w, inner.h);
    for (const a of [].concat(annotation || [])) {
      drawAnnotation(g, a, x, y, inner);
    }
  }

  // crosshair: readers aim at a year, never at a 2px line
  const hair = g.append("line").attr("class", "crosshair")
    .attr("y1", 0).attr("y2", inner.h).attr("opacity", 0);

  g.append("rect").attr("class", "hit")
    .attr("width", inner.w).attr("height", inner.h)
    .on("pointerleave", () => { hideTip(tip); hair.attr("opacity", 0); })
    .on("pointermove", (event) => {
      const [mx, my] = d3.pointer(event);
      let best = years[0];
      let bestD = Infinity;
      for (const yr of years) {
        const d = Math.abs(x(yr) - mx);
        if (d < bestD) { bestD = d; best = yr; }
      }
      hair.attr("x1", x(best)).attr("x2", x(best)).attr("opacity", 1);
      const rows = series.map((s) => {
        const p = s.points.find((q) => q.year === best);
        return {
          color: s.color,
          label: p ? `${s.label} (${BASIS_WORD[p.basis] || p.basis})` : s.label,
          value: p ? tipFormat(p.value) : "not parsed",
        };
      });
      const pos = toHostPx(host, svg.node(), margin.left + x(best), margin.top + my);
      showTip(tip, host, pos.x, pos.y, best, rows);
    });
}

function drawAnnotation(g, a, x, y, inner) {
  const px = x(a.year);
  const py = y(a.value);
  const tx = Math.min(px + (a.dx ?? -16), inner.w - 8);
  const ty = py + (a.dy ?? -44);
  if (a.from != null) {
    g.append("path").attr("class", "annot-leader")
      .attr("d", `M${px},${y(a.from)}L${px},${y(a.to ?? a.value)}`);
    g.append("path").attr("class", "annot-leader")
      .attr("d", `M${px},${ty + 6}L${px},${y(a.from)}`);
  }
  const text = g.append("text").attr("class", "annot")
    .attr("x", tx).attr("y", ty)
    .attr("text-anchor", a.anchor || "end");
  text.append("tspan").attr("class", "annot-strong").text(a.headline);
  if (a.detail) {
    text.append("tspan").attr("x", tx).attr("dy", "1.25em").text(a.detail);
  }
}

// --------------------------------------------------------------------------
// Dumbbell: what was budgeted against what was spent, one row per year.
// The form the data asks for — before and after, per item — and it reads the
// gap directly instead of making the eye difference two bar heights.
// --------------------------------------------------------------------------

export function dumbbell(host, opts) {
  if (!d3) return;
  const { rows, format, height = 380, labelOf } = opts;
  const narrow = hostWidth(host) < NARROW;
  const margin = narrow
    ? { top: 24, right: 16, bottom: 34, left: 58 }
    : { top: 28, right: 124, bottom: 34, left: 70 };
  const { svg, g, inner } = frame(host, height, margin);
  const tip = tooltipFor(host);

  const y = d3.scaleBand().domain(rows.map((r) => r.year))
    .range([0, inner.h]).padding(0.42);
  const max = d3.max(rows, (r) => Math.max(r.be ?? 0, r.re ?? 0, r.a ?? 0)) ?? 1;
  const x = d3.scaleLinear().domain([0, max * 1.08]).nice().range([0, inner.w]);

  // One hue - the ministry is the Union - with the page's idiom carrying the
  // difference: hollow for an estimate, filled for an audited outturn.
  const est = cssVar("--union", "#e65d31");
  const out = cssVar("--union", "#e65d31");
  const ground = cssVar("--ground", "#faf6f0");

  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).tickSize(0).tickPadding(10))
    .select(".domain").remove();
  xAxis(g, x, inner.h, format, 1);
  g.selectAll(null).data(x.ticks(narrow ? 3 : 5)).join("line")
    .attr("class", "gridline")
    .attr("x1", (d) => x(d)).attr("x2", (d) => x(d))
    .attr("y1", 0).attr("y2", inner.h);

  for (const r of rows) {
    const cy = y(r.year) + y.bandwidth() / 2;
    const has = r.be != null && r.a != null;

    if (has) {
      g.append("line")
        .attr("x1", x(r.be)).attr("x2", x(r.a))
        .attr("y1", cy).attr("y2", cy)
        .attr("stroke", cssVar("--rule-strong", "#c9c1b4"))
        .attr("stroke-width", 2).attr("stroke-linecap", "round");
    }

    // the revised estimate, a tick on the way from promise to outturn
    if (r.re != null) {
      g.append("line")
        .attr("x1", x(r.re)).attr("x2", x(r.re))
        .attr("y1", cy - 7).attr("y2", cy + 7)
        .attr("stroke", cssVar("--ink-muted", "#8a9099"))
        .attr("stroke-width", 1.5);
    }

    // The page's one idiom, carried over from the line chart: hollow is an
    // estimate, filled is an audited outturn. It also solves the real problem
    // with a one-hue dumbbell, which is that two shades of the same blue are
    // hard to tell apart at 11px.
    if (r.be != null) {
      g.append("circle")
        .attr("cx", x(r.be)).attr("cy", cy).attr("r", 5)
        .attr("fill", ground)
        .attr("stroke", est).attr("stroke-width", 2.5);
    }
    if (r.a != null) {
      g.append("circle")
        .attr("cx", x(r.a)).attr("cy", cy).attr("r", 5.5)
        .attr("fill", out)
        .attr("stroke", ground).attr("stroke-width", 2);
    }

    // Label only the years where the comparison can actually be made; the
    // table carries the rest. Saying "not yet audited" for a year we simply
    // have not parsed would be a claim about the government, not about us.
    if (has && !narrow) {
      const pctOf = (100 * r.a) / r.be;
      g.append("text").attr("class", "mark-label")
        .attr("x", inner.w + 12).attr("y", cy).attr("dy", "0.34em")
        .attr("fill", cssVar("--ink", "#15181c"))
        .text(`${pctOf.toFixed(0)}% of the estimate`);
    } else if (labelOf && !narrow) {
      const t = labelOf(r);
      if (t) {
        g.append("text").attr("class", "mark-label")
          .attr("x", inner.w + 12).attr("y", cy).attr("dy", "0.34em")
          .attr("opacity", 0.75)
          .text(t);
      }
    }

    g.append("rect")
      .attr("x", 0).attr("y", y(r.year) - y.step() * 0.1)
      .attr("width", inner.w).attr("height", y.bandwidth() + y.step() * 0.2)
      .attr("fill", "transparent")
      .on("pointerleave", () => hideTip(tip))
      .on("pointermove", (event) => {
        const [, my] = d3.pointer(event);
        const pos = toHostPx(host, svg.node(), margin.left + inner.w / 2, margin.top + my);
        showTip(tip, host, pos.x, pos.y, r.year, [
          { color: est, label: "Budget estimate", value: format(r.be ?? NaN) },
          { color: cssVar("--ink-muted", "#8a9099"), label: "Revised", value: format(r.re ?? NaN) },
          { color: out, label: "Actuals", value: format(r.a ?? NaN) },
        ]);
      });
  }
}

// --------------------------------------------------------------------------
// Horizontal stacked bar, years as rows. Part-to-whole over time, horizontal
// because account-head names are long.
// --------------------------------------------------------------------------

export function stackedBarH(host, opts) {
  if (!d3) return;
  const { years, layers, format, height = 400, annotation = null } = opts;
  const narrow = hostWidth(host) < NARROW;
  // room above the first row for the in-chart annotation
  const margin = {
    top: annotation && !narrow ? 52 : 22,
    right: narrow ? 14 : 26,
    bottom: 36,
    left: narrow ? 56 : 72,
  };
  const { svg, g, inner } = frame(host, height, margin);
  const tip = tooltipFor(host);
  const ground = cssVar("--ground", "#faf6f0");

  const rows = years.map((year) => {
    const row = { year, total: 0, parts: [] };
    for (const l of layers) {
      const v = l.values[year];
      if (v != null && v > 0) { row.parts.push({ layer: l, value: v }); row.total += v; }
    }
    return row;
  }).filter((r) => r.total > 0);

  const y = d3.scaleBand().domain(rows.map((r) => r.year))
    .range([0, inner.h]).padding(0.34);
  const max = d3.max(rows, (r) => r.total) ?? 1;
  const x = d3.scaleLinear().domain([0, max]).range([0, inner.w]);
  const bandH = Math.min(y.bandwidth(), 24);   // marks stay thin

  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).tickSize(0).tickPadding(10))
    .select(".domain").remove();
  xAxis(g, x, inner.h, format, 1);

  for (const r of rows) {
    let acc = 0;
    const top = y(r.year) + (y.bandwidth() - bandH) / 2;
    for (const part of r.parts) {
      const x0 = x(acc);
      const x1 = x(acc + part.value);
      acc += part.value;
      // 2px gap in the ground colour does the separating, never a stroke
      const w = Math.max(0, x1 - x0 - 2);
      const rect = g.append("rect")
        .attr("x", x0).attr("y", top)
        .attr("width", w).attr("height", bandH)
        .attr("fill", part.layer.color)
        .attr("rx", 1);

      rect
        .on("pointerleave", () => { hideTip(tip); rect.attr("opacity", 1); })
        .on("pointermove", (event) => {
          rect.attr("opacity", 0.78);
          const [mx, my] = d3.pointer(event, g.node());
          const pos = toHostPx(host, svg.node(), margin.left + mx, margin.top + my);
          showTip(tip, host, pos.x, pos.y, `${part.layer.label} · ${r.year}`, [
            { color: part.layer.color, label: "Provision", value: format(part.value) },
            { label: "Share of ministry", value: `${((100 * part.value) / r.total).toFixed(1)}%` },
          ]);
        });

      // only label inside the mark when the text genuinely fits
      const text = part.layer.short || part.layer.code;
      if (w > text.length * 7.2 + 14 && bandH >= 16) {
        g.append("text")
          .attr("x", x0 + 7).attr("y", top + bandH / 2).attr("dy", "0.34em")
          .attr("class", "mark-label")
          .attr("fill", part.layer.onFill || "#fff")
          .text(text);
      }
    }
  }

  if (annotation && !narrow) {
    // Anchor to the first row: it is the one with clear space above it, and
    // the segment being called out leads every row anyway.
    const r = rows.find((q) => q.year === annotation.year) || rows[0];
    if (r && r.parts.length) {
      const i = Math.min(annotation.index ?? 0, r.parts.length - 1);
      const start = r.parts.slice(0, i).reduce((a, p) => a + p.value, 0);
      const mid = x(start + r.parts[i].value / 2);
      const topY = y(r.year) - 4;
      g.append("path").attr("class", "annot-leader")
        .attr("d", `M${mid},${topY}L${mid},${topY - 14}`);
      const t = g.append("text").attr("class", "annot")
        .attr("x", mid).attr("y", topY - 20).attr("text-anchor", "middle");
      t.append("tspan").attr("class", "annot-strong").text(annotation.headline);
      if (annotation.detail) {
        t.append("tspan").attr("x", mid).attr("dy", "1.25em").text(annotation.detail);
      }
    }
  }
}

// --------------------------------------------------------------------------
// Treemap: the whole budget at true scale, with education picked out of it.
// Emphasis, not categorical — one accent against the de-emphasis grey. A
// share is far easier to feel as area than to read off a table.
// --------------------------------------------------------------------------

export function treemap(host, opts) {
  if (!d3) return;
  const { items, format, height = 460, accent, dim, onFillAccent } = opts;
  host.textContent = "";
  const width = Math.max(host.clientWidth || 720, 300);
  const svg = d3.select(host).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  const tip = tooltipFor(host);

  const root = d3.hierarchy({ children: items })
    .sum((d) => d.value || 0)
    .sort((a, b) => b.value - a.value);
  d3.treemap().size([width, height]).paddingInner(2).round(true)(root);

  const total = root.value || 1;

  for (const leaf of root.leaves()) {
    const w = leaf.x1 - leaf.x0;
    const h = leaf.y1 - leaf.y0;
    if (w <= 0 || h <= 0) continue;
    const d = leaf.data;
    const fill = d.highlight ? accent : dim;

    const cell = svg.append("g").attr("transform", `translate(${leaf.x0},${leaf.y0})`);
    const rect = cell.append("rect")
      .attr("width", w).attr("height", h)
      .attr("fill", fill)
      .attr("rx", 1);

    const share = (100 * (d.value || 0)) / total;
    rect
      .on("pointerleave", () => { hideTip(tip); rect.attr("opacity", 1); })
      .on("pointermove", (event) => {
        rect.attr("opacity", 0.8);
        const [mx, my] = d3.pointer(event, svg.node());
        const pos = toHostPx(host, svg.node(), mx, my);
        showTip(tip, host, pos.x, pos.y, d.name, [
          { color: fill, label: "Provision", value: format(d.value) },
          { label: "Share of Union spending", value: `${share.toFixed(2)}%` },
        ]);
      });

    // labels only where they fit with padding; otherwise the tooltip and the
    // table view carry the value
    if (w > 62 && h > 26) {
      const colour = d.highlight
        ? (onFillAccent || "#fff")
        : cssVar("--ink-2", "#4d545c");
      const words = String(d.name).split(/\s+/);
      const lines = [];
      let cur = "";
      const perLine = Math.floor(w / 6.4);
      for (const word of words) {
        if ((cur + " " + word).trim().length > perLine && cur) { lines.push(cur); cur = word; }
        else cur = (cur + " " + word).trim();
        if (lines.length >= 2) break;
      }
      if (cur && lines.length < 3) lines.push(cur);

      const text = cell.append("text")
        .attr("x", 6).attr("y", 15)
        .attr("class", "mark-label")
        .attr("fill", colour)
        .style("font-weight", d.highlight ? 640 : 400);
      lines.forEach((ln, i) => {
        text.append("tspan").attr("x", 6).attr("dy", i ? "1.15em" : 0).text(ln);
      });
      if (h > 46) {
        text.append("tspan").attr("x", 6).attr("dy", "1.3em")
          .attr("opacity", 0.85)
          .text(share >= 0.1 ? `${share.toFixed(1)}%` : "<0.1%");
      }
    }
  }
}

// --------------------------------------------------------------------------

export function legend(host, items) {
  host.textContent = "";
  for (const i of items) {
    const span = document.createElement("span");
    const key = document.createElement("i");
    key.className = i.shape === "rect" ? "rect-key" : "line-key";
    key.style.background = i.color;
    if (i.dash) {
      key.style.background = "none";
      key.style.borderTop = `2px dashed ${i.color}`;
      key.style.height = "0";
    }
    if (i.hollow) {
      key.style.background = "none";
      key.style.border = `2px solid ${i.color}`;
      key.style.height = "10px";
      key.style.width = "10px";
      key.style.borderRadius = "50%";
    }
    const label = document.createElement("span");
    label.textContent = i.label;
    span.append(key, label);
    host.appendChild(span);
  }
}

export { cssVar };

// --------------------------------------------------------------------------
// Benchmark plot: several measurements of the same quantity against one
// target. The measurements disagree because they use different definitions,
// so they are one hue, not a categorical set — the variation is in the method,
// not in the thing being measured. The target is a reference rule in ink, not
// a series.
// --------------------------------------------------------------------------

export function benchmarkPlot(host, opts) {
  if (!d3) return;
  const { marks, target, max, format, height = 220 } = opts;
  const narrow = hostWidth(host) < NARROW;
  const margin = { top: 34, right: narrow ? 16 : 30, bottom: 34, left: narrow ? 16 : 30 };
  const { svg, g, inner } = frame(host, height, margin);
  const tip = tooltipFor(host);

  const x = d3.scaleLinear().domain([0, max]).range([0, inner.w]);
  const ink = cssVar("--ink", "#15181c");
  const accent = cssVar("--ink", "#15181c");
  const ground = cssVar("--ground", "#faf6f0");

  const axisY = inner.h - 6;
  g.append("line")
    .attr("x1", 0).attr("x2", inner.w).attr("y1", axisY).attr("y2", axisY)
    .attr("stroke", cssVar("--rule-strong", "#c9c1b4"));
  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${axisY})`)
    .call(d3.axisBottom(x).ticks(narrow ? 4 : 7).tickFormat(format).tickSize(0).tickPadding(9))
    .select(".domain").remove();

  // the target
  g.append("line")
    .attr("x1", x(target.value)).attr("x2", x(target.value))
    .attr("y1", -10).attr("y2", axisY)
    .attr("stroke", ink).attr("stroke-width", 1.5);
  const tl = g.append("text").attr("class", "annot")
    .attr("x", x(target.value)).attr("y", -18).attr("text-anchor", "end");
  tl.append("tspan").attr("class", "annot-strong").text(target.label);

  // the measurements, stacked so their labels never collide
  const step = Math.max(22, (axisY - 16) / Math.max(marks.length, 1));
  marks.forEach((m, i) => {
    const cy = 10 + i * step;
    g.append("line")
      .attr("x1", x(m.value)).attr("x2", x(target.value))
      .attr("y1", cy).attr("y2", cy)
      .attr("stroke", cssVar("--rule", "#e4ddd2")).attr("stroke-width", 1);
    const dot = g.append("circle")
      .attr("cx", x(m.value)).attr("cy", cy).attr("r", 6)
      .attr("fill", accent).attr("stroke", ground).attr("stroke-width", 2);
    const label = g.append("text")
      .attr("class", "mark-label")
      .attr("x", x(m.value) - 11).attr("y", cy).attr("dy", "0.34em")
      .attr("text-anchor", "end")
      .attr("fill", ink);
    label.text(`${format(m.value)}`);
    if (!narrow) {
      g.append("text").attr("class", "annot")
        .attr("x", x(m.value) + 12).attr("y", cy).attr("dy", "0.34em")
        .text(m.label);
    }
    dot.on("pointerleave", () => hideTip(tip))
      .on("pointermove", (event) => {
        const [mx, my] = d3.pointer(event, g.node());
        const pos = toHostPx(host, svg.node(), margin.left + mx, margin.top + my);
        showTip(tip, host, pos.x, pos.y, m.label, [
          { color: accent, label: m.detail || "share of GDP", value: format(m.value) },
          { label: "short of target by", value: format(target.value - m.value) },
        ]);
      });
  });
}

// --------------------------------------------------------------------------
// Ranked bars: one measure across many entities, ordered. One series, so one
// hue for every bar — colouring by value would burn the only free channel on
// information the bar length already carries. A reference rule marks the
// aggregate.
// --------------------------------------------------------------------------

export function rankedBars(host, opts) {
  if (!d3) return;
  const {
    items, format, reference = null, highlight = [], barHeight = 17,
  } = opts;
  const narrow = hostWidth(host) < NARROW;
  const margin = {
    top: reference ? 34 : 14,
    right: narrow ? 46 : 64,
    bottom: 30,
    left: narrow ? 104 : 150,
  };
  const height = margin.top + margin.bottom + items.length * barHeight;
  const { svg, g, inner } = frame(host, height, margin);
  const tip = tooltipFor(host);

  const y = d3.scaleBand().domain(items.map((d) => d.name))
    .range([0, inner.h]).padding(0.28);
  const max = d3.max(items, (d) => d.value) ?? 1;
  const x = d3.scaleLinear().domain([0, max * 1.02]).nice().range([0, inner.w]);

  const accent = cssVar("--states", "#3d8bff");
  const dim = cssVar("--dim", "#d9d2c6");
  const ink = cssVar("--ink", "#15181c");

  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${inner.h})`)
    .call(d3.axisBottom(x).ticks(narrow ? 4 : 6).tickFormat(format).tickSize(0).tickPadding(8))
    .select(".domain").remove();
  g.selectAll(null).data(x.ticks(narrow ? 4 : 6)).join("line")
    .attr("class", "gridline")
    .attr("x1", (d) => x(d)).attr("x2", (d) => x(d))
    .attr("y1", 0).attr("y2", inner.h);

  // Entity names are long and the gutter is short on a phone. Truncate to
  // what fits rather than letting the text spill outside the svg, which
  // would give the whole page a horizontal scrollbar.
  const budget = margin.left - 10;
  const fit = (name) => {
    const chars = Math.floor(budget / 6.1);
    return name.length > chars ? `${name.slice(0, Math.max(3, chars - 1))}…` : name;
  };
  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).tickSize(0).tickPadding(8).tickFormat(fit))
    .select(".domain").remove();

  for (const d of items) {
    const strong = highlight.includes(d.name);
    const bar = g.append("rect")
      .attr("x", 0).attr("y", y(d.name))
      .attr("width", Math.max(0, x(d.value)))
      .attr("height", y.bandwidth())
      .attr("fill", strong ? accent : dim)
      .attr("rx", 1);
    g.append("text").attr("class", "mark-label")
      .attr("x", x(d.value) + 7)
      .attr("y", y(d.name) + y.bandwidth() / 2).attr("dy", "0.34em")
      .attr("fill", strong ? ink : cssVar("--ink-2", "#4d545c"))
      .text(format(d.value));
    bar.on("pointerleave", () => { hideTip(tip); bar.attr("opacity", 1); })
      .on("pointermove", (event) => {
        bar.attr("opacity", 0.78);
        const [mx, my] = d3.pointer(event, g.node());
        const pos = toHostPx(host, svg.node(), margin.left + mx, margin.top + my);
        showTip(tip, host, pos.x, pos.y, d.name, [
          { color: strong ? accent : dim, label: d.detail || "value", value: format(d.value) },
        ].concat(d.extra ? [{ label: d.extra.label, value: d.extra.value }] : []));
      });
  }

  if (reference) {
    g.append("line")
      .attr("x1", x(reference.value)).attr("x2", x(reference.value))
      .attr("y1", -8).attr("y2", inner.h)
      .attr("stroke", ink).attr("stroke-width", 1.25)
      .attr("opacity", 0.7);
    const t = g.append("text").attr("class", "annot")
      .attr("x", x(reference.value)).attr("y", -16).attr("text-anchor", "middle");
    t.append("tspan").attr("class", "annot-strong").text(reference.label);
  }
}

// --------------------------------------------------------------------------
// Choropleth. Sequential encoding: one hue, light to dark, because the thing
// shown is magnitude, not identity. The ramp is the documented blue scale;
// its lightest step may recede toward the surface, since near-zero should
// read as near-nothing.
// --------------------------------------------------------------------------

// Validated as ordinal ramps against each ground: monotone lightness, every
// adjacent step at least 0.06 apart, and the low end clearing 2:1 - so the
// lowest share still reads as a value and never as an empty state.
const BLUE_RAMP_LIGHT = [
  "#6aa4ea", "#418bdf", "#2b72cc", "#205ca9", "#174886", "#0e3466",
];
const BLUE_RAMP_DARK = [
  "#184f95", "#2266c0", "#3d8bff", "#6aa6ff", "#97c1ff", "#c6dcff",
];

// The page is a light design; dark exists only when the reader picks it.
function isDark() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

export function choropleth(host, opts) {
  if (!d3) return null;
  const {
    features, values, format, height = 520, label,
    noDataLabel = "no state budget of its own",
  } = opts;
  host.textContent = "";
  const width = hostWidth(host);
  const svg = d3.select(host).append("svg")
    .attr("viewBox", "0 0 " + width + " " + height)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  const tip = tooltipFor(host);

  const collection = { type: "FeatureCollection", features };
  // India is roughly as tall as it is wide, so on a wide figure the map is
  // limited by height and the sides go empty. Fit it to a centred column and
  // use the space that frees up for the key.
  const mapW = Math.min(width, height * 0.95);
  const left = (width - mapW) / 2;
  const projection = d3.geoMercator().fitExtent(
    [[left + 10, 12], [left + mapW - 10, height - 16]], collection);
  const path = d3.geoPath(projection);

  const ramp = isDark() ? BLUE_RAMP_DARK : BLUE_RAMP_LIGHT;
  const nums = features
    .map((f) => values.get(f.properties.code))
    .filter((v) => v != null);
  if (!nums.length) return null;
  const extent = d3.extent(nums);
  const scale = d3.scaleQuantize().domain(extent).range(ramp);
  const ground = cssVar("--ground", "#faf6f0");
  const noData = cssVar("--dim", "#262c35");
  const ink = cssVar("--ink", "#15181c");

  svg.append("g").selectAll("path").data(features).join("path")
    .attr("d", path)
    .attr("class", "map-state")
    .attr("fill", (f) => {
      const v = values.get(f.properties.code);
      return v == null ? noData : scale(v);
    })
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
      showTip(tip, host, pos.x, pos.y, f.properties.name, [
        v == null
          ? { label: noDataLabel, value: "—" }
          : { color: scale(v), label: label || "value", value: format(v) },
      ]);
    });

  // A sequential scale is meaningless without its key.
  const legendW = Math.min(230, width - 32);
  const lgX = width > mapW + legendW + 40 ? 8 : (width - legendW) / 2;
  const lgY = width > mapW + legendW + 40 ? 40 : height - 26;
  const lg = svg.append("g")
    .attr("transform", "translate(" + lgX + "," + lgY + ")");
  const step = legendW / ramp.length;
  ramp.forEach((colour, i) => {
    lg.append("rect")
      .attr("x", i * step).attr("y", 0)
      .attr("width", Math.max(1, step - 1.5)).attr("height", 9)
      .attr("fill", colour);
  });
  lg.append("text").attr("class", "mark-label")
    .attr("x", 0).attr("y", 23).text(format(extent[0]));
  lg.append("text").attr("class", "mark-label")
    .attr("x", legendW).attr("y", 23).attr("text-anchor", "end")
    .text(format(extent[1]));
  if (label) {
    lg.append("text").attr("class", "mark-label")
      .attr("x", legendW / 2).attr("y", -7).attr("text-anchor", "middle")
      .text(label);
  }
  return { scale, extent };
}

// --------------------------------------------------------------------------
// Motion. A figure draws itself in the first time it comes into view, once.
//
// prefers-reduced-motion is honoured by rendering the finished state
// immediately rather than by withholding it: the chart is the point, the
// animation is decoration, and decoration is what gets dropped.
// --------------------------------------------------------------------------

function reduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function animateIn(host) {
  if (!host || reduced()) return;
  const svg = host.querySelector("svg");
  if (!svg) return;

  const lines = [...svg.querySelectorAll("path.series-line")];
  // A dashed stroke already means "estimate" here, so those lines fade in
  // rather than draw: animating them would have to overwrite the dash array
  // and destroy the idiom.
  const solid = lines.filter((p) => !p.getAttribute("stroke-dasharray"));
  const dashed = lines.filter((p) => p.getAttribute("stroke-dasharray"));

  for (const p of solid) {
    const len = p.getTotalLength ? p.getTotalLength() : 0;
    if (!len) continue;
    p.style.transition = "none";
    p.style.strokeDasharray = len + " " + len;
    p.style.strokeDashoffset = String(len);
  }
  for (const p of dashed) p.style.opacity = "0";

  const bars = [...svg.querySelectorAll("rect")]
    .filter((r) => !r.classList.contains("hit"));
  for (const r of bars) {
    r.style.transformBox = "fill-box";
    r.style.transformOrigin = "left center";
    r.style.transform = "scaleX(0.001)";
  }
  const dots = [...svg.querySelectorAll("circle")];
  for (const c of dots) c.style.opacity = "0";
  const labels = [...svg.querySelectorAll("text")];
  for (const t of labels) t.style.opacity = "0";

  requestAnimationFrame(() => {
    solid.forEach((p, i) => {
      p.style.transition =
        "stroke-dashoffset 950ms cubic-bezier(.22,.61,.36,1) " + (i * 70) + "ms";
      p.style.strokeDashoffset = "0";
    });
    dashed.forEach((p, i) => {
      p.style.transition = "opacity 520ms ease " + (420 + i * 70) + "ms";
      p.style.opacity = "1";
    });
    bars.forEach((r, i) => {
      r.style.transition =
        "transform 640ms cubic-bezier(.22,.61,.36,1) " + Math.min(i * 13, 420) + "ms";
      r.style.transform = "scaleX(1)";
    });
    dots.forEach((c, i) => {
      c.style.transition = "opacity 420ms ease " + (380 + Math.min(i * 7, 320)) + "ms";
      c.style.opacity = "1";
    });
    labels.forEach((t, i) => {
      t.style.transition = "opacity 520ms ease " + (460 + Math.min(i * 5, 340)) + "ms";
      t.style.opacity = "1";
    });
  });
}

export function animateMap(host) {
  if (!host || reduced()) return;
  const paths = [...host.querySelectorAll("path.map-state")];
  for (const p of paths) {
    p.style.opacity = "0";
    p.style.transformBox = "fill-box";
    p.style.transformOrigin = "center";
    p.style.transform = "scale(0.9)";
  }
  requestAnimationFrame(() => {
    paths.forEach((p, i) => {
      const delay = i * 12;
      p.style.transition =
        "opacity 430ms ease " + delay + "ms, transform 560ms cubic-bezier(.22,.61,.36,1) " + delay + "ms";
      p.style.opacity = "1";
      p.style.transform = "scale(1)";
    });
  });
}

// Count a figure up when it first appears. The final value is written at the
// end regardless, so the DOM is correct even if the animation never runs.
export function countUp(el, value, format, duration = 950) {
  if (!el) return;
  if (reduced() || !Number.isFinite(value)) {
    el.textContent = format(value);
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = format(value * eased);
    if (t < 1) requestAnimationFrame(tick);
    else el.textContent = format(value);
  };
  requestAnimationFrame(tick);
}

// Run `fn` the first time `el` scrolls into view, then stop watching.
export function onFirstView(el, fn, opts) {
  const threshold = (opts && opts.threshold) || 0.2;
  if (!el) return;
  if (!("IntersectionObserver" in window)) { fn(); return; }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) { io.disconnect(); fn(); return; }
    }
  }, { threshold });
  io.observe(el);
}

export { tooltipFor, showTip, hideTip, toHostPx, isDark, BLUE_RAMP_LIGHT, BLUE_RAMP_DARK };

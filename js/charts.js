// Charts, drawn with d3 v7 loaded from a CDN as a global.
//
// Budget series have a quirk worth drawing honestly: within one line, early
// years are audited outturns and the last year or two are forecasts. So every
// line here can change stroke partway along, and estimate points are drawn
// hollow. A reader should be able to see where the facts stop.

const d3 = window.d3;

const MARGIN = { top: 14, right: 18, bottom: 34, left: 66 };

function frame(host, height) {
  host.innerHTML = "";
  const width = Math.max(host.clientWidth || 680, 320);
  const svg = d3
    .select(host)
    .append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("role", "img");
  return {
    svg,
    width,
    height,
    inner: {
      w: width - MARGIN.left - MARGIN.right,
      h: height - MARGIN.top - MARGIN.bottom,
    },
    g: svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`),
  };
}

function yAxis(g, scale, innerW, format) {
  const axis = d3.axisLeft(scale).ticks(6).tickFormat(format).tickSize(0).tickPadding(8);
  const sel = g.append("g").attr("class", "axis").call(axis);
  sel.select(".domain").remove();
  sel
    .selectAll(".tick")
    .append("line")
    .attr("class", "gridline")
    .attr("x1", 0)
    .attr("x2", innerW);
  return sel;
}

function xAxisBand(g, scale, innerH) {
  const sel = g
    .append("g")
    .attr("class", "axis")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(scale).tickSize(0).tickPadding(8));
  sel.select(".domain").attr("stroke", "currentColor").attr("opacity", 0.25);
  return sel;
}

// ---------------------------------------------------------------------------
// Line chart. `series` is [{label, color, points:[{year,value,basis}]}].
// ---------------------------------------------------------------------------

export function lineChart(host, { series, years, format, height = 330 }) {
  if (!d3) {
    host.innerHTML = '<p class="loading">d3 did not load.</p>';
    return;
  }
  const { g, inner } = frame(host, height);
  const x = d3.scalePoint().domain(years).range([0, inner.w]).padding(0.5);
  const values = series.flatMap((s) => s.points.map((p) => p.value));
  const max = d3.max(values) ?? 1;
  const y = d3.scaleLinear().domain([0, max * 1.08]).nice().range([inner.h, 0]);

  yAxis(g, y, inner.w, format);
  xAxisBand(g, x, inner.h);

  for (const s of series) {
    const pts = s.points.slice().sort((a, b) => years.indexOf(a.year) - years.indexOf(b.year));
    if (!pts.length) continue;

    // Split into runs of outturn and runs of estimate so the stroke can change
    // where the data stops being an actual.
    const line = d3.line().x((p) => x(p.year)).y((p) => y(p.value));
    for (let i = 0; i < pts.length - 1; i += 1) {
      const pair = [pts[i], pts[i + 1]];
      // Leave a break where years are missing. Joining 2019-20 straight to
      // 2022-23 would draw three years of trend that was never measured.
      const span = parseInt(pair[1].year.slice(0, 4), 10)
        - parseInt(pair[0].year.slice(0, 4), 10);
      if (span > 1) continue;
      const estimate = pair.some((p) => p.basis !== "A");
      g.append("path")
        .attr("class", "series-line")
        .attr("d", line(pair))
        .attr("stroke", s.color)
        .attr("stroke-dasharray", estimate ? "5 4" : null)
        .attr("opacity", estimate ? 0.85 : 1);
    }
    g.selectAll(null)
      .data(pts)
      .join("circle")
      .attr("class", "series-dot")
      .attr("cx", (p) => x(p.year))
      .attr("cy", (p) => y(p.value))
      .attr("r", 3.6)
      .attr("fill", (p) => (p.basis === "A" ? s.color : "var(--panel)"))
      .attr("stroke", s.color)
      .append("title")
      .text((p) => `${s.label}\n${p.year} ${p.basis}: ${format(p.value)}`);
  }
}

// ---------------------------------------------------------------------------
// Grouped bars, for comparing the three estimate types in the same year.
// ---------------------------------------------------------------------------

export function groupedBars(host, { years, groups, format, height = 330 }) {
  if (!d3) return;
  const { g, inner } = frame(host, height);
  const x0 = d3.scaleBand().domain(years).range([0, inner.w]).paddingInner(0.25).paddingOuter(0.1);
  const x1 = d3
    .scaleBand()
    .domain(groups.map((s) => s.key))
    .range([0, x0.bandwidth()])
    .padding(0.08);
  const max = d3.max(groups.flatMap((s) => years.map((yr) => s.values[yr] ?? 0))) ?? 1;
  const y = d3.scaleLinear().domain([0, max * 1.1]).nice().range([inner.h, 0]);

  yAxis(g, y, inner.w, format);
  xAxisBand(g, x0, inner.h);

  for (const s of groups) {
    g.selectAll(null)
      .data(years.filter((yr) => s.values[yr] != null))
      .join("rect")
      .attr("x", (yr) => x0(yr) + x1(s.key))
      .attr("width", x1.bandwidth())
      .attr("y", (yr) => y(s.values[yr]))
      .attr("height", (yr) => inner.h - y(s.values[yr]))
      .attr("fill", s.color)
      .attr("rx", 2)
      .append("title")
      .text((yr) => `${s.label}\n${yr}: ${format(s.values[yr])}`);
  }
}

// ---------------------------------------------------------------------------
// Stacked bars, for composition: what a total is made of, year by year.
// ---------------------------------------------------------------------------

export function stackedBars(host, { years, layers, format, height = 340 }) {
  if (!d3) return;
  const { g, inner } = frame(host, height);
  const rows = years.map((yr) => {
    const row = { year: yr };
    for (const l of layers) row[l.key] = l.values[yr] ?? 0;
    return row;
  });
  const keys = layers.map((l) => l.key);
  const stacked = d3.stack().keys(keys)(rows);
  const x = d3.scaleBand().domain(years).range([0, inner.w]).padding(0.28);
  const max = d3.max(rows, (r) => keys.reduce((a, k) => a + r[k], 0)) ?? 1;
  const y = d3.scaleLinear().domain([0, max * 1.08]).nice().range([inner.h, 0]);
  const colour = new Map(layers.map((l) => [l.key, l.color]));
  const label = new Map(layers.map((l) => [l.key, l.label]));

  yAxis(g, y, inner.w, format);
  xAxisBand(g, x, inner.h);

  g.selectAll(null)
    .data(stacked)
    .join("g")
    .attr("fill", (s) => colour.get(s.key))
    .selectAll("rect")
    .data((s) => s.map((seg) => Object.assign({ key: s.key }, seg)))
    .join("rect")
    .attr("x", (s) => x(s.data.year))
    .attr("width", x.bandwidth())
    .attr("y", (s) => y(s[1]))
    .attr("height", (s) => Math.max(0, y(s[0]) - y(s[1])))
    .append("title")
    .text((s) => `${label.get(s.key)}\n${s.data.year}: ${format(s[1] - s[0])}`);
}

export function legend(host, items) {
  host.innerHTML = items
    .map(
      (i) =>
        `<span><i class="swatch${i.dash ? " dash" : ""}" style="background:${
          i.dash ? "none" : i.color
        };color:${i.color}"></i>${i.label}</span>`,
    )
    .join("");
}

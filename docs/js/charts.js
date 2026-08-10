/* ─── Interactive SVG Chart Engine & Table Utilities ───────────────────────
   Self-contained, dependency-free interactive SVG charts and data tables.
   Adheres to style_guide.md design specifications.
*/

const NS = "http://www.w3.org/2000/svg";

// Default configuration constants
const DEFAULT_DECIMAL_PLACES = 1;
const DEFAULT_TICK_COUNT = 5;
const NICE_STEP_MULTIPLIERS = [1, 2, 2.5, 5, 10];
const TICK_PRECISION = 6; // Decimal places for tick values
const TOOLTIP_PADDING = 12; // Padding from edge for tooltip positioning

function el(name, attrs) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v != null) node.setAttribute(k, v);
  }
  return node;
}

/**
 * Parse CSV text with proper handling of quoted fields, escaped quotes, and empty values.
 * Follows RFC 4180 standard for CSV format.
 */
export function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (!lines.length || !lines[0]) return [];
  
  // Parse header line
  const headers = parseCSVLine(lines[0]);
  
  return lines.slice(1).map((line) => {
    const cells = parseCSVLine(line);
    const row = {};
    headers.forEach((h, i) => {
      row[h] = cells[i] !== undefined ? cells[i] : '';
    });
    return row;
  });
}

/**
 * Parse a single CSV line, handling quoted fields properly.
 * @returns {string[]} Array of cell values
 */
function parseCSVLine(line) {
  const cells = [];
  let current = '';
  let inQuotes = false;
  let i = 0;
  
  while (i < line.length) {
    const char = line[i];
    const nextChar = line[i + 1];
    
    if (inQuotes) {
      if (char === '"') {
        // Check for escaped quote
        if (nextChar === '"') {
          current += '"';
          i += 2;
          continue;
        } else {
          // End of quoted field
          inQuotes = false;
          i++;
          continue;
        }
      } else {
        current += char;
        i++;
        continue;
      }
    } else {
      // Not in quotes
      if (char === '"') {
        inQuotes = true;
        i++;
        continue;
      } else if (char === ',') {
        cells.push(current.trim());
        current = '';
        i++;
        continue;
      } else {
        current += char;
        i++;
        continue;
      }
    }
  }
  
  // Add the last cell
  cells.push(current.trim());
  
  return cells;
}

export function formatNum(v) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return Math.round(Number(v)).toLocaleString("en-US");
}

export function formatDecimal(v, decimals = DEFAULT_DECIMAL_PLACES) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return Number(v).toFixed(decimals);
}

export function formatPercent(v, decimals = DEFAULT_DECIMAL_PLACES) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return `${Number(v).toFixed(decimals)}%`;
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FULL_MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

export function monthLabel(iso, full = false) {
  const s = String(iso || "");
  const m = Number(s.slice(5, 7));
  const y = Number(s.slice(0, 4));
  if (!Number.isFinite(m) || !Number.isFinite(y) || m < 1 || m > 12) return s || "—";
  return full ? `${FULL_MONTH_NAMES[m - 1]} ${y}` : `${MONTH_NAMES[m - 1]} ${y}`;
}

export function isoDate(s) {
  const v = String(s).slice(0, 10);
  const full = v.length === 7 ? `${v}-01` : v;
  return new Date(`${full}T00:00:00Z`);
}

/**
 * Normalize a date value to YYYY-MM format for comparison.
 * Handles ISO strings (YYYY-MM-DD or YYYY-MM), Date objects, or timestamps.
 * @param {string|Date|number} date - The date value to normalize
 * @returns {string} - YYYY-MM formatted string
 */
export function normalizeDateMonth(date) {
  if (!date) return '';
  
  // If already a string in YYYY-MM format
  const str = String(date);
  if (str.length >= 7 && str.slice(4, 5) === '-') {
    return str.slice(0, 7);
  }
  
  // Convert to Date object and format
  const d = typeof date === 'number' ? new Date(date) : isoDate(date);
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
}

function niceTicks(min, max, count = DEFAULT_TICK_COUNT) {
  if (min === max) {
    min = min - 1;
    max = max + 1;
  }
  const span = max - min;
  const rawStep = span / count;
  const pow = Math.pow(10, Math.floor(Math.log10(rawStep || 1)));
  let step = pow;
  for (const m of NICE_STEP_MULTIPLIERS) {
    if (m * pow >= rawStep) {
      step = m * pow;
      break;
    }
  }
  const tickMin = Math.floor(min / step) * step;
  const tickMax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let t = tickMin; t <= tickMax + step * 0.5; t += step) {
    ticks.push(+t.toFixed(TICK_PRECISION));
  }
  return { ticks, min: tickMin, max: tickMax };
}

// Global tooltip singleton
let activeTooltip = null;
function getTooltip() {
  if (!activeTooltip) {
    activeTooltip = document.createElement("div");
    activeTooltip.className = "chart-tooltip";
    activeTooltip.setAttribute("role", "tooltip");
    activeTooltip.style.display = "none";
    document.body.appendChild(activeTooltip);
  }
  return activeTooltip;
}

function showTooltip(html, x, y) {
  const tip = getTooltip();
  tip.innerHTML = html;
  tip.style.display = "block";
  const tipW = tip.offsetWidth;
  const tipH = tip.offsetHeight;

  let left = x + TOOLTIP_PADDING;
  let top = y - tipH / 2;

  if (left + tipW > window.innerWidth - TOOLTIP_PADDING) {
    left = x - tipW - TOOLTIP_PADDING;
  }
  if (left < TOOLTIP_PADDING) left = TOOLTIP_PADDING;
  if (top < TOOLTIP_PADDING) top = TOOLTIP_PADDING;
  if (top + tipH > window.innerHeight - TOOLTIP_PADDING) {
    top = window.innerHeight - tipH - TOOLTIP_PADDING;
  }

  tip.style.left = `${left + window.scrollX}px`;
  tip.style.top = `${top + window.scrollY}px`;
}

function hideTooltip() {
  const tip = getTooltip();
  tip.style.display = "none";
}

window.addEventListener("scroll", hideTooltip, { passive: true });
window.addEventListener("resize", hideTooltip, { passive: true });

/* ─── Interactive Line Chart ────────────────────────────────────────────── */

/**
 * Extract and normalize all data points from active series for axis calculation.
 */
function extractAllPoints(activeSeries) {
  return activeSeries
    .flatMap((s) => s.values.filter((p) => Number.isFinite(p.y)))
    .map((p) => ({ x: isoDate(p.x).getTime(), y: Number(p.y) }));
}

/**
 * Calculate the Y-axis range, factoring in confidence bands.
 */
function calculateYRange(activeSeries, opts) {
  const allPoints = extractAllPoints(activeSeries);
  
  if (allPoints.length === 0) return { min: 0, max: 0 };
  
  let yMinVal = 0;
  if (opts.includeZero === false) {
    yMinVal = Math.min(...allPoints.map((p) => p.y));
  }
  let yMaxVal = Math.max(...allPoints.map((p) => p.y));
  
  // Factor in bands if present
  for (const s of activeSeries) {
    if (s.band && Array.isArray(s.band.upper)) {
      for (const u of s.band.upper) {
        if (Number.isFinite(u) && u > yMaxVal) yMaxVal = u;
      }
    }
  }
  
  return { min: yMinVal, max: yMaxVal };
}

/**
 * Create the X and Y scale functions for the chart.
 */
function createScales(width, height, pad, xMin, xMax, yAxis, isDiscrete, dateKeys) {
  const yMin = yAxis.min;
  const yMax = yAxis.max;
  
  const x = (val) => {
    if (isDiscrete && dateKeys.length > 1) {
      const key = normalizeDateMonth(val);
      const idx = dateKeys.indexOf(key);
      if (idx !== -1) {
        return pad.left + (idx / (dateKeys.length - 1)) * (width - pad.left - pad.right);
      }
    }
    const t = typeof val === "number" ? val : isoDate(val).getTime();
    return pad.left + ((t - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  };
  
  const y = (v) => pad.top + (1 - (v - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);
  
  return { x, y };
}

/**
 * Extract discrete date keys from series data.
 */
function extractDateKeys(activeSeries) {
  return Array.from(new Set(activeSeries.flatMap((s) => s.values.map((p) => normalizeDateMonth(p.x))))).sort();
}

/**
 * Check if chart has no data to display.
 */
function hasNoData(activeSeries) {
  const allPoints = extractAllPoints(activeSeries);
  return allPoints.length === 0;
}

export function lineChart(container, opts = {}) {
  if (!container) return;
  const width = opts.width || 1000;
  const height = opts.height || 360;
  const pad = { top: 32, right: 28, bottom: 44, left: 68, ...opts.pad };

  const seriesState = opts.series.map((s) => ({ ...s, visible: s.visible !== false }));

  function render() {
    container.innerHTML = "";
    const activeSeries = seriesState.filter((s) => s.visible);
    
    // Check for empty data
    if (hasNoData(activeSeries)) {
      container.innerHTML = `<div class="chart-empty"><p>Select at least one series from the legend to display data.</p></div>`;
      renderLegend();
      return;
    }

    // Calculate ranges and keys
    const isDiscrete = opts.exactXTicks || false;
    const dateKeys = isDiscrete ? extractDateKeys(activeSeries) : [];
    const allPoints = extractAllPoints(activeSeries);
    const xMin = Math.min(...allPoints.map((p) => p.x));
    const xMax = Math.max(...allPoints.map((p) => p.x));
    const yRange = calculateYRange(activeSeries, opts);
    const yAxis = niceTicks(yRange.min, yRange.max, 4);
    
    // Create scale functions
    const { x, y } = createScales(width, height, pad, xMin, xMax, yAxis, isDiscrete, dateKeys);
    const svg = el("svg", {
      viewBox: `0 0 ${width} ${height}`,
      class: "interactive-svg",
      role: "img",
      "aria-label": opts.title || "Interactive line chart",
    });

    // Background rect for tracking hover
    const bg = el("rect", {
      x: pad.left,
      y: pad.top,
      width: width - pad.left - pad.right,
      height: height - pad.top - pad.bottom,
      fill: "transparent",
      class: "chart-hover-backdrop",
    });
    svg.appendChild(bg);

    // Y Grid + Ticks
    for (const tick of yAxis.ticks) {
      const yi = y(tick);
      if (yi < pad.top - 2 || yi > height - pad.bottom + 2) continue;
      svg.appendChild(el("line", { class: "grid-line", x1: pad.left, x2: width - pad.right, y1: yi, y2: yi }));
      const label = el("text", { class: "axis-tick", x: pad.left - 10, y: yi + 4, "text-anchor": "end" });
      label.textContent = opts.yFormat ? opts.yFormat(tick) : formatNum(tick);
      svg.appendChild(label);
    }

    // Y Axis Label
    if (opts.yLabel) {
      const yMid = (height - pad.top - pad.bottom) / 2 + pad.top;
      const yLabelText = el("text", {
        class: "axis-title",
        x: pad.left - 30,
        y: yMid,
        "text-anchor": "end",
        "transform": `rotate(-90, ${pad.left - 30}, ${yMid})`,
        fill: "#000",
        "font-size": "12px",
        "font-weight": "600",
      });
      yLabelText.textContent = opts.yLabel;
      svg.appendChild(yLabelText);
    }

    // X Ticks
    if (isDiscrete && dateKeys.length > 0) {
      for (const k of dateKeys) {
        const xi = x(k + "-01");
        svg.appendChild(el("line", { class: "grid-line", x1: xi, x2: xi, y1: pad.top, y2: height - pad.bottom, "stroke-dasharray": "2 2" }));
        svg.appendChild(el("line", { class: "axis-mark", x1: xi, x2: xi, y1: height - pad.bottom, y2: height - pad.bottom + 5 }));
        const label = el("text", { class: "axis-tick", x: xi, y: height - pad.bottom + 18, "text-anchor": "middle" });
        label.textContent = monthLabel(k + "-01");
        svg.appendChild(label);
      }
    } else {
      const xTickCount = opts.xTicks || (width > 600 ? 7 : 4);
      for (let i = 0; i <= xTickCount; i++) {
        const t = xMin + ((xMax - xMin) / xTickCount) * i;
        const xi = x(t);
        svg.appendChild(el("line", { class: "axis-mark", x1: xi, x2: xi, y1: height - pad.bottom, y2: height - pad.bottom + 5 }));
        const label = el("text", { class: "axis-tick", x: xi, y: height - pad.bottom + 18, "text-anchor": "middle" });
        label.textContent = monthLabel(new Date(t).toISOString().slice(0, 10));
        svg.appendChild(label);
      }
    }
    // Event Markers
    for (const e of opts.events || []) {
      const t = isoDate(e.x).getTime();
      if (t < xMin || t > xMax) continue;
      const xi = x(t);
      const g = el("g", { class: "event-marker-group" });
      g.appendChild(el("line", { class: "event-line", x1: xi, x2: xi, y1: pad.top, y2: height - pad.bottom }));
      
      const badgeW = Math.max(e.label.length * 6.8 + 16, 70);
      let badgeX = xi - badgeW / 2;
      let txtX = xi;

      if (badgeX + badgeW > width - 12) {
        badgeX = width - badgeW - 12;
        txtX = badgeX + badgeW / 2;
      }
      if (badgeX < 12) {
        badgeX = 12;
        txtX = badgeX + badgeW / 2;
      }

      const badge = el("rect", {
        x: badgeX,
        y: pad.top - 24,
        width: badgeW,
        height: 20,
        rx: 4,
        class: "event-badge-bg",
      });
      const txt = el("text", {
        class: "event-badge-txt",
        x: txtX,
        y: pad.top - 10,
        "text-anchor": "middle",
      });
      txt.textContent = e.label;
      g.appendChild(badge);
      g.appendChild(txt);
      svg.appendChild(g);
    }

    // Render Bands
    for (const s of activeSeries) {
      if (s.band && Array.isArray(s.band.lower) && Array.isArray(s.band.upper)) {
        const pts = s.values.filter((p) => Number.isFinite(p.y));
        const lowerPts = pts
          .map((p, i) => ({ rawX: p.x, v: Math.max(0, s.band.lower[i]) }))
          .filter((p) => Number.isFinite(p.v));
        const upperPts = pts
          .map((p, i) => ({ rawX: p.x, v: s.band.upper[i] }))
          .filter((p) => Number.isFinite(p.v));
        if (lowerPts.length && upperPts.length) {
          const d = [
            ...lowerPts.map((p, i) => (i === 0 ? `M ${x(p.rawX)} ${y(p.v)}` : `L ${x(p.rawX)} ${y(p.v)}`)),
            ...[...upperPts].reverse().map((p) => `L ${x(p.rawX)} ${y(p.v)}`),
            "Z",
          ].join(" ");
          svg.appendChild(el("path", { class: s.bandClassName || "chart-band", d }));
        }
      }
    }

    // Render Lines
    for (const s of activeSeries) {
      const pts = s.values.filter((p) => Number.isFinite(p.y));
      if (!pts.length) continue;
      const pathStr = pts
        .map((p, i) => {
          const xi = x(p.x);
          const yi = y(p.y);
          return i === 0 ? `M ${xi} ${yi}` : `L ${xi} ${yi}`;
        })
        .join(" ");

      svg.appendChild(el("path", {
        class: `chart-line ${s.className || "series-actual"}`,
        d: pathStr,
        fill: "none",
      }));

      // Render points if sparse or enabled
      if (opts.showPoints || pts.length <= 24) {
        const pointsGroup = el("g", { class: "points-group" });
        for (const p of pts) {
          const px = x(p.x);
          const py = y(p.y);
          const circle = el("circle", {
            class: `chart-point ${s.className || "series-actual"}`,
            cx: px,
            cy: py,
            r: opts.pointRadius || 3.5,
          });
          pointsGroup.appendChild(circle);
        }
        svg.appendChild(pointsGroup);
      }
    }

    // Hover UI elements
    const hoverGroup = el("g", { class: "hover-elements", style: "display: none;" });
    const crosshair = el("line", {
      class: "hover-crosshair",
      x1: 0,
      x2: 0,
      y1: pad.top,
      y2: height - pad.bottom,
    });
    hoverGroup.appendChild(crosshair);

    const hoverDots = activeSeries.map((s) => {
      const dot = el("circle", {
        class: `hover-dot ${s.className || "series-actual"}`,
        r: 6,
      });
      hoverGroup.appendChild(dot);
      return { dot, series: s };
    });
    svg.appendChild(hoverGroup);

    // Interactive Hover Tracking
    function handlePointer(evt) {
      const rect = svg.getBoundingClientRect();
      const clientX = evt.clientX;
      const clientY = evt.clientY;
      const svgX = ((clientX - rect.left) / rect.width) * width;

      if (svgX < pad.left || svgX > width - pad.right) {
        hoverGroup.style.display = "none";
        hideTooltip();
        return;
      }

      let closestDate = null;
      if (isDiscrete && dateKeys.length > 0) {
        const frac = (svgX - pad.left) / (width - pad.left - pad.right);
        const idx = Math.max(0, Math.min(dateKeys.length - 1, Math.round(frac * (dateKeys.length - 1))));
        closestDate = dateKeys[idx] + "-01";
      } else {
        const hoverTime = xMin + ((svgX - pad.left) / (width - pad.left - pad.right)) * (xMax - xMin);
        let minDiff = Infinity;
        for (const s of activeSeries) {
          for (const p of s.values) {
            const ptTime = isoDate(p.x).getTime();
            const diff = Math.abs(ptTime - hoverTime);
            if (diff < minDiff) {
              minDiff = diff;
              closestDate = p.x;
            }
          }
        }
      }

      if (!closestDate) return;

      const crossX = x(closestDate);
      crosshair.setAttribute("x1", crossX);
      crosshair.setAttribute("x2", crossX);
      let tooltipRows = [];
      let activeCount = 0;

      hoverDots.forEach(({ dot, series }) => {
        const matchIdx = series.values.findIndex((p) => normalizeDateMonth(p.x) === normalizeDateMonth(closestDate));
        if (matchIdx !== -1) {
          const pt = series.values[matchIdx];
          const py = y(pt.y);
          dot.style.display = "block";
          dot.setAttribute("cx", crossX);
          dot.setAttribute("cy", py);
          activeCount++;

          let ciText = "";
          if (series.band && series.band.lower && series.band.upper) {
            const low = series.band.lower[matchIdx];
            const up = series.band.upper[matchIdx];
            if (Number.isFinite(low) && Number.isFinite(up)) {
              ciText = `<div class="tip-ci">95% CI: [${formatNum(low)}, ${formatNum(up)}]</div>`;
            }
          }

          tooltipRows.push(`
            <div class="tip-row">
              <span class="tip-legend-dot ${series.className || "series-actual"}"></span>
              <span class="tip-label">${series.label}:</span>
              <strong class="tip-val">${formatNum(pt.y)}</strong>
            </div>
            ${ciText}
          `);
        } else {
          dot.style.display = "none";
        }
      });

      if (activeCount > 0) {
        hoverGroup.style.display = "block";
        const tipHtml = `
          <div class="tip-header">${monthLabel(closestDate, true)}</div>
          <div class="tip-body">${tooltipRows.join("")}</div>
        `;
        showTooltip(tipHtml, clientX, clientY);
      } else {
        hoverGroup.style.display = "none";
        hideTooltip();
      }
    }

    svg.addEventListener("pointermove", handlePointer);
    svg.addEventListener("pointerleave", () => {
      hoverGroup.style.display = "none";
      hideTooltip();
    });

    const legendNode = createLegend();
    container.innerHTML = "";
    if (legendNode) container.appendChild(legendNode);
    container.appendChild(svg);
  }

  function createLegend() {
    if (seriesState.length <= 1 && !opts.showSingleLegend) return null;
    const legend = document.createElement("div");
    legend.className = "chart-legend-interactive";
    legend.setAttribute("role", "group");
    legend.setAttribute("aria-label", "Toggle series visibility");

    seriesState.forEach((s) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `legend-chip ${s.className || "series-actual"} ${s.visible ? "is-active" : "is-muted"}`;
      btn.setAttribute("aria-pressed", s.visible ? "true" : "false");
      btn.innerHTML = `
        <span class="legend-indicator"></span>
        <span class="legend-text">${s.label}</span>
      `;
      btn.addEventListener("click", () => {
        s.visible = !s.visible;
        render();
      });
      legend.appendChild(btn);
    });

    return legend;
  }

  render();
}

/* ─── Interactive Bar Chart (Handles Positive & Negative Multipliers) ─────── */

export function barChart(container, opts = {}) {
  if (!container) return;
  const width = opts.width || 1000;
  const height = opts.height || 360;
  const pad = { top: 28, right: 28, bottom: 56, left: 68, ...opts.pad };
  const items = opts.items || [];

  if (items.length === 0) {
    container.innerHTML = `<div class="chart-empty"><p>No bar chart data available.</p></div>`;
    return;
  }

  const values = items.map((i) => Number(i.value)).filter((v) => Number.isFinite(v));
  const rawMin = Math.min(...values, 0);
  const rawMax = Math.max(...values, 0);

  const yAxis = niceTicks(rawMin, rawMax, 4);
  const yMin = yAxis.min;
  const yMax = yAxis.max;

  const y = (v) => pad.top + (1 - (v - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);
  const yZero = y(0);
  const bw = (width - pad.left - pad.right) / items.length;
  const fmt = opts.valueFormat || ((v) => (Number.isFinite(v) ? v.toFixed(2) : "—"));

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "interactive-svg",
    role: "img",
    "aria-label": opts.title || "Interactive bar chart",
  });

  // Grid lines
  for (const tick of yAxis.ticks) {
    const yi = y(tick);
    if (yi < pad.top - 2 || yi > height - pad.bottom + 2) continue;
    svg.appendChild(el("line", {
      class: tick === 0 ? "zero-axis-line" : "grid-line",
      x1: pad.left,
      x2: width - pad.right,
      y1: yi,
      y2: yi,
    }));
    const label = el("text", { class: "axis-tick", x: pad.left - 10, y: yi + 4, "text-anchor": "end" });
    label.textContent = fmt(tick);
    svg.appendChild(label);
  }

  // Bars and labels
  items.forEach((item, i) => {
    const val = Number(item.value);
    const xc = pad.left + bw * i + bw / 2;
    const barW = Math.max(bw * 0.65, 12);
    const yi = y(val);

    let barY, barH, isPos = val >= 0;
    if (isPos) {
      barY = yi;
      barH = Math.max(yZero - yi, 2);
    } else {
      barY = yZero;
      barH = Math.max(yi - yZero, 2);
    }

    const g = el("g", { class: "bar-group", tabindex: "0", role: "graphics-symbol" });
    const rect = el("rect", {
      class: item.highlight ? "bar-highlight" : isPos ? "bar-positive" : "bar-negative",
      x: xc - barW / 2,
      y: barY,
      width: barW,
      height: barH,
      rx: 3,
    });
    g.appendChild(rect);

    // Value badge above/below bar
    const vLabel = el("text", {
      class: `bar-value-label ${item.highlight ? "is-highlight" : ""}`,
      x: xc,
      y: isPos ? yi - 6 : yi + 14,
      "text-anchor": "middle",
    });
    const formattedVal = fmt(val);
    vLabel.textContent = formattedVal;
    g.appendChild(vLabel);

    // X category tick
    const isAngled = opts.angledLabels || item.label.length > 7;
    const xLabel = el("text", {
      class: `axis-tick ${item.highlight ? "is-highlight" : ""}`,
      x: isAngled ? xc + 4 : xc,
      y: height - pad.bottom + (isAngled ? 12 : 18),
      "text-anchor": isAngled ? "end" : "middle",
      transform: isAngled ? `rotate(-28, ${xc + 4}, ${height - pad.bottom + 12})` : null,
    });
    xLabel.textContent = item.label;
    g.appendChild(xLabel);

    // Interactive tooltip events
    function onBarHover(evt) {
      const tipHtml = `
        <div class="tip-header">${item.fullLabel || item.label}</div>
        <div class="tip-row">
          <span class="tip-label">${opts.xLabel || "Component"}:</span>
          <strong class="tip-val">${formattedVal}</strong>
        </div>
        ${item.note ? `<div class="tip-note">${item.note}</div>` : ""}
      `;
      showTooltip(tipHtml, evt.clientX, evt.clientY);
    }

    g.addEventListener("pointermove", onBarHover);
    g.addEventListener("pointerleave", hideTooltip);
    g.addEventListener("focus", (e) => {
      const r = rect.getBoundingClientRect();
      onBarHover({ clientX: r.left + r.width / 2, clientY: r.top });
    });
    g.addEventListener("blur", hideTooltip);

    svg.appendChild(g);
  });

  // Axis title
  if (opts.xLabel) {
    const title = el("text", {
      class: "axis-title",
      x: width / 2,
      y: height - 12,
      "text-anchor": "middle",
    });
    title.textContent = opts.xLabel;
    svg.appendChild(title);
  }

  container.innerHTML = "";
  container.appendChild(svg);
}

/* ─── Interactive Table Utilities (Sort, Search, Export) ─────────────────── */

export function enhanceTable(tableId, options = {}) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  if (!thead || !tbody) return;

  const headers = Array.from(thead.querySelectorAll("th"));
  let currentSortCol = options.defaultSortCol ?? -1;
  let sortAsc = options.defaultSortAsc ?? true;

  headers.forEach((th, colIdx) => {
    if (th.getAttribute("data-sortable") === "false") return;
    th.classList.add("sortable-header");
    th.setAttribute("tabindex", "0");
    th.setAttribute("role", "columnheader");
    th.setAttribute("aria-sort", "none");

    const sortIndicator = document.createElement("span");
    sortIndicator.className = "sort-indicator";
    sortIndicator.innerHTML = "↕";
    th.appendChild(sortIndicator);

    function triggerSort() {
      if (currentSortCol === colIdx) {
        sortAsc = !sortAsc;
      } else {
        currentSortCol = colIdx;
        sortAsc = true;
      }
      sortTable(colIdx, sortAsc);
    }

    th.addEventListener("click", triggerSort);
    th.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        triggerSort();
      }
    });
  });

  function sortTable(colIdx, asc) {
    const rows = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {
      const cellA = a.children[colIdx]?.getAttribute("data-sort-value") ?? a.children[colIdx]?.textContent.trim() ?? "";
      const cellB = b.children[colIdx]?.getAttribute("data-sort-value") ?? b.children[colIdx]?.textContent.trim() ?? "";

      const numA = Number(cellA.replace(/[^0-9.-]/g, ""));
      const numB = Number(cellB.replace(/[^0-9.-]/g, ""));

      if (!isNaN(numA) && !isNaN(numB) && cellA !== "" && cellB !== "") {
        return asc ? numA - numB : numB - numA;
      }
      return asc ? cellA.localeCompare(cellB) : cellB.localeCompare(cellA);
    });

    tbody.innerHTML = "";
    rows.forEach((r) => tbody.appendChild(r));

    headers.forEach((th, idx) => {
      const ind = th.querySelector(".sort-indicator");
      if (idx === colIdx) {
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        if (ind) ind.innerHTML = asc ? "↑" : "↓";
        th.classList.add("is-sorted");
      } else {
        th.setAttribute("aria-sort", "none");
        if (ind) ind.innerHTML = "↕";
        th.classList.remove("is-sorted");
      }
    });
  }

}

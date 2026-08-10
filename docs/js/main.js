/* ─── NYC Pothole Forecast · Main Application Controller ───────────────────
   Loads static CSV artifacts, coordinates interactive charts, populates
   accessible data tables, and provides full presentation slide-deck navigation.
*/

import {
  parseCSV,
  formatNum,
  formatPercent,
  monthLabel,
  normalizeDateMonth,
  lineChart,
  barChart,
  enhanceTable,
} from "./charts.js";

const DATA_DIR = "data/";

// Fallback KPI values when data loading fails
// These match the actual expected values from the dataset
const FALLBACK_AUG_FORECAST = 2758;
const FALLBACK_MAR_FORECAST = 10810;
const FALLBACK_MAR_ACTUAL = 25171;

async function loadCSV(filename) {
  const res = await fetch(DATA_DIR + filename);
  if (!res.ok) throw new Error(`Failed to load ${filename}: ${res.status}`);
  return parseCSV(await res.text());
}

function num(val) {
  if (val == null || val === "") return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}

function setStatText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function populateTable(tableId, rowsData) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (!tbody) return;
  tbody.innerHTML = "";
  for (const row of rowsData) {
    const tr = document.createElement("tr");
    if (row.isWinner) tr.classList.add("winner-row");

    for (const cell of row.cells) {
      const td = document.createElement("td");
      if (typeof cell === "object" && cell !== null) {
        td.innerHTML = cell.html ?? cell.text ?? "";
        if (cell.align) td.style.textAlign = cell.align;
        if (cell.sortValue != null) td.setAttribute("data-sort-value", cell.sortValue);
      } else {
        td.textContent = cell;
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

/* ─── Presentation Slide Deck Controller ─────────────────────────────────── */

function initSlideDeck() {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const dotsContainer = document.getElementById("deck-dots");
  const counter = document.getElementById("deck-counter");
  const prevBtn = document.getElementById("deck-prev");
  const nextBtn = document.getElementById("deck-next");
  const modeBtn = document.getElementById("btn-mode-toggle");
  const fullscreenBtn = document.getElementById("btn-fullscreen");
  const navLinks = Array.from(document.querySelectorAll("#nav-menu a"));

  let currentSlideIdx = 0;
  let isSlideshowMode = false;

  // Build Dots
  if (dotsContainer) {
    dotsContainer.innerHTML = "";
    slides.forEach((slide, idx) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = `deck-dot ${idx === 0 ? "is-active" : ""}`;
      dot.setAttribute("role", "tab");
      dot.setAttribute("aria-label", `Go to Slide ${idx + 1}`);
      dot.addEventListener("click", () => goToSlide(idx));
      dotsContainer.appendChild(dot);
    });
  }

  function updateUI(idx) {
    currentSlideIdx = Math.max(0, Math.min(idx, slides.length - 1));
    if (counter) counter.textContent = `Slide ${currentSlideIdx + 1} of ${slides.length}`;

    if (prevBtn) prevBtn.disabled = currentSlideIdx === 0;
    if (nextBtn) nextBtn.disabled = currentSlideIdx === slides.length - 1;

    const dots = dotsContainer?.querySelectorAll(".deck-dot");
    dots?.forEach((d, i) => {
      d.classList.toggle("is-active", i === currentSlideIdx);
      d.setAttribute("aria-selected", i === currentSlideIdx ? "true" : "false");
    });

    navLinks.forEach((link, i) => {
      link.classList.toggle("is-active", i === currentSlideIdx);
    });
  }

  function goToSlide(idx) {
    const targetIdx = Math.max(0, Math.min(idx, slides.length - 1));
    slides[targetIdx]?.scrollIntoView({ behavior: "smooth", block: "start" });
    updateUI(targetIdx);
  }

  prevBtn?.addEventListener("click", () => goToSlide(currentSlideIdx - 1));
  nextBtn?.addEventListener("click", () => goToSlide(currentSlideIdx + 1));

  // Keyboard Navigation
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (e.key === "ArrowRight" || e.key === "PageDown" || (e.key === " " && !e.shiftKey)) {
      e.preventDefault();
      goToSlide(currentSlideIdx + 1);
    } else if (e.key === "ArrowLeft" || e.key === "PageUp" || (e.key === " " && e.shiftKey)) {
      e.preventDefault();
      goToSlide(currentSlideIdx - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      goToSlide(0);
    } else if (e.key === "End") {
      e.preventDefault();
      goToSlide(slides.length - 1);
    }
  });

  // Intersection Observer for scroll tracking
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const idx = slides.indexOf(entry.target);
          if (idx !== -1) updateUI(idx);
        }
      });
    },
    { root: null, threshold: 0.5 }
  );
  slides.forEach((s) => observer.observe(s));

  // Mode Toggle (Slideshow vs Document View)
  modeBtn?.addEventListener("click", () => {
    isSlideshowMode = !isSlideshowMode;
    document.body.classList.toggle("mode-slideshow", isSlideshowMode);
    modeBtn.setAttribute("aria-pressed", isSlideshowMode ? "true" : "false");
    const modeIcon = document.getElementById("mode-icon");
    const modeText = document.getElementById("mode-text");
    if (isSlideshowMode) {
      if (modeIcon) modeIcon.textContent = "📄";
      if (modeText) modeText.textContent = "Doc View";
      goToSlide(currentSlideIdx);
    } else {
      if (modeIcon) modeIcon.textContent = "📽️";
      if (modeText) modeText.textContent = "Deck View";
    }
  });

  // Fullscreen toggle
  fullscreenBtn?.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  });

  updateUI(0);
}

/* ─── Main Application Bootstrap ─────────────────────────────────────────── */

async function main() {
  try {
    const [history, bestForecast, testForecast, seasonality, evalData, modelsComparison] = await Promise.all([
      loadCSV("history.csv"),
      loadCSV("best_forecast_data.csv"),
      loadCSV("test_forecast_data.csv"),
      loadCSV("seasonality_data.csv"),
      loadCSV("test_evaluation_data.csv"),
      loadCSV("models_comparison.csv"),
    ]);

    // ── 1. KPI Cards in Hero ──
    const augForecast = num(bestForecast[0]?.yhat) || FALLBACK_AUG_FORECAST;
    const marForecast = num(bestForecast.find((r) => normalizeDateMonth(r.ds) === "2027-03")?.yhat) || FALLBACK_MAR_FORECAST;
    const marActual = num(history.find((r) => normalizeDateMonth(r.ds) === "2026-03")?.y) || FALLBACK_MAR_ACTUAL;

    setStatText("kpi-aug-val", formatNum(augForecast));
    setStatText("kpi-mar-val", formatNum(marForecast));
    setStatText("kpi-outlier-val", formatNum(marActual));

    // ── 2. Historical Baseline Chart ──
    lineChart(document.getElementById("history-chart"), {
      title: "NYC Monthly Pothole Complaints (2009-2026)",
      series: [
        {
          label: "Monthly Pothole Complaints",
          className: "series-actual",
          values: history.map((r) => ({ x: r.ds, y: num(r.y) })),
        },
      ],
      events: [
        { x: "2015-02-01", label: "2015 Snowstorms" },
        { x: "2026-03-01", label: "Mar 2026 Peak (25,171)" },
      ],
      showPoints: false,
    });

    // ── 3. 9-Month Forecast Chart & Table with 2015 Snow Benchmark ──
    const benchmark2015Months = [
      "2015-08", "2015-09", "2015-10", "2015-11", "2015-12",
      "2016-01", "2016-02", "2016-03", "2016-04"
    ];
    const benchmark2015Values = benchmark2015Months.map((m) => {
      const match = history.find((r) => normalizeDateMonth(r.ds) === m);
      return num(match?.y);
    });

    lineChart(document.getElementById("forecast-chart"), {
      title: "9-Month Complaints Forecast with 95% Confidence Bounds",
      yLabel: "Projected # of Complaints",
      series: [
        {
          label: "Primary Forecast (B · Multiplicative)",
          className: "series-forecast",
          values: bestForecast.map((r) => ({ x: r.ds, y: num(r.yhat) })),
          band: {
            lower: bestForecast.map((r) => num(r.yhat_lower)),
            upper: bestForecast.map((r) => num(r.yhat_upper)),
          },
        },
        {
          label: "Event-Aware Alt (A · Additive+Regressors)",
          className: "series-alt",
          values: testForecast.map((r) => ({ x: r.ds, y: num(r.yhat) })),
        },
        {
          label: "2015 Post-Snow Benchmark (Actuals)",
          className: "series-benchmark",
          values: bestForecast.map((r, i) => ({ x: r.ds, y: benchmark2015Values[i] })),
        },
      ],
      showPoints: true,
      exactXTicks: true,
    });

    const seasonalContext = [
      "Summer baseline (~2.8k)",
      "Summer trough (~2.4k)",
      "Autumn baseline (~2.6k)",
      "Pre-winter low (~2.2k)",
      "Winter onset (~3.0k)",
      "Winter surge ramp (~3.9k)",
      "Late winter ramp (~5.1k)",
      "ANNUAL PEAK (10.8k; +270%)",
      "Spring thaw (~5.8k)",
    ];

    // March 2027 is at index 7 in the 9-month forecast (Aug 2026 - Apr 2027)
    const MARCH_2027_INDEX = 7;

    populateTable(
      "forecast-table",
      bestForecast.map((r, i) => {
        const yhatVal = num(r.yhat);
        const altVal = i < testForecast.length ? num(testForecast[i].yhat) : null;
        const bmarkVal = benchmark2015Values[i];
        return {
          isWinner: i === MARCH_2027_INDEX, // Highlight March peak
          cells: [
            { text: monthLabel(r.ds, true), sortValue: r.ds },
            { text: formatNum(yhatVal), sortValue: yhatVal },
            { text: altVal ? formatNum(altVal) : "—", sortValue: altVal || 0 },
            { text: bmarkVal ? formatNum(bmarkVal) : "—", sortValue: bmarkVal || 0 },
            { text: seasonalContext[i] || "Standard baseline", align: "left" },
          ],
        };
      })
    );
    enhanceTable("forecast-table");
    // ── 4. Seasonality Chart ──
    const monthlyTotals = Array.from({ length: 12 }, () => ({ sum: 0, count: 0 }));
    for (const r of seasonality) {
      const m = new Date(`${r.ds}T00:00:00Z`).getUTCMonth();
      if (Number.isFinite(m) && m >= 0 && m < 12) {
        monthlyTotals[m].sum += num(r.yearly) || 0;
        monthlyTotals[m].count += 1;
      }
    }

    const monthNotes = [
      "Winter freeze-thaw begins",
      "Cold temperatures stress asphalt",
      "ANNUAL PEAK (+148%): Maximum hydraulic freeze-thaw wedge pressure",
      "Spring thaw continues (+69%)",
      "Gradual post-thaw stabilization (+40%)",
      "Summer baseline conditions (+26%)",
      "Dry asphalt, minimal thermal stress (-8%)",
      "Low complaint volume (-18%)",
      "Stable autumn weather (-27%)",
      "Low seasonal volume (-28%)",
      "ANNUAL TROUGH (-36%): Lowest complaint generation month",
      "Early winter frost onset (-14%)",
    ];

    const seasonalItems = monthlyTotals.map((x, i) => {
      const avg = x.count > 0 ? +(x.sum / x.count).toFixed(2) : 0;
      return {
        label: monthLabel(`2026-${String(i + 1).padStart(2, "0")}-01`).slice(0, 3),
        fullLabel: monthLabel(`2026-${String(i + 1).padStart(2, "0")}-01`, true),
        value: avg,
        highlight: i === 2, // March peak
        note: monthNotes[i],
      };
    });

    barChart(document.getElementById("seasonality-chart"), {
      title: "Yearly Multiplicative Seasonal Multiplier",
      items: seasonalItems,
      xLabel: "Multiplicative Seasonal Component (0 = Baseline)",
      valueFormat: (v) => (v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)),
    });

    // ── 5. Model Selection Chart & Table ──
    // Model selection constants
    const WINNING_MODEL_MAPE = 11.4;
    const WINNING_MODEL_DESCRIPTION = 'Linear + Multiplicative';

    // Mapping of verbose model configuration names to short labels
    const MODEL_LABEL_MAP = {
      'B (multiplicative) | cp=': 'B · ',
      'A (additive-smooth) | cp=': 'A · ',
      'C (additive-flex) | cp=': 'C · ',
      'D (flat-trend) | cp=': 'D · ',
      'auto-flexible+regressors': 'flex+reg',
      'events+regressors': 'event+reg',
      'auto-flexible': 'flexible',
      'regressors': 'regress',
    };

    /**
     * Convert verbose model configuration name to short label for display.
     * Replaces known patterns with shorter, more readable labels.
     */
    const shortConfigName = (s) => {
      let result = s;
      for (const [pattern, replacement] of Object.entries(MODEL_LABEL_MAP)) {
        result = result.replace(new RegExp(pattern, 'g'), replacement);
      }
      return result;
    };

    barChart(document.getElementById("models-chart"), {
      title: "Top Model Configurations by Validation MAPE",
      items: modelsComparison.map((r, i) => ({
        label: shortConfigName(r.full),
        fullLabel: r.full,
        value: num(r.avg) || 0,
        highlight: i === 0,
        note: i === 0 ? `Validation Winner: ${WINNING_MODEL_MAPE}% Avg MAPE (${WINNING_MODEL_DESCRIPTION})` : undefined,
      })),
      xLabel: "Average Validation MAPE % (Lower is Better)",
      valueFormat: (v) => `${v.toFixed(1)}%`,
      angledLabels: true,
      pad: { bottom: 68 },
    });

    populateTable(
      "models-table",
      modelsComparison.map((r, i) => ({
        isWinner: i === 0,
        cells: [
          {
            html: `${r.full} ${i === 0 ? '<span class="tag-winner">Winner</span>' : ""}`,
            sortValue: r.full,
            align: "left",
          },
          { text: formatPercent(r.val1), sortValue: num(r.val1) },
          { text: formatPercent(r.val2), sortValue: num(r.val2) },
          { text: formatPercent(r.avg), sortValue: num(r.avg) },
          { text: formatPercent(r.cv), sortValue: num(r.cv) },
          { text: formatPercent(r.test), sortValue: num(r.test) },
        ],
      }))
    );
    enhanceTable("models-table", { defaultSortCol: 3, defaultSortAsc: true });

    // ── 6. Test Period Evaluation Chart & Table ──
    lineChart(document.getElementById("validation-chart"), {
      title: "12-Month Held-Out Test Evaluation (Aug 2025 – Jul 2026)",
      series: [
        {
          label: "Actual 311 Complaints",
          className: "series-actual",
          values: evalData.map((r) => ({ x: r.ds, y: num(r.y) })),
        },
        {
          label: "Baseline Forecast (B · Multiplicative)",
          className: "series-pred",
          values: evalData.map((r) => ({ x: r.ds, y: num(r.yhat) })),
        },
      ],
      events: [{ x: "2026-03-01", label: "March 2026 Outlier (25,171)" }],
      showPoints: true,
      exactXTicks: true,
    });

    populateTable(
      "validation-table",
      evalData.map((r) => {
        const act = num(r.y);
        const pred = num(r.yhat);
        const diff = act - pred;
        const isPos = diff >= 0;
        return {
          isWinner: normalizeDateMonth(r.ds) === "2026-03",
          cells: [
            { text: monthLabel(r.ds, true), sortValue: r.ds },
            { text: formatNum(act), sortValue: act },
            { text: formatNum(pred), sortValue: pred },
            {
              html: `<span class="${isPos ? "tag-delta-pos" : "tag-delta-neg"}">${isPos ? "+" : "−"}${formatNum(Math.abs(diff))}</span>`,
              sortValue: diff,
            },
          ],
        };
      })
    );
    enhanceTable("validation-table");

    // ── 7. Initialize Slide Deck Navigation ──
    initSlideDeck();
  } catch (err) {
    console.error("NYC Pothole Forecast Initialization Error:", err);
    document.querySelectorAll(".chart-figure").forEach((el) => {
      el.innerHTML = `<div class="chart-empty"><p>Failed to load visual data (${encodeURIComponent(err.message)}). Raw files available in <code>data/</code>.</p></div>`;
    });
  }
}

// Bootstrap on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}

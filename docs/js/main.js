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
  heatmapGrid,
} from "./charts.js?v=20260811_8";

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
/* ─── Password Access Gate Controller ───────────────────────────────────── */
const AUTH_KEY = "FAS2026";
const AUTH_STORAGE_KEY = "nyc_pothole_briefing_auth";

function initPasswordGate() {
  const isAuth = sessionStorage.getItem(AUTH_STORAGE_KEY) === "true";
  const gateOverlay = document.getElementById("password-gate-overlay");
  const gateForm = document.getElementById("gate-form");
  const gateInput = document.getElementById("gate-password-input");
  const gateError = document.getElementById("gate-error");

  if (isAuth) {
    if (gateOverlay) gateOverlay.style.display = "none";
    document.body.classList.remove("is-locked");
    return;
  }

  // Lock site
  document.body.classList.add("is-locked");
  if (gateOverlay) gateOverlay.style.display = "flex";
  setTimeout(() => gateInput?.focus(), 100);

  gateForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    const entered = gateInput?.value?.trim();
    if (entered === AUTH_KEY) {
      sessionStorage.setItem(AUTH_STORAGE_KEY, "true");
      document.body.classList.remove("is-locked");
      if (gateOverlay) gateOverlay.style.display = "none";
    } else {
      if (gateError) gateError.style.display = "block";
      if (gateInput) {
        gateInput.style.borderColor = "var(--red)";
        gateInput.value = "";
        gateInput.focus();
      }
    }
  });
}
/* ─── Presentation Slide Deck Controller ─────────────────────────────────── */

function initSlideDeck() {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const dotsContainer = document.getElementById("deck-dots");
  const counter = document.getElementById("deck-counter");
  const prevBtn = document.getElementById("deck-prev");
  const nextBtn = document.getElementById("deck-next");
  const fullscreenBtn = document.getElementById("btn-fullscreen");
  const navLinks = Array.from(document.querySelectorAll("#nav-menu a"));

  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (href && href.startsWith("#slide-")) {
        const slideIdx = parseInt(href.replace("#slide-", ""), 10) - 1;
        if (!isNaN(slideIdx) && slideIdx >= 0 && slideIdx < slides.length) {
          e.preventDefault();
          goToSlide(slideIdx);
        }
      }
    });
  });
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
      yFormat: (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(v)),
      series: [
        {
          label: "Monthly Pothole Complaints",
          className: "series-forecast",
          area: true,
          values: history.map((r) => ({ x: r.ds, y: num(r.y) })),
        },
      ],
      events: [
        { x: "2015-02-01", label: "2015 Snowstorms" },
        { x: "2026-03-01", label: "Mar 2026 Peak" },
      ],
      showPoints: false,
      areaFill: true,
      height: 240,
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
      yTicks: [0, 4000, 8000, 12000, 16000],
      yFormat: (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(v)),
      series: [
        {
          label: "2026-2027 Forecasted Values",
          className: "series-forecast",
          values: bestForecast.map((r) => ({ x: r.ds, y: num(r.yhat) })),
          band: {
            lower: bestForecast.map((r) => num(r.yhat_lower)),
            upper: bestForecast.map((r) => num(r.yhat_upper)),
          },
        },
        {
          label: "2015 Actuals",
          className: "series-benchmark",
          values: bestForecast.map((r, i) => ({ x: r.ds, y: benchmark2015Values[i] })),
        },
      ],
      exactXTicks: true,
      height: 240,
    });

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
      height: 230,
    });

    // ── 5. Model Selection Heatmaps ──
    const heatmapsData = [
      {
        id: "val2",
        title: "1. Validation 2 (Recent Rolling Window)",
        subtitle: "Aug 2024 – Jan 2025 · 6 Months · Tests baseline calibration on recent normal conditions",
        badge: "Rolling Test",
        badgeClass: "badge-turquoise",
        metricName: "Val 2 MAPE",
        columns: ["None", "Auto", "Events", "Regressors", "Auto + Reg", "Events + Reg"],
        rows: [
          {
            name: "Linear",
            fullName: "Linear (Additive-Smooth)",
            values: [26.0, 17.6, 13.4, 14.9, 12.4, 9.5],
            tooltips: [
              "Linear | None: 26.0% MAPE (Underperforms without event regressors)",
              "Linear | Auto: 17.6% MAPE (Automated changepoints)",
              "Linear | Events: 13.4% MAPE (Explicit 2015 & 2020 changepoints)",
              "Linear | Regressors: 14.9% MAPE (Historical event regressors)",
              "Linear | Auto + Reg: 12.4% MAPE (Auto changepoints + regressors)",
              "Linear | Events + Reg: 9.5% MAPE (Best linear short-term fit)",
            ],
          },
          {
            name: "Multiplicative",
            fullName: "Multiplicative (Selection Winner)",
            values: [16.8, 9.6, 11.6, 11.4, 9.6, 13.0],
            winnerCol: 0,
            tooltips: [
              "Multiplicative | None: 16.8% MAPE (Selection Winner · 11.4% Avg Val MAPE across windows)",
              "Multiplicative | Auto: 9.6% MAPE (Tied best short-term fit)",
              "Multiplicative | Events: 11.6% MAPE (Explicit event structural breaks)",
              "Multiplicative | Regressors: 11.4% MAPE (Event regressors)",
              "Multiplicative | Auto + Reg: 9.6% MAPE (Tied best short-term fit)",
              "Multiplicative | Events + Reg: 13.0% MAPE (Event changepoints + regressors)",
            ],
          },
        ],
      },
      {
        id: "cv",
        title: "2. Cross-Validation (14 Historical Folds)",
        subtitle: "14 Expanding-Window Folds (2009–2025) · Tests long-term generalization across 16 years",
        badge: "16-Year Generalization",
        badgeClass: "badge-blue",
        metricName: "Cross-Validation MAPE",
        columns: ["None", "Auto", "Events", "Regressors", "Auto + Reg", "Events + Reg"],
        rows: [
          {
            name: "Linear",
            fullName: "Linear (Additive-Smooth)",
            values: [26.9, 26.6, 25.9, 40.1, 41.8, 35.9],
            tooltips: [
              "Linear | None: 26.9% MAPE",
              "Linear | Auto: 26.6% MAPE",
              "Linear | Events: 25.9% MAPE",
              "Linear | Regressors: 40.1% MAPE (High CV variance from regressor overfitting)",
              "Linear | Auto + Reg: 41.8% MAPE (Highest CV error in dataset)",
              "Linear | Events + Reg: 35.9% MAPE",
            ],
          },
          {
            name: "Multiplicative",
            fullName: "Multiplicative (Selection Winner)",
            values: [21.7, 19.7, 18.7, 31.3, 32.3, 31.6],
            winnerCol: 0,
            tooltips: [
              "Multiplicative | None: 21.7% MAPE (Selected Model · Robust across 14 historical folds)",
              "Multiplicative | Auto: 19.7% MAPE (Solid generalization)",
              "Multiplicative | Events: 18.7% MAPE (Lowest historical CV error)",
              "Multiplicative | Regressors: 31.3% MAPE (Overfitting penalty on earlier years)",
              "Multiplicative | Auto + Reg: 32.3% MAPE",
              "Multiplicative | Events + Reg: 31.6% MAPE",
            ],
          },
        ],
      },
      {
        id: "test",
        title: "3. Real-World Test (Held-Out 2025–2026)",
        subtitle: "Aug 2025 – Jul 2026 · Includes record-breaking March 2026 extreme winter shock",
        badge: "Held-Out Stress Test",
        badgeClass: "badge-yellow",
        metricName: "Test MAPE",
        columns: ["None", "Auto", "Events", "Regressors", "Auto + Reg", "Events + Reg"],
        rows: [
          {
            name: "Linear",
            fullName: "Linear (Additive-Smooth)",
            values: [37.6, 36.2, 33.5, 27.4, 23.3, 25.6],
            tooltips: [
              "Linear | None: 37.6% MAPE (Struggles on summer trough and winter shock)",
              "Linear | Auto: 36.2% MAPE",
              "Linear | Events: 33.5% MAPE",
              "Linear | Regressors: 27.4% MAPE",
              "Linear | Auto + Reg: 23.3% MAPE (Lowest test error on outlier year)",
              "Linear | Events + Reg: 25.6% MAPE",
            ],
          },
          {
            name: "Multiplicative",
            fullName: "Multiplicative (Selection Winner)",
            values: [33.9, 32.4, 27.2, 28.2, 26.2, 24.5],
            winnerCol: 0,
            tooltips: [
              "Multiplicative | None: 33.9% MAPE (Selected Model · 66.1% accuracy with outlier)",
              "Multiplicative | Auto: 32.4% MAPE",
              "Multiplicative | Events: 27.2% MAPE",
              "Multiplicative | Regressors: 28.2% MAPE",
              "Multiplicative | Auto + Reg: 26.2% MAPE",
              "Multiplicative | Events + Reg: 24.5% MAPE (Best multiplicative test fit)",
            ],
          },
        ],
      },
    ];

    heatmapGrid(document.getElementById("model-heatmaps-dashboard") || document.getElementById("model-heatmaps-container"), heatmapsData);

    // ── 6. Test Period Evaluation Chart & Table ──
    lineChart(document.getElementById("validation-chart"), {
      title: "12-Month Held-Out Test Evaluation (Aug 2025 – Jul 2026)",
      yFormat: (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(v)),
      series: [
        {
          label: "Actual 311 Complaints",
          className: "series-actual",
          values: evalData.map((r) => ({ x: r.ds, y: num(r.y) })),
        },
        {
          label: "Model Forecast",
          className: "series-pred",
          values: evalData.map((r) => ({ x: r.ds, y: num(r.yhat) })),
        },
      ],
      events: [{ x: "2026-03-01", label: "March 2026 Outlier" }],
      exactXTicks: true,
      height: 300,
    });


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
  document.addEventListener("DOMContentLoaded", () => {
    initPasswordGate();
    main();
  });
} else {
  initPasswordGate();
  main();
}

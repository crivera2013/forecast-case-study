# NYC Pothole Demand Forecasting — Senior Lead Analyst Case Study

## Project Overview

This repository contains an end-to-end data pipeline, time-series forecasting engine, and interactive executive briefing site developed for the **NYC Department of Transportation (DOT)**.

### Purpose & Objective
- **Problem**: Following five years of unusually mild winters (2020–2025), the record snowfall of 2026 triggered an unprecedented surge in pothole complaints (25,171 in March 2026; 5.1× baseline). Legacy linear models fail to capture such extreme climate volatility.
- **Solution**: Built a 9-month predictive resource planning forecast (Aug 2026 – Apr 2027) using Meta's **Prophet (Generalized Additive Model)** trained on 200 months of NYC 311 Open Data (~918K records from Dec 2009 through Jul 2026).
- **Deliverable**: An interactive, dependency-free executive presentation deck published via GitHub Pages (`docs/`), styled under an institutional Vanguard design system to help DOT leadership proactively deploy maintenance crews, asphalt, and budget before winter surges.

---

# Setup

## Dependencies

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

To install dependencies:

```bash
uv sync
```

## Environment Variables

Create a `.env` file in the project root with your Socrata API credentials:

```
SOCRATA_APP_TOKEN=your_app_token_here
SOCRATA_API_KEY_ID=your_api_key_id_here
SOCRATA_API_KEY_SECRET=your_api_key_secret_here
```

These credentials can be obtained from the [NYC Open Data portal](https://opendata.cityofnewyork.us/).

## Static Case-Study Site (GitHub Pages)

The repository includes a static case-study site under `docs/`, published with GitHub Pages. It presents the forecast narrative and renders the charts from the CSV artifacts in `docs/data/` — no Python or server is required at runtime.

### Local preview

Serve the `docs/` directory from a static file server:

```bash
uv run python -m http.server 8000 --directory docs
```

Then open <http://localhost:8000/>.

> Note: the deployed site lives under the `/forecast-case-study/` project subpath, and the page fetches `data/*.csv` at runtime, so opening `docs/index.html` directly via `file://` will not work (browsers block `fetch` on `file://` URLs). Use the local server above or the deployed site.

### Publishing to GitHub Pages

1. Push the default branch (with `docs/` committed) to GitHub.
2. In the repository on GitHub, go to **Settings → Pages → Build and deployment**.
3. Under **Source**, select **Deploy from a branch**.
4. Set **Branch** to your default branch and **folder** to `/docs`.
5. Save. The site publishes at:

   `https://crivera2013.github.io/forecast-case-study/`

   The first deploy can take a minute or two.

### Refreshing the site data

Every chart reads only from `docs/data/`. After regenerating artifacts, refresh the copies:

```bash
cp artifacts/forecast_data.csv docs/data/
cp artifacts/best_forecast_data.csv docs/data/
cp artifacts/test_forecast_data.csv docs/data/
cp artifacts/seasonality_data.csv docs/data/
cp artifacts/test_evaluation_data.csv docs/data/
cp artifacts/test_outlier_analysis.csv docs/data/
```

Regenerate the history export (monthly pothole counts through Jul 2026):

```bash
uv run python -c "import duckdb, pandas as pd; con = duckdb.connect('data/nyc_311_road_surface.duckdb', read_only=True); df = con.execute(\"SELECT strftime(created_date, '%Y-%m') AS ds, COUNT(*) AS y FROM complaints WHERE series = 'pothole' AND created_date < DATE '2026-08-01' GROUP BY ds ORDER BY ds\").fetchdf(); df.to_csv('docs/data/history.csv', index=False)"
```

`models_comparison.csv` is a curated top-8 table of evaluation metrics; update it from `artifacts/metrics_summary.txt` when the model selection changes.
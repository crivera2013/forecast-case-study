#!/usr/bin/env python3
"""Evaluate monthly pothole forecasts for NYC 311 road-surface complaints."""

from datetime import datetime, timezone

import argparse
import duckdb
import json
import logging
import numpy as np
import os
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── CLI Argument Parsing ────────────────────────────────────────────────────

def parse_args():
    """Parse command-line arguments for configurable paths and dates."""
    parser = argparse.ArgumentParser(description="Forecast NYC pothole complaints using Prophet.")
    parser.add_argument("--db-path", default="data/nyc_311_road_surface.duckdb", help="Path to DuckDB database")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Directory to save artifacts")
    parser.add_argument("--train-end", default="2024-07-31", help="End date for training data (YYYY-MM-DD)")
    parser.add_argument("--validation-start", default="2024-08-01", help="Start date for validation (YYYY-MM-DD)")
    parser.add_argument("--validation-end", default="2025-07-31", help="End date for validation (YYYY-MM-DD)")
    parser.add_argument("--test-start", default="2025-08-01", help="Start date for test (YYYY-MM-DD)")
    parser.add_argument("--test-end", default="2026-07-31", help="End date for test (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()
# ─── Configuration ───────────────────────────────────────────────────────────

args = parse_args()

# Use CLI args or defaults
DB_PATH = args.db_path
ARTIFACTS_DIR = args.artifacts_dir
TRAIN_END = args.train_end
VALIDATION_START = args.validation_start
VALIDATION_END = args.validation_end
TEST_START = args.test_start
TEST_END = args.test_end

# Set logging level based on verbosity
if args.verbose:
    logger.setLevel(logging.DEBUG)
    logging.getLogger("prophet").setLevel(logging.DEBUG)

# Configuration for validation windows - ensure they don't overlap with test period
VALIDATION_WINDOWS = [
    {
        "name": "Aug 2023-Jul 2024",
        "train_end": "2023-07-31",
        "start": "2023-08-01",
        "end": "2024-07-31",
    },
    {
        "name": "Aug 2024-Jan 2025",  # Adjusted to end before test period
        "train_end": "2024-07-31",
        "start": "2024-08-01",
        "end": "2025-01-31",  # Ends before TEST_START (2025-08-01)
    },
]

CONFIGS = {
    "A (additive-smooth)":  {"changepoint_prior_scale": 0.01, "seasonality_prior_scale": 100.0, "growth": "linear"},
    "B (multiplicative)":   {"changepoint_prior_scale": 0.01, "seasonality_prior_scale": 100.0, "growth": "linear"},
    "C (additive-flex)":    {"changepoint_prior_scale": 0.05, "seasonality_prior_scale": 100.0, "growth": "linear"},
    "D (flat-trend)":       {"changepoint_prior_scale": 0.01, "seasonality_prior_scale": 50.0,  "growth": "flat"},
}
# Known structural breaks to test as explicit changepoints
KNOWN_CHANGEPOINTS = [
    "2015-01-01",  # Extreme snowstorms
    "2015-02-01",
    "2015-03-01",
    "2020-03-01",  # Pandemic onset
    "2020-04-01",
]

SNOWSTORM_START = "2015-01-01"
SNOWSTORM_END = "2015-03-01"
COVID_PERIOD_START = "2020-03-01"
COVID_PERIOD_END = "2021-12-01"
EVENT_REGRESSORS = ["snowstorm_2015", "covid_period"]
# Function to dynamically detect outliers in a series
def detect_outliers(series: pd.Series, threshold: float = 2.5) -> list:
    """Detect outliers in a series using the IQR method.
    
    Args:
        series: Pandas Series to analyze
        threshold: Multiplier for IQR to determine outlier bounds
        
    Returns:
        List of outlier values (not indices)
    """
    if len(series) == 0:
        return []
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr
    outliers = series[(series < lower) | (series > upper)].tolist()
    return outliers

# Placeholder for stress test dates - will be populated dynamically
STRESS_TEST_DATES = []

CHANGEPPOINT_STRATEGIES = {
    "none":                    "none",
    "auto":                    "auto",
    "events":                  "events",
    "auto-flexible":           "auto-flexible",
    "regressors":              "regressors",
    "events+regressors":       "events+regressors",
    "auto+regressors":         "auto+regressors",
    "auto-flexible+regressors": "auto-flexible+regressors",
}

NO_CHANGEPOINT_STRATEGIES = {"none", "regressors"}
EVENT_CHANGEPOINT_STRATEGIES = {"events", "events+regressors"}
REGRESSOR_STRATEGIES = {
    "regressors",
    "events+regressors",
    "auto+regressors",
    "auto-flexible+regressors",
}


def add_event_regressors(df: pd.DataFrame) -> pd.DataFrame:
    """Add historical event indicators required by regressor strategies.
    
    Args:
        df: DataFrame with a 'ds' column (datetime)
        
    Returns:
        DataFrame with added event regressor columns
        
    Raises:
        ValueError: If 'ds' column is missing
    """
    enriched = df.copy()
    if "ds" not in enriched.columns:
        raise ValueError("DataFrame must have a 'ds' column (datetime).")
    dates = enriched["ds"]
    enriched["snowstorm_2015"] = dates.between(SNOWSTORM_START, SNOWSTORM_END).astype(int)
    enriched["covid_period"] = dates.between(COVID_PERIOD_START, COVID_PERIOD_END).astype(int)
    return enriched

# ─── Helpers ─────────────────────────────────────────────────────────────────

def compute_metrics(actual: pd.Series, predicted: pd.Series) -> dict:
    """Return MAE, MAPE, RMSE between actual and predicted series.
    
    Handles division by zero for MAPE calculation by filtering out zero actuals.
    """
    # Filter out zero actuals to avoid division by zero
    mask = actual != 0
    actual_safe = actual[mask]
    predicted_safe = predicted[mask]
    
    if len(actual_safe) == 0:
        # If all actuals are zero, return NaN for MAPE
        mae = float(np.mean(np.abs(actual - predicted)))
        mape = float('nan')
        rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    else:
        mae = float(np.mean(np.abs(actual_safe - predicted_safe)))
        mape = float(np.mean(np.abs((actual_safe - predicted_safe) / actual_safe)) * 100)
        rmse = float(np.sqrt(np.mean((actual_safe - predicted_safe) ** 2)))
    
    return {"MAE": mae, "MAPE": mape, "RMSE": rmse}


def print_table(headers: list[str], rows: list[list[str]], title: str = ""):
    """Print a formatted table to stdout."""
    if title:
        print(f"\n{title}")
        print("-" * len(title))
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


# ─── Step 1: Data extraction ────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load monthly pothole complaint counts from DuckDB."""
    logger.info("=" * 60)
    logger.info("STEP 1: Data extraction")
    logger.info("=" * 60)

    try:
        con = duckdb.connect(DB_PATH)
        query = """
            SELECT strftime(created_date, '%Y-%m') as ds, COUNT(*) as y
            FROM complaints
            WHERE series = 'pothole'
            GROUP BY ds
            ORDER BY ds
        """
        df = con.execute(query).fetchdf()
        con.close()
    except Exception as e:
        logger.error(f"Failed to load data from DuckDB: {e}")
        raise

    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(int)

    before = len(df)
    df = df[df["ds"] < "2026-08-01"].copy()
    dropped = before - len(df)

    logger.info(f"  Date range: {df['ds'].min().strftime('%Y-%m')} – {df['ds'].max().strftime('%Y-%m')}")
    logger.info(f"  Total months: {len(df)}")
    logger.info(f"  Total complaints: {df['y'].sum():,}")
    logger.info(f"  Dropped incomplete months: {dropped}")
    mar26 = df[df["ds"] == "2026-03-01"]["y"].values
    if len(mar26) > 0:
        logger.info(f"  March 2026 spike: {mar26[0]:,} complaints (KEPT - genuine)")
    apr20 = df[df["ds"] == "2020-04-01"]["y"].values
    if len(apr20) > 0:
        logger.info(f"  2020-04 pandemic dip: {apr20[0]:,} complaints (KEPT)")

    return add_event_regressors(df)


# ─── Step 2: Train/validation/test split ───────────────────────────────────

def split_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split data into training, validation, and held-out test periods.
    
    Args:
        df: DataFrame with 'ds' column (datetime)
        
    Returns:
        Tuple of (train, validation, test) DataFrames
        
    Raises:
        ValueError: If splits overlap or don't cover all data
    """
    train = df[df["ds"] <= TRAIN_END].copy()
    validation = df[df["ds"].between(VALIDATION_START, VALIDATION_END)].copy()
    test = df[df["ds"].between(TEST_START, TEST_END)].copy()

    # Validate no overlap and full coverage
    all_dates = set(df["ds"])
    train_dates = set(train["ds"])
    val_dates = set(validation["ds"])
    test_dates = set(test["ds"])

    if train_dates & val_dates:
        raise ValueError("Train and validation periods overlap.")
    if val_dates & test_dates:
        raise ValueError("Validation and test periods overlap.")
    if train_dates & test_dates:
        raise ValueError("Train and test periods overlap.")
    
    covered_dates = train_dates | val_dates | test_dates
    if not covered_dates == all_dates:
        missing = all_dates - covered_dates
        raise ValueError(f"Data not fully split. Missing dates: {sorted(missing)}")

    logger.info(f"\n{'=' * 60}")
    logger.info("STEP 2: Train/validation/test split")
    logger.info("=" * 60)
    logger.info(f"  Train:      {train['ds'].min().strftime('%Y-%m')} – {train['ds'].max().strftime('%Y-%m')} ({len(train)} months)")
    logger.info(f"  Validation: {validation['ds'].min().strftime('%Y-%m')} – {validation['ds'].max().strftime('%Y-%m')} ({len(validation)} months)")
    logger.info(f"  Test:       {test['ds'].min().strftime('%Y-%m')} – {test['ds'].max().strftime('%Y-%m')} ({len(test)} months)")

    return train, validation, test


# ─── Step 3 & 4: Model training, evaluation, hyperparameter search ──────────

def _make_prophet_model(model_params: dict) -> Prophet:
    """Create a Prophet model from the selected trend and event strategy."""
    growth = model_params.get("growth", "linear")
    seasonality_mode = "multiplicative" if "multiplicative" in model_params.get("name", "") else "additive"
    strategy = model_params.get("changepoint_strategy", "auto")

    cp_kwargs = {}
    if strategy in NO_CHANGEPOINT_STRATEGIES:
        cp_kwargs["n_changepoints"] = 0
    elif strategy in EVENT_CHANGEPOINT_STRATEGIES:
        cp_kwargs["changepoints"] = KNOWN_CHANGEPOINTS
    elif strategy in {"auto-flexible", "auto-flexible+regressors"}:
        cp_kwargs["n_changepoints"] = 50

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        growth=growth,
        seasonality_mode=seasonality_mode,
        changepoint_prior_scale=model_params["changepoint_prior_scale"],
        seasonality_prior_scale=model_params["seasonality_prior_scale"],
        interval_width=0.95,
        **cp_kwargs,
    )
    regressors = model_params.get("regressors", EVENT_REGRESSORS)
    if strategy in REGRESSOR_STRATEGIES or "regressors" in model_params:
        for regressor in regressors:
            model.add_regressor(regressor, mode="additive")
    return model



def run_cross_validation(model_params: dict, train_df: pd.DataFrame) -> dict:
    """Run expanding-window validation with a six-month forecast horizon.
    
    Ensures sufficient history (at least 2 years) for each fold to capture seasonality.
    """
    model = _make_prophet_model(model_params)
    model.fit(train_df)

    # Ensure sufficient history for each fold (at least 2 years to capture seasonality)
    latest_event = max(pd.to_datetime(KNOWN_CHANGEPOINTS))
    min_history = train_df["ds"].min() + pd.DateOffset(years=2)
    first_cutoff = max(min_history, latest_event + pd.DateOffset(months=6))
    last_cutoff = train_df["ds"].max() - pd.DateOffset(months=6)
    
    # Generate cutoffs every 3 months
    cutoffs = pd.date_range(first_cutoff, last_cutoff, freq="3MS")
    if len(cutoffs) == 0:
        raise ValueError("Training data does not contain enough history for cross-validation")

    logger.debug(f"Cross-validation cutoffs: {cutoffs.tolist()}")
    cv = cross_validation(model, cutoffs=cutoffs, horizon="180 days", parallel=None)
    metrics = compute_metrics(cv["y"], cv["yhat"])
    return {
        "cv_mae": metrics["MAE"],
        "cv_mape": metrics["MAPE"],
        "cv_rmse": metrics["RMSE"],
        "num_folds": int(cv["cutoff"].nunique()),
    }

def _fit_and_forecast(model_params: dict, train_df: pd.DataFrame,
                      forecast_end: pd.Timestamp, model_cache: dict = None) -> tuple[Prophet, pd.DataFrame]:
    """Fit one configuration and forecast through the requested month.
    
    Args:
        model_params: Dictionary of model parameters
        train_df: Training DataFrame
        forecast_end: End date for forecast
        model_cache: Optional dictionary to cache fitted models by their hash
        
    Returns:
        Tuple of (fitted Prophet model, forecast DataFrame)
    """
    # Create a cache key based on model parameters and training data
    if model_cache is None:
        model_cache = {}
    
    # Create a hashable key for the model parameters
    param_key = tuple(sorted((k, str(v)) for k, v in model_params.items()))
    train_hash = hash(tuple(train_df["ds"].tolist()) + tuple(train_df["y"].tolist()))
    cache_key = (param_key, train_hash)
    
    # Check if we have a cached model
    if cache_key in model_cache:
        model = model_cache[cache_key]
        logger.debug(f"Using cached model for {model_params.get('name', 'unknown')}")
    else:
        # Create and fit new model
        model = _make_prophet_model(model_params)
        model.fit(train_df)
        model_cache[cache_key] = model
        logger.debug(f"Fitted new model for {model_params.get('name', 'unknown')}")
    
    train_end = train_df["ds"].max()
    periods = (forecast_end.year - train_end.year) * 12 + forecast_end.month - train_end.month
    future = model.make_future_dataframe(periods=int(periods), freq="MS")
    if model_params["changepoint_strategy"] in REGRESSOR_STRATEGIES:
        future = add_event_regressors(future)
    return model, model.predict(future)
    
def evaluate_config(name: str, params: dict, changepoint_strategy: str,
                    train_df: pd.DataFrame, test_df: pd.DataFrame,
                    full_df: pd.DataFrame, model_cache: dict = None) -> dict:
    """Evaluate a configuration with validation windows and test set.
    
    Uses model caching to avoid redundant fits for the same configuration.
    """
    if model_cache is None:
        model_cache = {}
    
    model_params = {**params, "name": name, "changepoint_strategy": changepoint_strategy}
    
    # Fit model once for the full test forecast
    model, forecast = _fit_and_forecast(model_params, train_df, test_df["ds"].max(), model_cache)

    validation_window_metrics = []
    for window in VALIDATION_WINDOWS:
        fold_train = full_df[full_df["ds"] <= window["train_end"]].copy()
        fold_validation = full_df[full_df["ds"].between(window["start"], window["end"])].copy()
        # Use the same model cache for validation folds
        _, fold_forecast = _fit_and_forecast(model_params, fold_train, fold_validation["ds"].max(), model_cache)
        fold_prediction = fold_forecast.merge(fold_validation[["ds", "y"]], on="ds", how="inner")
        fold_metrics = compute_metrics(fold_prediction["y"], fold_prediction["yhat"])
        validation_window_metrics.append({"window": window["name"], **fold_metrics})

    validation_metrics = {
        metric: float(np.mean([item[metric] for item in validation_window_metrics]))
        for metric in ("MAE", "MAPE", "RMSE")
    }
    test_pred = forecast.merge(test_df[["ds", "y"]], on="ds", how="inner")
    test_metrics = compute_metrics(test_pred["y"], test_pred["yhat"])
    
    # Dynamically detect outliers in test set for stress testing
    test_actuals = test_pred["y"]
    outlier_values = detect_outliers(test_actuals)
    outlier_dates = test_pred[test_pred["y"].isin(outlier_values)]["ds"].tolist()
    
    if len(outlier_dates) > 0:
        stress_pred = test_pred[test_pred["ds"].isin(outlier_dates)].copy()
        clean_test_pred = test_pred[~test_pred["ds"].isin(outlier_dates)].copy()
        stress_metrics = compute_metrics(stress_pred["y"], stress_pred["yhat"])
        clean_test_metrics = compute_metrics(clean_test_pred["y"], clean_test_pred["yhat"])
    else:
        # If no outliers detected, use the hardcoded stress test dates as fallback
        stress_pred = test_pred[test_pred["ds"].isin(pd.to_datetime(["2026-03-01"]))].copy()
        clean_test_pred = test_pred[~test_pred["ds"].isin(pd.to_datetime(["2026-03-01"]))].copy()
        stress_metrics = compute_metrics(stress_pred["y"], stress_pred["yhat"])
        clean_test_metrics = compute_metrics(clean_test_pred["y"], clean_test_pred["yhat"])
    
    cv_metrics = run_cross_validation(model_params, train_df)

    return {
        "name": name,
        "params": params,
        "changepoint_strategy": changepoint_strategy,
        "validation_window_metrics": validation_window_metrics,
        "validation_metrics": validation_metrics,
        "test_pred": test_pred,
        "test_metrics": test_metrics,
        "stress_pred": stress_pred,
        "stress_metrics": stress_metrics,
        "clean_test_metrics": clean_test_metrics,
        "cv_metrics": cv_metrics,
    }


def hyperparameter_search(train_df: pd.DataFrame, test_df: pd.DataFrame,
                          full_df: pd.DataFrame) -> list[dict]:
    """Select on mean MAPE across rolling windows; report held-out test results.
    
    Uses model caching to avoid redundant fits across configurations.
    """
    logger.info(f"\n{'=' * 60}")
    logger.info("STEP 3-4: Rolling validation & test evaluation")
    logger.info("=" * 60)

    # Create a shared model cache for all configurations
    model_cache = {}
    results = []
    for name, params in CONFIGS.items():
        for cp_name, cp_strategy in CHANGEPPOINT_STRATEGIES.items():
            full_name = f"{name} | cp={cp_name}"
            logger.info(f"  Training {full_name}... ", extra={"end": "", "flush": True})
            result = evaluate_config(
                full_name, params, cp_name, train_df, test_df, full_df, model_cache
            )
            results.append(result)
            window_mapes = ", ".join(
                f"{item['window']}={item['MAPE']:.1f}%"
                for item in result["validation_window_metrics"]
            )
            logger.info(f"Validation avg MAPE={result['validation_metrics']['MAPE']:.1f}% "
                  f"({window_mapes}), Test MAPE={result['test_metrics']['MAPE']:.1f}%, "
                  f"CV MAPE={result['cv_metrics']['cv_mape']:.1f}%")

    best = min(results, key=lambda r: r["validation_metrics"]["MAPE"])
    logger.info(f"\n  Best config: {best['name']} "
          f"(Rolling validation avg MAPE={best['validation_metrics']['MAPE']:.1f}%, "
          f"Test MAPE={best['test_metrics']['MAPE']:.1f}%)")

    headers = ["Config", "Trend/Event Strategy", "CP Scale", "Seas Scale"]
    headers.extend(f"Val {index}" for index, _ in enumerate(VALIDATION_WINDOWS, start=1))
    headers.extend(["Avg Val MAPE", "Test MAPE"])
    rows = []
    for r in results:
        rows.append([
            r["name"],
            r["changepoint_strategy"],
            r["params"]["changepoint_prior_scale"],
            r["params"]["seasonality_prior_scale"],
            *[f"{item['MAPE']:.1f}%" for item in r["validation_window_metrics"]],
            f"{r['validation_metrics']['MAPE']:.1f}%",
            f"{r['test_metrics']['MAPE']:.1f}%",
        ])
    print_table(headers, rows, "Changepoint + Regressor Strategy Comparison")

    return results


# ─── Step 5: Store evaluation artifacts ─────────────────────────────────────

def save_test_evaluation_data(test_pred: pd.DataFrame):
    """Save all test-period actuals and predictions."""
    path = os.path.join(ARTIFACTS_DIR, "test_evaluation_data.csv")
    try:
        test_pred.sort_values("ds").to_csv(path, index=False)
        logger.info(f"  Saved {path}")
    except IOError as e:
        logger.error(f"  ERROR: Failed to save {path}: {e}")
        raise

def save_outlier_analysis(results: list[dict]):
    """Save event-stress metrics separately from aggregate test metrics."""
    rows = []
    for result in results:
        for _, row in result["stress_pred"].iterrows():
            rows.append({
                "config": result["name"],
                "strategy": result["changepoint_strategy"],
                "event_month": row["ds"].strftime("%Y-%m"),
                "actual": row["y"],
                "predicted": row["yhat"],
                "absolute_error": abs(row["y"] - row["yhat"]),
                "absolute_percentage_error": abs(row["y"] - row["yhat"]) / row["y"] * 100 if row["y"] != 0 else float('nan'),
                "test_mape": result["test_metrics"]["MAPE"],
                "clean_test_mape": result["clean_test_metrics"]["MAPE"],
            })
    path = os.path.join(ARTIFACTS_DIR, "test_outlier_analysis.csv")
    try:
        pd.DataFrame(rows).to_csv(path, index=False)
        logger.info(f"  Saved {path}")
    except IOError as e:
        logger.error(f"  ERROR: Failed to save {path}: {e}")
        raise

def _make_config_json(result: dict) -> dict:
    """Extract model configuration from an evaluation result."""
    name = result["name"]
    strategy = result["changepoint_strategy"]
    return {
        "name": name,
        "changepoint_strategy": strategy,
        "growth": result["params"]["growth"],
        "seasonality_mode": "multiplicative" if "multiplicative" in name else "additive",
        "changepoint_prior_scale": result["params"]["changepoint_prior_scale"],
        "seasonality_prior_scale": result["params"]["seasonality_prior_scale"],
        "regressors": EVENT_REGRESSORS if strategy in REGRESSOR_STRATEGIES else [],
    }


def save_best_model_configs(results: list[dict], artifacts_dir: str) -> None:
    """Save configurations for best validation and best test models."""
    best_val = min(results, key=lambda r: r["validation_metrics"]["MAPE"])
    best_test = min(results, key=lambda r: r["test_metrics"]["MAPE"])

    val_config = _make_config_json(best_val)
    val_config_path = os.path.join(artifacts_dir, "best_model_config.json")
    with open(val_config_path, "w") as f:
        json.dump(val_config, f, indent=2)
    logger.info("Saved best validation model config to %s", val_config_path)

    test_config = _make_config_json(best_test)
    test_config_path = os.path.join(artifacts_dir, "best_test_model_config.json")
    with open(test_config_path, "w") as f:
        json.dump(test_config, f, indent=2)
    logger.info("Saved best test model config to %s", test_config_path)






def save_metrics_summary(df: pd.DataFrame, results: list[dict]):
    """Write evaluation metrics and event-stress results to metrics_summary.txt."""
    best = min(results, key=lambda r: r["validation_metrics"]["MAPE"])

    lines = [
        "=" * 60,
        "NYC POTHOLE COMPLAINT FORECAST - METRICS SUMMARY",
        "=" * 60,
        "",
        "Data Summary:",
        f"  Date range: {df['ds'].min().strftime('%Y-%m')} - {df['ds'].max().strftime('%Y-%m')}",
        f"  Total months: {len(df)}",
        f"  Total complaints: {df['y'].sum():,}",
        "  Anomalies handled:",
        "    - Aug 2026: DROPPED (incomplete month)",
        "    - Mar 2026 spike: KEPT (genuine weather event)",
        "    - Apr 2020 dip: KEPT (pandemic structural break)",
        "",
        "All Configurations Comparison:",
        f"  {'Config':<34} {'Strategy':>20} {'CV MAPE':>10} {'Val 1':>8} {'Val 2':>8} {'Avg Val':>9} {'Test':>8}",
        f"  {'-'*34} {'-'*20} {'-'*10} {'-'*8} {'-'*8} {'-'*9} {'-'*8}",
    ]
    for r in sorted(results, key=lambda r: r["validation_metrics"]["MAPE"]):
        marker = " <<" if r["name"] == best["name"] else ""
        window_mapes = [item["MAPE"] for item in r["validation_window_metrics"]]
        lines.append(
            f"  {r['name']:<34} {r['changepoint_strategy']:>20} "
            f"{r['cv_metrics']['cv_mape']:>9.1f}% "
            f"{window_mapes[0]:>7.1f}% {window_mapes[1]:>7.1f}% "
            f"{r['validation_metrics']['MAPE']:>8.1f}%{marker} "
            f"{r['test_metrics']['MAPE']:>7.1f}%"
        )

    lines.extend([
        "",
        f"Winning Configuration: {best['name']}",
        f"  strategy: {best['changepoint_strategy']}",
        f"  changepoint_prior_scale: {best['params']['changepoint_prior_scale']}",
        f"  seasonality_prior_scale: {best['params']['seasonality_prior_scale']}",
        f"  growth: {best['params'].get('growth', 'linear')}",
        "",
        "Rolling Validation Metrics (selection uses average MAPE):",
    ])
    for item in best["validation_window_metrics"]:
        lines.append(
            f"  {item['window']}: MAE={item['MAE']:.0f}, "
            f"MAPE={item['MAPE']:.1f}%, RMSE={item['RMSE']:.0f}"
        )
    lines.extend([
        f"  Average: MAE={best['validation_metrics']['MAE']:.0f}, "
        f"MAPE={best['validation_metrics']['MAPE']:.1f}%, "
        f"RMSE={best['validation_metrics']['RMSE']:.0f}",
        "",
        f"Cross-Validation Metrics ({best['cv_metrics']['num_folds']} folds, 6-month horizon):",
        f"  MAE:  {best['cv_metrics']['cv_mae']:.0f}",
        f"  MAPE: {best['cv_metrics']['cv_mape']:.1f}%",
        f"  RMSE: {best['cv_metrics']['cv_rmse']:.0f}",
        "",
        f"Per-Month Test Comparison ({TEST_START[:7]}-{TEST_END[:7]}):",
        f"  {'Month':<12} {'Actual':>10} {'Predicted':>12} {'Error':>10}",
        f"  {'-'*12} {'-'*10} {'-'*12} {'-'*10}",
    ])

    for _, row in best["test_pred"].sort_values("ds").iterrows():
        month = row["ds"].strftime("%Y-%m")
        actual = int(row["y"])
        pred = round(row["yhat"])
        lines.append(f"  {month:<12} {actual:>10,} {pred:>12,} {actual - pred:>10,}")

    stress = best["stress_metrics"]
    clean = best["clean_test_metrics"]
    
    # Update stress test section to handle dynamic outliers
    if len(best["stress_pred"]) > 0:
        stress_actual = int(best["stress_pred"]["y"].iloc[0]) if len(best["stress_pred"]) > 0 else 0
        stress_predicted = int(best["stress_pred"]["yhat"].iloc[0]) if len(best["stress_pred"]) > 0 else 0
        stress_test_name = "Dynamic Outliers" if len(best["stress_pred"]) > 1 else "March 2026"
        lines.extend([
            "",
            f"Event Stress Test ({stress_test_name}):",
            f"  Actual: {stress_actual:,}",
            f"  Predicted: {stress_predicted:,}",
            f"  Absolute error: {int(stress['MAE']):,}",
            f"  MAPE: {stress['MAPE']:.1f}%",
            f"  Test MAPE excluding outliers: {clean['MAPE']:.1f}%",
        ])
    else:
        lines.extend([
            "",
            "Event Stress Test (No outliers detected):",
            f"  Test MAPE excluding outliers: {clean['MAPE']:.1f}%",
        ])

    lines.extend([
        "",
        "=" * 60,
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
    ])

    text = "\n".join(lines)
    path = os.path.join(ARTIFACTS_DIR, "metrics_summary.txt")
    try:
        with open(path, "w") as f:
            f.write(text)
        logger.info(f"  Saved {path}")
    except IOError as e:
        logger.error(f"  ERROR: Failed to save {path}: {e}")
        raise
    return text

def print_console_summary(df: pd.DataFrame, results: list[dict]):
    """Print the evaluation summary without producing a future forecast."""
    best = min(results, key=lambda r: r["validation_metrics"]["MAPE"])

    logger.info(f"\n{'=' * 60}")
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"\nData: {df['ds'].min().strftime('%Y-%m')} - {df['ds'].max().strftime('%Y-%m')}")
    logger.info(f"  {len(df)} months, {df['y'].sum():,} total complaints")
    logger.info("  Dropped incomplete Aug 2026; kept March 2026 event spike")
    
    # Update stress test reference to be dynamic
    if len(best["stress_pred"]) > 0:
        stress_test_name = "Dynamic Outliers" if len(best["stress_pred"]) > 1 else "March 2026"
        logger.info(f"\nSelected by rolling validation: {best['name']} / {best['changepoint_strategy']}")
        logger.info(f"  Validation MAPE={best['validation_metrics']['MAPE']:.1f}%")
        logger.info(f"  Held-out test MAPE={best['test_metrics']['MAPE']:.1f}%")
        logger.info(f"  Test MAPE excluding outliers={best['clean_test_metrics']['MAPE']:.1f}%")
        logger.info(f"  {stress_test_name} stress MAPE={best['stress_metrics']['MAPE']:.1f}%")
    else:
        logger.info(f"\nSelected by rolling validation: {best['name']} / {best['changepoint_strategy']}")
        logger.info(f"  Validation MAPE={best['validation_metrics']['MAPE']:.1f}%")
        logger.info(f"  Held-out test MAPE={best['test_metrics']['MAPE']:.1f}%")
        logger.info(f"  Test MAPE excluding outliers={best['clean_test_metrics']['MAPE']:.1f}%")
    
    logger.info(f"\nAll artifacts saved to {ARTIFACTS_DIR}/")
    logger.info("=" * 60)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    """Main entry point for the forecast pipeline."""
    try:
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)

        logger.info("Starting NYC pothole forecast pipeline")
        df = load_data()
        train_df, _, test_df = split_data(df)
        results = hyperparameter_search(train_df, test_df, df)
        save_best_model_configs(results, ARTIFACTS_DIR)
        best = min(results, key=lambda r: r["validation_metrics"]["MAPE"])

        logger.info(f"\n{'=' * 60}")
        logger.info("STEP 5: Store evaluation artifacts")
        logger.info("=" * 60)
        save_test_evaluation_data(best["test_pred"])
        save_outlier_analysis(results)
        save_metrics_summary(df, results)
        print_console_summary(df, results)
        
        logger.info("Forecast pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Forecast pipeline failed: {e}")
        raise






if __name__ == "__main__":
    main()

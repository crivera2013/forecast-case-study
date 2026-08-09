#!/usr/bin/env python3
"""Train the selected event-aware model on all data and forecast nine months."""

import argparse
import json
import logging
import os
import pickle

import duckdb
import pandas as pd
from prophet import Prophet

# Try to import joblib, fall back to pickle
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants for column names
DS_COL = "ds"
Y_COL = "y"
YHAT_COL = "yhat"
YHAT_LOWER_COL = "yhat_lower"
YHAT_UPPER_COL = "yhat_upper"

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

# Default configuration - will be overridden if best config is available
DEFAULT_MODEL_CONFIG = {
    "name": "B (multiplicative)",
    "growth": "linear",
    "seasonality_mode": "multiplicative",
    "changepoint_prior_scale": 0.01,
    "seasonality_prior_scale": 100.0,
    "changepoints": KNOWN_CHANGEPOINTS,
    "regressors": ["snowstorm_2015", "covid_period", "march_2026_spike"],
    "mcmc_samples": 300,
}


def parse_args():
    """Parse command-line arguments for configurable paths and parameters."""
    parser = argparse.ArgumentParser(description="Generate 9-month forecast for NYC pothole complaints using Prophet.")
    parser.add_argument("--db-path", default="data/nyc_311_road_surface.duckdb", help="Path to DuckDB database")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Directory to save artifacts")
    parser.add_argument("--forecast-months", type=int, default=9, help="Number of months to forecast")
    parser.add_argument("--cutoff-date", default="2026-08-01", help="Cutoff date for training data (YYYY-MM-DD)")
    parser.add_argument("--no-mcmc", action="store_true", help="Disable MCMC sampling for faster execution")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def load_best_model_config(artifacts_dir: str) -> dict:
    """Load the best model configuration from artifacts or use defaults.
    
    Args:
        artifacts_dir: Directory containing forecast artifacts
        
    Returns:
        Dictionary with model configuration
    """
    config_path = os.path.join(artifacts_dir, "best_model_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
            logger.info(f"Loaded best model config from {config_path}")
            return config
        except OSError as e:
            logger.warning(f"Failed to load best model config: {e}. Using defaults.")
    
    # Fallback to default config
    logger.info("Using default model configuration")
    return DEFAULT_MODEL_CONFIG


def load_data(db_path: str, cutoff_date: str) -> pd.DataFrame:
    """Load complete monthly history, excluding only an incomplete month.
    
    Args:
        db_path: Path to DuckDB database
        cutoff_date: Date string to filter data (YYYY-MM-DD)
        
    Returns:
        DataFrame with ds and y columns
        
    Raises:
        OSError: If database connection or query fails
    """
    try:
        with duckdb.connect(db_path, read_only=True) as connection:
            data = connection.execute(
                """
                SELECT strftime(created_date, '%Y-%m') AS ds, COUNT(*) AS y
                FROM complaints
                WHERE series = 'pothole'
                GROUP BY ds
                ORDER BY ds
                """
            ).fetchdf()
    except Exception as e:
        logger.error(f"Failed to load data from DuckDB: {e}")
        raise

    data[DS_COL] = pd.to_datetime(data[DS_COL])
    data[Y_COL] = data[Y_COL].astype(int)
    
    # Filter data based on cutoff date
    cutoff = pd.to_datetime(cutoff_date)
    filtered_data = data[data[DS_COL] < cutoff].copy()
    
    logger.info(f"Loaded {len(filtered_data)} months of data ({filtered_data[DS_COL].min().strftime('%Y-%m')} to {filtered_data[DS_COL].max().strftime('%Y-%m')})")
    return filtered_data


def add_regressors(data: pd.DataFrame, model_config: dict) -> pd.DataFrame:
    """Add event indicators used by the final model.
    
    Args:
        data: DataFrame with a 'ds' column (datetime)
        model_config: Model configuration containing regressor info
        
    Returns:
        DataFrame with added event regressor columns
        
    Raises:
        ValueError: If 'ds' column is missing
    """
    if DS_COL not in data.columns:
        raise ValueError("DataFrame must have a 'ds' column (datetime).")
    
    enriched = data.copy()
    dates = enriched[DS_COL]
    
    # Add known event regressors
    enriched["snowstorm_2015"] = dates.between(SNOWSTORM_START, SNOWSTORM_END).astype(int)
    enriched["covid_period"] = dates.between(COVID_PERIOD_START, COVID_PERIOD_END).astype(int)
    
    # Add dynamic regressors from model config if available
    regressors = model_config.get("regressors", [])
    for regressor in regressors:
        if regressor not in enriched.columns:
            if regressor == "march_2026_spike":
                # Handle the March 2026 spike specifically
                enriched[regressor] = (dates == pd.to_datetime("2026-03-01")).astype(int)
            else:
                # For other regressors, try to detect them dynamically
                logger.warning(f"Regressor '{regressor}' not found in data and not handled dynamically")
    
    return enriched


def build_model(model_config: dict, use_mcmc: bool = True) -> Prophet:
    """Build the model based on the provided configuration.
    
    Args:
        model_config: Dictionary containing model parameters
        use_mcmc: Whether to use MCMC sampling
        
    Returns:
        Configured Prophet model instance
    """
    changepoints = pd.to_datetime(model_config.get("changepoints", KNOWN_CHANGEPOINTS))
    
    # Use mcmc_samples=0 to disable MCMC for faster execution
    mcmc_samples = model_config.get("mcmc_samples", 300) if use_mcmc else 0
    
    model = Prophet(
        growth=model_config.get("growth", "linear"),
        seasonality_mode=model_config.get("seasonality_mode", "additive"),
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoints=changepoints,
        changepoint_prior_scale=model_config.get("changepoint_prior_scale", 0.01),
        seasonality_prior_scale=model_config.get("seasonality_prior_scale", 100.0),
        interval_width=0.95,
        mcmc_samples=mcmc_samples,
    )
    
    # Add regressors from config
    regressors = model_config.get("regressors", [])
    for regressor in regressors:
        model.add_regressor(regressor, mode="additive")
    
    return model


def make_future(data: pd.DataFrame, forecast_months: int) -> pd.DataFrame:
    """Create the next N monthly dates with known future event values.
    
    Args:
        data: DataFrame with historical data
        forecast_months: Number of months to forecast
        
    Returns:
        DataFrame with future dates
        
    Raises:
        ValueError: If data is empty
    """
    if len(data) == 0:
        raise ValueError("Data is empty. Cannot create future dates.")
    
    start = data[DS_COL].max() + pd.offsets.MonthBegin(1)
    future = pd.DataFrame({
        DS_COL: pd.date_range(start=start, periods=forecast_months, freq="MS")
    })
    
    # Add regressors to future data
    future["snowstorm_2015"] = 0
    future["covid_period"] = 0
    future["march_2026_spike"] = (future[DS_COL] == pd.to_datetime("2026-03-01")).astype(int)
    
    return future


def save_outputs(forecast: pd.DataFrame, data: pd.DataFrame, model: Prophet, 
                 model_config: dict, artifacts_dir: str) -> None:
    """Persist the forecast CSV, model configuration, and fitted model.
    
    Args:
        forecast: DataFrame with forecast results
        data: Original training data
        model: Fitted Prophet model
        model_config: Model configuration
        artifacts_dir: Directory to save artifacts
        
    Raises:
        OSError: If file operations fail
    """
    os.makedirs(artifacts_dir, exist_ok=True)
    
    try:
        # Save forecast data
        future_forecast = forecast[forecast[DS_COL] > data[DS_COL].max()].copy()
        columns = [DS_COL, YHAT_COL, YHAT_LOWER_COL, YHAT_UPPER_COL]
        forecast_path = os.path.join(artifacts_dir, "final_forecast_data.csv")
        future_forecast[columns].to_csv(forecast_path, index=False)
        logger.info(f"Saved {forecast_path}")

        # Save model configuration
        config_path = os.path.join(artifacts_dir, "final_model_config.json")
        with open(config_path, "w") as file:
            json.dump(model_config, file, indent=2)
        logger.info(f"Saved {config_path}")

        # Save fitted model
        model_path = os.path.join(artifacts_dir, "final_model.pkl")
        if HAS_JOBLIB:
            joblib.dump(model, model_path)
        else:
            with open(model_path, "wb") as f:
                pickle.dump(model, f)
        logger.info(f"Saved {model_path}")

        # Print forecast summary
        logger.info("\nForecast:")
        logger.info(future_forecast[columns].to_string(index=False, formatters={
            DS_COL: lambda value: value.strftime("%Y-%m"),
            YHAT_COL: "{:,.0f}".format,
            YHAT_LOWER_COL: "{:,.0f}".format,
            YHAT_UPPER_COL: "{:,.0f}".format,
        }))
        
    except OSError as e:
        logger.error(f"Failed to save outputs: {e}")
        raise


def main() -> None:
    """Main entry point for generating the 9-month forecast.
    
    Loads data, builds the model, fits it, and saves the forecast.
    """
    args = parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("prophet").setLevel(logging.DEBUG)
    
    try:
        logger.info("Starting 9-month forecast generation")
        
        # Load the best model configuration
        model_config = load_best_model_config(args.artifacts_dir)
        
        # Load and prepare data
        data = load_data(args.db_path, args.cutoff_date)
        data_with_regressors = add_regressors(data, model_config)
        
        # Build and fit model
        model = build_model(model_config, use_mcmc=not args.no_mcmc)
        logger.info(f"Training model: {model_config.get('name', 'unknown')}")
        
        # Get the regressor columns that are actually in the data
        available_regressors = [col for col in model_config.get("regressors", []) 
                              if col in data_with_regressors.columns]
        
        model.fit(data_with_regressors[[DS_COL, Y_COL] + available_regressors])
        
        # Generate forecast
        future = make_future(data_with_regressors, args.forecast_months)
        forecast = model.predict(future)
        
        # Save outputs
        save_outputs(forecast, data_with_regressors, model, model_config, args.artifacts_dir)
        
        logger.info("Forecast generation completed successfully")
        
    except Exception as e:
        logger.error(f"Forecast generation failed: {e}")
        raise


if __name__ == "__main__":
    main()
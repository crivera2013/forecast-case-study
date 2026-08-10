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

# Known structural breaks to register as explicit changepoints
KNOWN_CHANGEPOINTS = [
    "2015-01-01",  # Extreme snowstorms
    "2015-02-01",
    "2015-04-01",
    "2020-03-01",  # Pandemic onset
    "2020-04-01",
]

# Default configuration - will be overridden if best config is available
DEFAULT_MODEL_CONFIG = {
    "name": "B (multiplicative)",
    "growth": "linear",
    "seasonality_mode": "multiplicative",
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10.0,
    "mcmc_samples": 2000,
}

# Event regressor definitions: name -> (start_date, end_date)
# Used by both add_regressors and make_future
EVENT_REGRESSORS = {
    "snowstorm_2015": ("2015-01-01", "2015-03-01"),
    "covid_period":   ("2020-03-01", "2021-12-01"),
}


def parse_args():
    """Parse command-line arguments for configurable paths and parameters."""
    parser = argparse.ArgumentParser(description="Generate 9-month forecast for NYC pothole complaints using Prophet.")
    parser.add_argument("--db-path", default="data/nyc_311_road_surface.duckdb", help="Path to DuckDB database")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Directory to save artifacts")
    parser.add_argument("--forecast-months", type=int, default=9, help="Number of months to forecast")
    parser.add_argument("--cutoff-date", default="2026-08-01", help="Cutoff date for training data (YYYY-MM-DD)")
    parser.add_argument("--no-mcmc", action="store_true", help="Disable MCMC sampling for faster execution")
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
            logger.info("Loaded best model config from %s", config_path)
            return config
        except OSError as e:
            logger.warning("Failed to load best model config: %s. Using defaults.", e)

    logger.info("Using default model configuration")
    return DEFAULT_MODEL_CONFIG
def load_best_test_model_config(artifacts_dir: str) -> dict:
    """Load the best test model configuration from artifacts or return None.

    Args:
        artifacts_dir: Directory containing forecast artifacts

    Returns:
        Dictionary with model configuration, or None if not found
    """
    config_path = os.path.join(artifacts_dir, "best_test_model_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
            logger.info("Loaded best test model config from %s", config_path)
            return config
        except OSError as e:
            logger.warning("Failed to load best test model config: %s. Skipping test model forecast.", e)
            return None

    logger.debug("No best test model config found at %s", config_path)
    return None


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
        logger.error("Failed to load data from DuckDB: %s", e)
        raise

    data[DS_COL] = pd.to_datetime(data[DS_COL])
    data[Y_COL] = data[Y_COL].astype(int)

    # Filter data based on cutoff date
    cutoff = pd.to_datetime(cutoff_date)
    filtered_data = data[data[DS_COL] < cutoff].copy()

    logger.info(
        "Loaded %d months of data (%s to %s)",
        len(filtered_data),
        filtered_data[DS_COL].min().strftime("%Y-%m"),
        filtered_data[DS_COL].max().strftime("%Y-%m"),
    )
    return filtered_data


def add_regressors(data: pd.DataFrame, model_config: dict) -> pd.DataFrame:
    """Add event indicators used by the final model.

    Event regressors are defined in EVENT_REGRESSORS (static) or can be
    added dynamically via the model config.

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

    # Add known event regressors from EVENT_REGRESSORS
    for regressor_name, (start, end) in EVENT_REGRESSORS.items():
        enriched[regressor_name] = dates.between(start, end).astype(int)

    # Add dynamic regressors from model config not already present
    for regressor in model_config.get("regressors", []):
        if regressor not in enriched.columns:
            if regressor == "march_2026_spike":
                enriched[regressor] = (
                    dates == pd.to_datetime("2026-03-01")
                ).astype(int)
            else:
                logger.warning("Regressor '%s' not found in data", regressor)

    return enriched


def build_model(model_config: dict, use_mcmc: bool = True) -> Prophet:
    """Build the model based on the provided configuration.

    Args:
        model_config: Dictionary containing model parameters
        use_mcmc: Whether to use MCMC sampling

    Returns:
        Configured Prophet model instance
    """
    changepoints = pd.to_datetime(
        model_config.get("changepoints", KNOWN_CHANGEPOINTS)
    )

    # Use mcmc_samples=0 to disable MCMC for faster execution
    mcmc_samples = (
        model_config.get("mcmc_samples", 300) if use_mcmc else 0
    )

    model = Prophet(
        growth=model_config.get("growth", "linear"),
        seasonality_mode=model_config.get("seasonality_mode", "additive"),
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoints=changepoints,
        changepoint_prior_scale=model_config.get(
            "changepoint_prior_scale", 0.01
        ),
        seasonality_prior_scale=model_config.get(
            "seasonality_prior_scale", 100.0
        ),
        interval_width=0.95,
        mcmc_samples=mcmc_samples,
    )

    # Add regressors from config
    for regressor in model_config.get("regressors", []):
        model.add_regressor(regressor, mode="additive")

    return model


def make_future(data: pd.DataFrame, forecast_months: int) -> pd.DataFrame:
    """Create the next N monthly dates with known future event values.

    Event regressors already passed are set to 0 (they are in the past).
    Dynamic regressors (e.g. march_2026_spike) are evaluated for future dates.

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
        DS_COL: pd.date_range(start=start, periods=forecast_months, freq="MS"),
    })

    # Past events are always 0 in the forecast window
    for regressor_name in EVENT_REGRESSORS:
        future[regressor_name] = 0

    return future


def save_outputs(
    forecast: pd.DataFrame,
    data: pd.DataFrame,
    model: Prophet,
    model_config: dict,
    artifacts_dir: str,
    model_name: str = "final",
) -> None:
    """Persist the forecast CSV, model configuration, and fitted model.

    Args:
        forecast: DataFrame with forecast results
        data: Original training data
        model: Fitted Prophet model
        model_config: Model configuration
        artifacts_dir: Directory to save artifacts
        model_name: Name suffix for outputs (e.g., 'best', 'test')

    Raises:
        OSError: If file operations fail
    """
    os.makedirs(artifacts_dir, exist_ok=True)

    try:
        # Save forecast data
        future_forecast = forecast[forecast[DS_COL] > data[DS_COL].max()].copy()
        columns = [DS_COL, YHAT_COL, YHAT_LOWER_COL, YHAT_UPPER_COL]
        forecast_path = os.path.join(artifacts_dir, f"{model_name}_forecast_data.csv")
        future_forecast[columns].to_csv(forecast_path, index=False)
        logger.info("Saved %s", forecast_path)

        # Save model configuration
        config_path = os.path.join(artifacts_dir, f"{model_name}_model_config.json")
        with open(config_path, "w") as file:
            json.dump(model_config, file, indent=2)
        logger.info("Saved %s", config_path)

        # Save fitted model (pickle; joblib is unreliable with Prophet)
        model_path = os.path.join(artifacts_dir, f"{model_name}_model.pkl")
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        logger.info("Saved %s", model_path)

        # Print forecast summary
        logger.info(
            "\nForecast (%s):", model_name
        )
        logger.info(
            future_forecast[columns].to_string(
                index=False,
                formatters={
                    DS_COL: lambda value: value.strftime("%Y-%m"),
                    YHAT_COL: "{:,.0f}".format,
                    YHAT_LOWER_COL: "{:,.0f}".format,
                    YHAT_UPPER_COL: "{:,.0f}".format,
                },
            )
        )

    except OSError as e:
        logger.error("Failed to save outputs: %s", e)
        raise


def main() -> None:
    """Main entry point for generating the 9-month forecast.

    Loads data, builds the model, fits it, and saves the forecast for both
    the best model config and the best test model config.
    """
    args = parse_args()

    try:
        logger.info("Starting 9-month forecast generation")

        # Load the best model configurations
        model_config = load_best_model_config(args.artifacts_dir)
        test_model_config = load_best_test_model_config(args.artifacts_dir)

        # Load and prepare data (same for both models)
        data = load_data(args.db_path, args.cutoff_date)
        data_with_regressors = add_regressors(data, model_config)

        # Build and fit model for best config
        logger.info("Training best model")
        model = build_model(model_config, use_mcmc=not args.no_mcmc)
        logger.info("Training model: %s", model_config.get("name", "unknown"))

        # Get the regressor columns that are actually in the data
        available_regressors = [
            col
            for col in model_config.get("regressors", [])
            if col in data_with_regressors.columns
        ]

        model.fit(data_with_regressors[[DS_COL, Y_COL] + available_regressors])

        # Generate forecast for best model
        future = make_future(data_with_regressors, args.forecast_months)
        forecast = model.predict(future)

        # Save outputs for best model
        save_outputs(
            forecast, data_with_regressors, model, model_config, args.artifacts_dir, "best"
        )

        # If test model config exists, train and save forecast for it too
        if test_model_config:
            logger.info("\nTraining best test model")
            test_model = build_model(test_model_config, use_mcmc=not args.no_mcmc)
            logger.info(
                "Training test model: %s", test_model_config.get("name", "unknown")
            )

            # Get available regressors for test model
            test_available_regressors = [
                col
                for col in test_model_config.get("regressors", [])
                if col in data_with_regressors.columns
            ]

            test_model.fit(
                data_with_regressors[[DS_COL, Y_COL] + test_available_regressors]
            )

            # Generate forecast for test model
            test_forecast = test_model.predict(future)

            # Save outputs for test model
            save_outputs(
                test_forecast,
                data_with_regressors,
                test_model,
                test_model_config,
                args.artifacts_dir,
                "test",
            )
        else:
            logger.info("\nNo best test model config found. Skipping test model forecast.")

        logger.info("\nForecast generation completed successfully")

    except Exception as e:
        logger.error("Forecast generation failed: %s", e)
        raise


if __name__ == "__main__":
    main()

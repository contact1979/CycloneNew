# /feature_engineering/feature_generator.py

import logging
import pandas as pd
import numpy as np
from sqlalchemy.sql import select, and_, or_, text
import datetime
import pytz
from typing import List, Dict, Optional

# Use absolute imports assuming 'cyclonev2' is the project root added to PYTHONPATH
# Import HydroBot packages
from hydrobot import config
from hydrobot.database import db_utils  # Import the db_utils module to access table objects and engine
from hydrobot.database.db_utils import fetch_table_data
# from .. import config # Use relative import if running as part of a package
# from ..database import db_utils

log = logging.getLogger(__name__)

# --- Constants ---
# Define feature calculation parameters (can also be moved to config if needed)
PRICE_LAG_PERIODS = config.FEATURE_LAG_PERIODS # e.g., 20
ROLLING_WINDOWS = ['1h', '4h', '12h', '24h'] # Pandas offset strings for rolling stats
SENTIMENT_WINDOWS = [config.SENTIMENT_AGG_WINDOW_SHORT, config.SENTIMENT_AGG_WINDOW_LONG] # e.g., ['1h', '24h']
PREDICTION_HORIZON = config.PREDICTION_HORIZON_PERIODS # e.g., 3 periods (15 mins for 5m interval)

# --- Helper Functions ---

def _calculate_rolling_sentiment(sentiment_df: pd.DataFrame, price_timestamps: pd.Series, window: str) -> pd.DataFrame:
    """Calculates rolling average sentiment scores aligned with price timestamps."""
    if sentiment_df.empty:
        # Return DataFrame with expected columns but all NaNs
        return pd.DataFrame(index=price_timestamps, columns=[f'sent_avg_{window}', f'sent_count_{window}']).rename_axis('open_time')

    # Ensure sentiment_df index is datetime
    if not pd.api.types.is_datetime64_any_dtype(sentiment_df.index):
         log.warning(f"Sentiment DataFrame index is not datetime for window {window}. Attempting conversion.")
         try:
             # Ensure the index is timezone-aware UTC before proceeding
             if sentiment_df.index.tz is None:
                 sentiment_df.index = pd.to_datetime(sentiment_df.index).tz_localize(pytz.utc)
             else:
                 sentiment_df.index = pd.to_datetime(sentiment_df.index, utc=True).tz_convert(pytz.utc)
         except Exception as e:
             log.error(f"Failed to convert sentiment index to datetime: {e}")
             return pd.DataFrame(index=price_timestamps, columns=[f'sent_avg_{window}', f'sent_count_{window}']).rename_axis('open_time')

    # Ensure price_timestamps is sorted and timezone-aware UTC
    price_timestamps = price_timestamps.sort_index()
    if price_timestamps.tz is None:
         price_timestamps = price_timestamps.tz_localize(pytz.utc)
    elif price_timestamps.tz != pytz.utc:
         price_timestamps = price_timestamps.tz_convert(pytz.utc)


    # Calculate rolling mean and count - align results to the *right* edge of the window
    # closed='left' means the interval is [start, end) - includes start, excludes end
    rolling_avg = sentiment_df['sentiment_score'].rolling(window, closed='left').mean()
    rolling_count = sentiment_df['sentiment_score'].rolling(window, closed='left').count()

    # Combine and rename
    rolling_sentiment = pd.DataFrame({
        f'sent_avg_{window}': rolling_avg,
        f'sent_count_{window}': rolling_count
    }, index=sentiment_df.index)

    # Reindex to match the exact price timestamps using forward fill
    # This ensures each price point has the latest available rolling sentiment calculated *before* its open_time
    # Need to ensure both indexes are timezone aware (UTC) before reindexing
    aligned_sentiment = rolling_sentiment.reindex(price_timestamps, method='ffill')

    log.debug(f"Calculated rolling sentiment for window: {window}. Shape: {aligned_sentiment.shape}")
    return aligned_sentiment


def _calculate_target(price_df: pd.DataFrame, periods: int) -> pd.Series:
    """
    Calculates the target variable: 1 if price increased N periods later, 0 otherwise.

    Args:
        price_df (pd.DataFrame): DataFrame with 'close' prices, indexed by time.
        periods (int): Number of periods ahead to look for price increase.

    Returns:
        pd.Series: Series with target variable (1 or 0), indexed by time.
                   NaN where future price is not available.
    """
    future_close = price_df['close'].shift(-periods)
    target = (future_close > price_df['close']).astype(float) # Use float 1.0 / 0.0, NaN where future unknown
    target.name = f'target_up_{periods}p'
    # Where future_close is NaN (at the end of the series), target will be NaN
    log.debug(f"Calculated target variable for {periods} periods ahead.")
    return target

# --- Main Feature Generation Function ---

def generate_features_for_symbol(symbol: str, end_time_utc: datetime.datetime, history_duration: pd.Timedelta = pd.Timedelta(days=30)) -> Optional[pd.DataFrame]:
    """
    Generates features for a given symbol up to a specified end time.

    Args:
        symbol (str): The cryptocurrency symbol (e.g., 'BTCUSDT').
        end_time_utc (datetime.datetime): The timestamp up to which features are needed
                                           (timezone-aware UTC). Should align with a candle close time.
        history_duration (pd.Timedelta): How far back to fetch raw data for calculating
                                         lags and rolling features.

    Returns:
        Optional[pd.DataFrame]: A DataFrame containing features and potentially the target variable.
                                Returns None if data fetching or processing fails.
                                Index is 'open_time', Columns include features and 'target_*'.
    """
    if not end_time_utc.tzinfo or end_time_utc.tzinfo.utcoffset(end_time_utc) != datetime.timedelta(0):
        log.error("end_time_utc must be timezone-aware UTC.")
        return None
    if db_utils.engine is None:
         log.error("Feature Generation: DB engine not configured.")
         return None

    start_time_utc = end_time_utc - history_duration
    interval = '5m' # Assuming 5-minute interval based on config fetch interval

    log.info(f"Generating features for {symbol} from {start_time_utc} to {end_time_utc}")

    # --- 1. Fetch Raw Data ---
    price_df = None
    sentiment_df = None
    try:
        # Use the engine directly for pd.read_sql when passing SQLAlchemy selectables
        engine = db_utils.engine # Get the engine instance

        # Fetch Price Data
        price_query = select(db_utils.price_data).where(
            db_utils.price_data.c.symbol == symbol,
            db_utils.price_data.c.interval == interval,
            db_utils.price_data.c.open_time >= start_time_utc,
            db_utils.price_data.c.open_time <= end_time_utc # Include end time candle
        ).order_by(db_utils.price_data.c.open_time)
        # *** FIX: Pass engine, not session, to pd.read_sql ***
        price_df = pd.read_sql(price_query, engine, index_col='open_time', parse_dates=['open_time'])
        if price_df.empty:
            log.warning(f"No price data found for {symbol} in the specified range.")
            # Still return None here, as features cannot be generated without price data
            return None
        # Ensure index is timezone-aware UTC
        if price_df.index.tz is None:
            price_df.index = price_df.index.tz_localize(pytz.utc)
        else:
            price_df.index = price_df.index.tz_convert(pytz.utc)
        log.info(f"Fetched {len(price_df)} price data points for {symbol}.")

        # Fetch Sentiment Data (combine all sources for simplicity here)
        sentiment_query = select(
            db_utils.sentiment_analysis_results.c.analyzed_at,
            db_utils.sentiment_analysis_results.c.sentiment_score
            # TODO: Filter sentiment by symbol (requires joins/schema changes)
        ).where(
            db_utils.sentiment_analysis_results.c.analyzed_at >= start_time_utc,
            db_utils.sentiment_analysis_results.c.analyzed_at <= end_time_utc
        ).order_by(db_utils.sentiment_analysis_results.c.analyzed_at)
        # *** FIX: Pass engine, not session, to pd.read_sql ***
        sentiment_df = pd.read_sql(sentiment_query, engine, index_col='analyzed_at', parse_dates=['analyzed_at'])
         # Ensure index is timezone-aware UTC
        if not sentiment_df.empty and sentiment_df.index.tz is None:
            sentiment_df.index = sentiment_df.index.tz_localize(pytz.utc)
        elif not sentiment_df.empty:
            sentiment_df.index = sentiment_df.index.tz_convert(pytz.utc)
        log.info(f"Fetched {len(sentiment_df)} sentiment data points (all symbols).") # Note: All symbols

    except Exception as e:
        log.error(f"Database error fetching data for {symbol}: {e}", exc_info=True)
        return None

    # --- 2. Feature Calculation ---
    # Ensure price_df is not None before proceeding
    if price_df is None or price_df.empty:
         log.error(f"Cannot calculate features for {symbol} due to missing price data.")
         return None

    features = pd.DataFrame(index=price_df.index)
    features['symbol'] = symbol # Add symbol identifier

    # a) Price/Volume Lags & Returns
    log.debug("Calculating price/volume features...")
    for lag in range(1, PRICE_LAG_PERIODS + 1):
        features[f'lag_close_{lag}'] = price_df['close'].shift(lag)
        features[f'lag_volume_{lag}'] = price_df['volume'].shift(lag)
        features[f'return_{lag}'] = price_df['close'].pct_change(periods=lag)

    # b) Rolling Price/Volume Statistics
    for window in ROLLING_WINDOWS:
        # closed='left' ensures data up to (but not including) the current candle is used
        features[f'roll_avg_close_{window}'] = price_df['close'].rolling(window, closed='left').mean()
        features[f'roll_std_close_{window}'] = price_df['close'].rolling(window, closed='left').std()
        features[f'roll_avg_vol_{window}'] = price_df['volume'].rolling(window, closed='left').mean()

    # c) Technical Indicators (already fetched, just use them)
    log.debug("Adding technical indicator features...")
    indicator_cols = ['sma_fast', 'sma_slow', 'ema_fast', 'ema_slow', 'rsi_value', 'macd_line', 'macd_signal', 'macd_hist']
    for col in indicator_cols:
        if col in price_df.columns:
            features[col] = price_df[col]
            # Create diff/cross features only if both components exist
            if col == 'sma_slow' and 'sma_fast' in features.columns: features['sma_diff'] = features['sma_fast'] - features['sma_slow']
            if col == 'ema_slow' and 'ema_fast' in features.columns: features['ema_diff'] = features['ema_fast'] - features['ema_slow']
            if col == 'macd_signal' and 'macd_line' in features.columns: features['macd_diff'] = features['macd_line'] - features['macd_signal']

    # d) Rolling Sentiment Features
    log.debug("Calculating rolling sentiment features...")
    if sentiment_df is not None and not sentiment_df.empty: # Check if sentiment_df exists
         # Ensure sentiment_df index is unique if duplicates exist (e.g., keep last)
         sentiment_df = sentiment_df[~sentiment_df.index.duplicated(keep='last')]
         for window in SENTIMENT_WINDOWS:
             rolling_sent = _calculate_rolling_sentiment(sentiment_df.copy(), features.index, window) # Pass copy
             features = pd.concat([features, rolling_sent], axis=1)
    else:
         # Add NaN columns if no sentiment data
         log.warning("No sentiment data found for feature calculation.")
         for window in SENTIMENT_WINDOWS:
             features[f'sent_avg_{window}'] = np.nan
             features[f'sent_count_{window}'] = np.nan


    # e) Time-based Features
    log.debug("Calculating time-based features...")
    features['hour'] = features.index.hour
    features['dayofweek'] = features.index.dayofweek # Monday=0, Sunday=6
    features['minute'] = features.index.minute # Might be useful for 5m interval
    # Cyclical features
    features['hour_sin'] = np.sin(2 * np.pi * features['hour'] / 24)
    features['hour_cos'] = np.cos(2 * np.pi * features['hour'] / 24)
    features['day_sin'] = np.sin(2 * np.pi * features['dayofweek'] / 7)
    features['day_cos'] = np.cos(2 * np.pi * features['dayofweek'] / 7)

    # --- 3. Calculate Target Variable ---
    log.debug("Calculating target variable...")
    target = _calculate_target(price_df, periods=PREDICTION_HORIZON)
    features = pd.concat([features, target], axis=1)

    # --- 4. Cleanup ---
    # Drop initial rows with NaNs created by lags/rolling features/target
    # Ensure target column name is correctly referenced
    target_col_name = f'target_up_{PREDICTION_HORIZON}p'
    min_required_periods = PRICE_LAG_PERIODS # Minimum needed for lags
    # Also consider longest rolling window, adjust drop logic if needed
    initial_len = len(features)
    # Drop rows where longest lag OR target is NaN
    features.dropna(subset=[f'lag_close_{PRICE_LAG_PERIODS}', target_col_name], inplace=True)
    final_len = len(features)
    log.info(f"Feature generation complete for {symbol}. Shape: {features.shape}. Dropped {initial_len - final_len} initial/final rows with NaNs.")

    # Optional: Fill remaining NaNs in features if any (e.g., std dev on flat data, initial sentiment NaNs)
    # Check for any remaining NaNs before filling
    if features.isnull().values.any():
         nan_cols = features.columns[features.isnull().any()].tolist()
         log.warning(f"Features still contain NaNs after initial drop: {nan_cols}. Imputing with 0.")
         features.fillna(0, inplace=True) # Or use more sophisticated imputation

    return features


def preprocess_backfill_data():
    """
    Preprocesses backfill data from the database for training.

    Returns:
        pd.DataFrame: Preprocessed data ready for training.
    """
    # Fetch data from relevant tables
    reddit_data = fetch_table_data("reddit_data")
    twitter_data = fetch_table_data("twitter_data")

    if reddit_data.empty and twitter_data.empty:
        raise ValueError("No data available in the database for preprocessing.")

    # Example preprocessing steps (customize as needed):
    # Combine data from multiple sources
    combined_data = pd.concat([reddit_data, twitter_data], ignore_index=True)

    # Drop unnecessary columns
    combined_data = combined_data.drop(columns=["id", "fetched_at"], errors="ignore")

    # Handle missing values
    combined_data = combined_data.fillna("unknown")

    # Add any additional feature engineering steps here

    return combined_data


# --- Example Usage (for testing) ---
if __name__ == '__main__':
    # Setup basic logging for direct script run
    logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s [%(name)s:%(lineno)d] %(message)s')

    print("--- Testing Feature Generator ---")
    # Note: This test requires data to be present in the database.
    # Ensure data collection has run first.

    test_symbol = 'BTCUSDT' # Use a symbol likely to have data
    # Use a recent end time, assuming data exists up to now
    end_time = datetime.datetime.now(pytz.utc)
    # Fetch last 7 days for feature calculation example
    history = pd.Timedelta(days=7)

    print(f"Generating features for {test_symbol} up to {end_time} with {history} history...")

    # Ensure DB is initialized (if running standalone)
    # db_utils.init_db() # Uncomment if needed, ensure config is correct

    features_df = generate_features_for_symbol(test_symbol, end_time, history_duration=history)

    if features_df is not None and not features_df.empty:
        print(f"\nSuccessfully generated features DataFrame. Shape: {features_df.shape}")
        print("\nColumns:")
        print(features_df.columns.tolist())
        print("\nFeatures DataFrame (last 5 rows):")
        print(features_df.tail())
        target_col_name = f'target_up_{config.PREDICTION_HORIZON_PERIODS}p'
        print(f"\nTarget variable ('{target_col_name}') distribution:")
        print(features_df[target_col_name].value_counts(dropna=False))
        print("\nInfo:")
        features_df.info()
        # Check for any remaining NaNs
        if features_df.isnull().values.any():
             print("\nWarning: NaNs detected in final feature DataFrame!")
             print(features_df.isnull().sum())
        else:
             print("\nNo NaNs detected in final feature DataFrame.")

    elif features_df is not None and features_df.empty:
         print(f"\nFeature generation ran but resulted in an empty DataFrame (possibly due to NaNs or insufficient history).")
    else:
        print(f"\nFailed to generate features for {test_symbol}. Check logs and database connection/data.")

    print("\n--- Test Complete ---")

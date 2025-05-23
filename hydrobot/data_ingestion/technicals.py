"""Technical indicator calculation module.

Provides functions for calculating technical indicators from OHLCV data
using pandas_ta. Indicators are configurable through central settings.
"""

import pandas as pd
import pandas_ta as ta

from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical indicators using pandas_ta and appends them to the DataFrame.

    Args:
        df (pd.DataFrame): DataFrame with OHLCV data. Must contain columns named
                           'open', 'high', 'low', 'close', 'volume' (case-insensitive).

    Returns:
        pd.DataFrame: Original DataFrame with appended indicator columns, or the
                      original DataFrame if calculation fails or df is empty.
    """
    if df.empty:
        logger.warning("Input DataFrame is empty, skipping indicator calculation.")
        return df

    # Ensure required columns exist (case-insensitive check)
    required_cols = ["open", "high", "low", "close", "volume"]
    df_cols_lower = [col.lower() for col in df.columns]
    if not all(col in df_cols_lower for col in required_cols):
        logger.error(
            f"Input DataFrame missing required columns ({required_cols}). Found: {df.columns}"
        )
        return df

    # Standardize column names to lowercase for pandas_ta compatibility
    df.columns = df.columns.str.lower()

    logger.debug(f"Calculating indicators for DataFrame with {len(df)} rows...")

    try:
        # Get indicator settings from central configuration
        ind_settings = settings.indicators

        # Create a custom strategy for pandas_ta using settings
        custom_strategy = ta.Strategy(
            name="HFT Indicators",
            description="SMA, EMA, RSI, MACD based on settings",
            ta=[
                {"kind": "sma", "length": ind_settings.sma.fast_period},
                {"kind": "sma", "length": ind_settings.sma.slow_period},
                {"kind": "ema", "length": ind_settings.ema.fast_period},
                {"kind": "ema", "length": ind_settings.ema.slow_period},
                {"kind": "rsi", "length": ind_settings.rsi.period},
                {
                    "kind": "macd",
                    "fast": ind_settings.macd.fast_period,
                    "slow": ind_settings.macd.slow_period,
                    "signal": ind_settings.macd.signal_period,
                },
            ],
        )

        # Apply the strategy to the DataFrame
        df.ta.strategy(custom_strategy)

        # --- Rename columns for consistency with planned schema ---
        rename_map = {
            f"sma_{ind_settings.sma.fast_period}": "sma_fast",
            f"sma_{ind_settings.sma.slow_period}": "sma_slow",
            f"ema_{ind_settings.ema.fast_period}": "ema_fast",
            f"ema_{ind_settings.ema.slow_period}": "ema_slow",
            f"rsi_{ind_settings.rsi.period}": "rsi_value",
            f"macd_{ind_settings.macd.fast_period}_{ind_settings.macd.slow_period}_{ind_settings.macd.signal_period}": "macd_line",
            f"macdh_{ind_settings.macd.fast_period}_{ind_settings.macd.slow_period}_{ind_settings.macd.signal_period}": "macd_hist",
            f"macds_{ind_settings.macd.fast_period}_{ind_settings.macd.slow_period}_{ind_settings.macd.signal_period}": "macd_signal",
        }
        # Only rename columns that actually exist after calculation
        existing_cols = df.columns
        effective_rename_map = {
            old: new for old, new in rename_map.items() if old in existing_cols
        }
        df.rename(columns=effective_rename_map, inplace=True)

        logger.debug(f"Successfully calculated indicators. DataFrame shape: {df.shape}")

    except Exception as e:
        logger.error(
            "Error calculating technical indicators", error=str(e), data_shape=df.shape
        )

    return df


# --- Example Usage (for testing) ---
if __name__ == "__main__":
    from hydrobot.utils.logger_setup import setup_logging

    # Setup logging using settings
    setup_logging(settings.log_level)

    print("--- Testing Technical Indicator Calculation ---")

    # Create a sample DataFrame (replace with actual data fetching if needed)
    data = {
        "Open": [100, 101, 102, 101, 103, 104, 105, 106, 105, 107] * 3,
        "High": [102, 103, 103, 102, 104, 105, 106, 107, 106, 108] * 3,
        "Low": [99, 100, 101, 100, 102, 103, 104, 105, 104, 106] * 3,
        "Close": [101, 102, 101, 101, 104, 105, 106, 105, 106, 107] * 3,
        "Volume": [1000, 1200, 1100, 1300, 1400, 1500, 1600, 1700, 1550, 1800] * 3,
    }
    # Need enough data points for indicators to calculate, hence * 3
    sample_df = pd.DataFrame(data)
    # Ensure columns are uppercase initially to test case insensitivity
    sample_df.columns = ["Open", "High", "Low", "Close", "Volume"]

    print(f"\nSample DataFrame (first 5 rows):\n{sample_df.head()}")

    # Calculate indicators
    df_with_indicators = calculate_indicators(sample_df.copy())  # Pass a copy

    if not df_with_indicators.empty and any(
        col in df_with_indicators.columns
        for col in ["sma_fast", "rsi_value", "macd_line"]
    ):
        print(
            f"\nDataFrame with indicators (first 5 rows):\n{df_with_indicators.head()}"
        )
        print("\nColumns added:")
        added_cols = [
            col for col in df_with_indicators.columns if col not in sample_df.columns
        ]
        print(added_cols)
        print("\nDataFrame Info:")
        df_with_indicators.info()
    else:
        print("\nFailed to calculate indicators or no indicator columns found.")

    print("\n--- Test Complete ---")

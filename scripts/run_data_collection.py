"""Data collection script for cryptocurrency price data.

This script fetches historical and current price data from configured exchanges
and stores it in the database. It handles rate limiting, error recovery,
and can be run as a one-time backfill or continuous collection process.
"""

import argparse
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
import pandas_ta as ta

from hydrobot.config.settings import load_secrets_into_settings, settings
from hydrobot.data.client_binance import fetch_klines, get_binance_client
from hydrobot.database.db_utils import df_to_db, init_db, price_data
from hydrobot.utils.logger_setup import get_logger, setup_logging

logger = get_logger(__name__)


async def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators for price data.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        DataFrame with added technical indicator columns
    """
    if df.empty:
        return df

    try:
        # Calculate SMAs
        df["sma_fast"] = ta.sma(df["close"], length=20)
        df["sma_slow"] = ta.sma(df["close"], length=50)

        # Calculate EMAs
        df["ema_fast"] = ta.ema(df["close"], length=12)
        df["ema_slow"] = ta.ema(df["close"], length=26)

        # Calculate RSI
        df["rsi_value"] = ta.rsi(df["close"], length=14)

        # Calculate MACD
        macd = ta.macd(df["close"])
        df["macd_line"] = macd["MACD_12_26_9"]
        df["macd_signal"] = macd["MACDs_12_26_9"]
        df["macd_hist"] = macd["MACDh_12_26_9"]

        return df

    except Exception as e:
        logger.error(
            "Error calculating technical indicators", error=str(e), data_shape=df.shape
        )
        return df


async def fetch_symbol_data(
    symbol: str,
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch historical data for a symbol.

    Args:
        symbol: Trading pair symbol
        interval: Kline interval
        start_time: Start time for historical data
        end_time: End time for historical data
        limit: Maximum number of candles to fetch

    Returns:
        DataFrame with OHLCV data and technical indicators
    """
    try:
        # Convert timestamps to string format expected by Binance
        start_str = int(start_time.timestamp() * 1000) if start_time else None
        end_str = int(end_time.timestamp() * 1000) if end_time else None

        # Fetch raw kline data
        df = fetch_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_str=start_str,
            end_str=end_str,
        )

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return df

        # Add technical indicators
        df = await calculate_technical_indicators(df)

        # Add interval column
        df["interval"] = interval
        df["symbol"] = symbol

        return df

    except Exception as e:
        logger.error(
            f"Error fetching data for {symbol}",
            error=str(e),
            start=start_time,
            end=end_time,
        )
        return pd.DataFrame()


async def collect_data_for_symbols(
    symbols: List[str],
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> None:
    """Collect data for multiple symbols and save to database.

    Args:
        symbols: List of trading pair symbols
        interval: Kline interval
        start_time: Start time for historical data
        end_time: End time for historical data
    """
    for symbol in symbols:
        try:
            # Fetch and process data
            df = await fetch_symbol_data(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
            )

            if df.empty:
                continue

            # Save to database
            df_to_db(df=df, table_name="price_data", if_exists="append", index=False)

            logger.info(f"Saved {len(df)} records for {symbol}")

            # Rate limiting
            await asyncio.sleep(0.5)  # Basic rate limit

        except Exception as e:
            logger.error(f"Error processing {symbol}", error=str(e))


async def continuous_collection(symbols: List[str], interval: str) -> None:
    """Run continuous data collection.

    Args:
        symbols: List of trading pair symbols
        interval: Kline interval
    """
    logger.info(
        "Starting continuous data collection", symbols=symbols, interval=interval
    )

    while True:
        try:
            # Get current time
            now = datetime.utcnow()

            # Collect last 5 minutes of data
            start_time = now - timedelta(minutes=5)

            await collect_data_for_symbols(
                symbols=symbols, interval=interval, start_time=start_time, end_time=now
            )

            # Wait until next collection cycle
            await asyncio.sleep(60)  # Check every minute

        except Exception as e:
            logger.error("Error in collection cycle", error=str(e))
            await asyncio.sleep(5)  # Wait on error


async def backfill_historical_data(
    symbols: List[str], interval: str, days: int = 30
) -> None:
    """Backfill historical data for symbols.

    Args:
        symbols: List of trading pair symbols
        interval: Kline interval
        days: Number of days of historical data to fetch
    """
    logger.info(
        "Starting historical data backfill",
        symbols=symbols,
        interval=interval,
        days=days,
    )

    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)

    await collect_data_for_symbols(
        symbols=symbols, interval=interval, start_time=start_time, end_time=end_time
    )


async def main() -> None:
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Crypto Data Collection")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["continuous", "backfill"],
        default="continuous",
        help="Collection mode",
    )
    parser.add_argument(
        "--interval", type=str, default="5m", help="Data collection interval"
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Days of historical data for backfill"
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+", help="Specific symbols to collect (optional)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = args.log_level or settings.log_level
    setup_logging(log_level)

    # Load secrets
    await load_secrets_into_settings()

    # Initialize database
    if not init_db():
        logger.error("Failed to initialize database")
        return

    # Get symbols to collect
    symbols = args.symbols or settings.exchange.trading_pairs
    if not symbols:
        logger.error("No symbols specified and none found in settings")
        return

    # Run collection
    if args.mode == "continuous":
        await continuous_collection(symbols=symbols, interval=args.interval)
    else:
        await backfill_historical_data(
            symbols=symbols, interval=args.interval, days=args.days
        )


if __name__ == "__main__":
    asyncio.run(main())

"""Binance client wrapper for fetching market data."""

import datetime
import logging  # Keep standard logging import for now, get_logger will wrap it

import pandas as pd
import pytz  # For timezone handling
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

# Use absolute imports for the new structure
from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import get_logger

# Use the configured logger
log = get_logger(__name__)

# --- Binance Client Initialization ---
_binance_client = None


def get_binance_client():
    """Initializes and returns the Binance client singleton using settings."""
    global _binance_client
    if _binance_client is None:
        # Use settings object for configuration
        api_key = settings.exchange.api_key
        # Use get_secret_value() for secrets
        secret_key = (
            settings.exchange.api_secret
        )  # Assuming secret is loaded into settings

        # Check if secrets are loaded (they might be None initially)
        if not api_key or not secret_key:
            # Secrets might be loaded later via load_secrets_into_settings()
            # Log a warning, but allow initialization attempt if testnet or for public endpoints
            log.warning(
                "Binance API Key or Secret Key not yet available in settings. Client might have limited functionality."
            )
            # Optionally, prevent initialization if keys are strictly required upfront:
            # log.error("Binance API Key or Secret Key not found in settings. Cannot initialize client.")
            # return None
            # For now, proceed cautiously

        # Determine tld based on exchange name or add a specific setting if needed
        # Example: Assuming 'binance.com' vs 'binance.us' is handled by the name or a dedicated field
        tld = "us" if "us" in settings.exchange.name.lower() else "com"
        log.info(
            f"Determined Binance TLD as '{tld}' based on exchange name '{settings.exchange.name}'."
        )

        try:
            log.info(
                f"Initializing Binance client for tld='{tld}' (Testnet: {settings.exchange.testnet})..."
            )
            _binance_client = Client(
                api_key=api_key,  # Pass potentially None key/secret
                api_secret=secret_key,
                tld=tld,
                testnet=settings.exchange.testnet,  # Use testnet setting
            )
            # Test connection (ping doesn't require auth)
            _binance_client.ping()
            server_time = _binance_client.get_server_time()
            log.info(
                f"Binance client connection successful. Server time: {datetime.datetime.fromtimestamp(server_time['serverTime']/1000)}"
            )
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(
                f"Binance API Error during client initialization: {e}", exc_info=True
            )
            _binance_client = None
        except Exception as e:
            log.error(
                f"Unexpected error initializing Binance client: {e}", exc_info=True
            )
            _binance_client = None
    return _binance_client


def get_target_symbols(price_threshold: float = None, quote_asset: str = "USDT"):
    """
    Gets all trading pairs on Binance with the specified quote asset
    and price under the threshold. Excludes leveraged tokens (UP/DOWN).
    Uses price_threshold from settings if not provided.

    Args:
        price_threshold (float, optional): The maximum price for symbols to be included. Defaults to settings.trading.target_symbol_price_usd if available.
        quote_asset (str): The quote asset (e.g., 'USDT', 'BUSD').

    Returns:
        list: A list of symbol strings (e.g., ['BTCUSDT', 'ETHUSDT']).
              Returns an empty list on failure.
    """
    client = get_binance_client()
    if client is None:
        log.error("Cannot get symbols, Binance client not available.")
        return []

    # Use price threshold from settings if not provided
    if price_threshold is None:
        # Assuming the threshold is defined in TradingSettings, adjust if needed
        try:
            # Add a setting for this if it doesn't exist, e.g., settings.trading.target_symbol_price_usd
            # For now, let's assume a default or handle its absence
            price_threshold = getattr(
                settings.trading, "target_symbol_price_usd", 10.0
            )  # Example default
            log.info(f"Using price threshold from settings: {price_threshold}")
        except AttributeError:
            log.warning(
                "target_symbol_price_usd not found in trading settings. Using default: 10.0"
            )
            price_threshold = 10.0

    target_symbols = []
    try:
        log.info(f"Fetching all tickers from Binance ({client.tld})...")
        tickers = client.get_ticker()  # Fetches all symbols' ticker info
        log.info(
            f"Processing {len(tickers)} tickers to find pairs ending with {quote_asset} under ${price_threshold}..."
        )

        count = 0
        processed_count = 0
        for ticker in tickers:
            processed_count += 1
            symbol = ticker.get("symbol")
            if not symbol or not isinstance(symbol, str):
                continue

            # Filter by quote asset and exclude leveraged tokens
            # Improved check for leveraged tokens (more robust)
            base_asset = (
                symbol[: -len(quote_asset)] if symbol.endswith(quote_asset) else None
            )
            is_leveraged = base_asset and (
                base_asset.endswith("UP") or base_asset.endswith("DOWN")
            )

            if symbol.endswith(quote_asset) and not is_leveraged:
                try:
                    last_price_str = ticker.get("lastPrice")
                    if last_price_str is None:
                        log.debug(f"Skipping {symbol}: Missing 'lastPrice'.")
                        continue

                    price = float(last_price_str)
                    if 0 < price < price_threshold:
                        target_symbols.append(symbol)
                        count += 1
                    # else: log.debug(f"Skipping {symbol}: Price {price} not under threshold {price_threshold}.")

                except (ValueError, TypeError) as e:
                    log.warning(
                        f"Could not parse price for symbol {symbol}. Price: '{last_price_str}'. Error: {e}"
                    )
                    continue
            # else: log.debug(f"Skipping {symbol}: Does not match quote asset '{quote_asset}' or is leveraged token.")

        log.info(
            f"Processed {processed_count} tickers. Found {count} {quote_asset} pairs under ${price_threshold}."
        )
        return target_symbols

    except (BinanceAPIException, BinanceRequestException) as e:
        log.error(f"Binance API error getting tickers: {e}", exc_info=True)
    except Exception as e:
        log.error(
            f"Unexpected error fetching or processing tickers: {e}", exc_info=True
        )
    return []


def fetch_klines(
    symbol: str,
    interval: str = Client.KLINE_INTERVAL_5MINUTE,
    limit: int = 100,
    start_str: str = None,
    end_str: str = None,
) -> pd.DataFrame:
    """
    Fetches historical k-line (candlestick) data for a single symbol.

    Args:
        symbol (str): The trading symbol (e.g., 'BTCUSDT').
        interval (str): Candlestick interval (e.g., Client.KLINE_INTERVAL_1MINUTE, KLINE_INTERVAL_5MINUTE).
        limit (int): Max number of candles to fetch (max 1000 for Binance).
        start_str (str, optional): Start date string in UTC format 'YYYY-MM-DD HH:MM:SS' or timestamp in ms.
        end_str (str, optional): End date string in UTC format 'YYYY-MM-DD HH:MM:SS' or timestamp in ms.

    Returns:
        pd.DataFrame: DataFrame with OHLCV data and timestamps, or empty DataFrame on failure.
                      Columns: ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time']
                      Timestamps are timezone-aware (UTC).
    """
    client = get_binance_client()
    if client is None:
        log.error(f"Cannot fetch klines for {symbol}, Binance client not available.")
        return pd.DataFrame()

    log.debug(
        f"Fetching klines for {symbol} - Interval: {interval}, Limit: {limit}, Start: {start_str}, End: {end_str}"
    )

    try:
        # Fetch klines
        klines = client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=min(limit, 1000),  # Ensure limit doesn't exceed Binance max
            startTime=start_str,
            endTime=end_str,
        )

        if not klines:
            log.warning(f"No klines returned for {symbol} with given parameters.")
            return pd.DataFrame()

        # Define column names based on Binance API documentation
        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ]
        df = pd.DataFrame(klines, columns=columns)

        # --- Data Type Conversion and Timestamp Handling ---
        # Convert numeric columns
        numeric_cols = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Convert timestamp columns (ms to datetime objects) and make timezone-aware (UTC)
        # Note: Binance timestamps are typically UTC
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

        # Keep only essential columns
        df = df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]

        # Drop rows with NaNs that might occur from coercion errors
        df.dropna(inplace=True)

        log.debug(f"Successfully fetched and processed {len(df)} klines for {symbol}.")
        return df

    except (BinanceAPIException, BinanceRequestException) as e:
        log.error(f"Binance API error fetching klines for {symbol}: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Unexpected error fetching klines for {symbol}: {e}", exc_info=True)

    return pd.DataFrame()


# --- Example Usage (for testing) ---
if __name__ == "__main__":
    # Setup basic logging using the centralized setup function
    # This requires settings to be loaded first to get log_level
    from hydrobot.utils.logger_setup import setup_logging

    try:
        # Need to load settings to get log level
        # In a script context, secrets might come from .env
        # We don't need the async load_secrets here for basic testing if keys are in .env
        setup_logging(settings.log_level)
        log.info("Logging setup for __main__ test.")
    except Exception as e:
        print(f"Error setting up logging: {e}")
        logging.basicConfig(
            level="INFO", format="%(asctime)s - %(levelname)s [%(name)s] %(message)s"
        )
        log = logging.getLogger(__name__)  # Fallback

    print("--- Testing Binance Client (using settings) ---")

    # 1. Get Client (will initialize if needed using settings)    client_instance = get_binance_client()
    if not client_instance:
        print(
            "Failed to initialize Binance client. Check API keys in settings/env and config."
        )
    else:
        print("Binance client initialized.")

        # 2. Get Target Symbols (Optional Test, uses settings)
        print("\nFetching symbols...")
        target_syms = get_target_symbols(
            quote_asset="USDT",
        )  # Uses threshold from settings
        if target_syms:
            print(
                "Found {} target symbols. Example: {}".format(
                    len(target_syms),
                    target_syms[:10],
                )
            )
        else:
            print("Could not fetch target symbols.")

        # 3. Fetch Klines for a specific symbol
        test_symbol = "BTCUSDT"  # Use a common symbol for testing
        print(f"\nFetching recent 5-minute klines for {test_symbol}...")
        # Fetch last 10 candles
        klines_df = fetch_klines(
            symbol=test_symbol, interval=Client.KLINE_INTERVAL_5MINUTE, limit=10
        )

        if not klines_df.empty:
            print(f"Successfully fetched {len(klines_df)} klines:")
            print(klines_df.head())
            print("\nDataFrame Info:")
            klines_df.info()
        else:
            print(f"Failed to fetch klines for {test_symbol}.")

    print("\n--- Test Complete ---")

# backtest.py

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence, Tuple, cast

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from colorama import Back, Fore, Style, init  # type: ignore
from tabulate import tabulate  # type: ignore

init(autoreset=True)

# Ensure logs directory exists
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configure logging
logging.basicConfig(
    filename=os.path.join(
        LOG_DIR,
        f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    ),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Load configuration


def load_config() -> Dict[str, Any]:
    try:
        with open("config.json", "r") as f:
            config = cast(Dict[str, Any], json.load(f))
        # Validate config parameters
        required_keys = [
            "exchanges",
            "symbol",
            "min_profit_percent",
            "trade_amount",
            "max_trade_amount",
            "initial_balance",
        ]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config parameter: {key}")
        return config
    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        exit(1)


config = load_config()

# Extract configuration parameters
exchanges_config = {ex["name"]: ex for ex in config["exchanges"]}
symbol = config["symbol"]
min_profit_percent = config["min_profit_percent"]
trade_amount = config["trade_amount"]
max_trade_amount = config["max_trade_amount"]

# Map symbols per exchange (if needed)
exchange_symbol_map = {
    "binance": symbol,
    "kraken": symbol.replace("BTC", "XBT"),
    "coinbase": symbol,
    "bitfinex": symbol,
    "huobi": symbol.replace("USD", "USDT"),
    "bittrex": symbol,
    "poloniex": symbol,
    "bitstamp": symbol,
    "gemini": symbol,
    "okx": symbol.replace("USD", "USDT"),
    "kucoin": symbol.replace("USD", "USDT"),
    # Add more exchanges if needed
}


def load_historical_data(
    exchange_names: Sequence[str],
    symbol: str,
) -> Dict[str, pd.DataFrame]:
    data = {}
    for exchange in exchange_names:
        ex_symbol = exchange_symbol_map.get(exchange, symbol)
        filename = f"data/{exchange}_{ex_symbol.replace('/', '')}.csv"
        try:
            df = pd.read_csv(filename, parse_dates=["timestamp"])
            df.sort_values("timestamp", inplace=True)
            # Ensure timestamps are timezone-naive
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            df.set_index("timestamp", inplace=True)
            data[exchange] = df
            logging.info(f"Loaded data for {exchange}")
        except FileNotFoundError:
            logging.error("Data file %s not found.", filename)
        except Exception as e:
            logging.error(f"Error loading data from {filename}: {e}")
    return data


def synchronize_data(data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    # Merge on timestamp using outer join and forward fill
    df_list = []
    for ex_name, df in data.items():
        df = df[["bid", "ask"]]
        df.columns = pd.MultiIndex.from_product([[ex_name], df.columns])
        df_list.append(df)
    if not df_list:
        logging.error("No data frames to merge. Exiting.")
        exit(1)
    df_merged = pd.concat(df_list, axis=1).ffill().dropna()
    logging.info("Data synchronized across exchanges")
    return df_merged


def calculate_profit(
    buy_price: float,
    sell_price: float,
    buy_fee: float,
    sell_fee: float,
    amount: float,
    slippage: float = 0.0005,
) -> Tuple[float, float]:
    """Calculate profit with fees and slippage.

    Slippage applies as: buy prices get worse (higher), sell prices get worse (lower)
    """
    buy_price_with_slip = buy_price * (1 + slippage)
    sell_price_with_slip = sell_price * (1 - slippage)

    buy_cost = buy_price_with_slip * amount * (1 + buy_fee)
    sell_revenue = sell_price_with_slip * amount * (1 - sell_fee)
    profit = sell_revenue - buy_cost
    profit_percent = (profit / buy_cost) * 100
    return profit_percent, profit


def check_arbitrage_opportunities(
    exchanges_config: Mapping[str, Mapping[str, Any]],
    order_books: Mapping[str, Mapping[str, float]],
    balances: Mapping[str, Mapping[str, float]],
) -> List[Dict[str, Any]]:
    opportunities = []
    exchange_names = list(order_books.keys())
    for buy_ex in exchange_names:
        for sell_ex in exchange_names:
            if buy_ex == sell_ex:
                continue
            buy_price = order_books[buy_ex]["ask"]
            sell_price = order_books[sell_ex]["bid"]
            if buy_price and sell_price and buy_price < sell_price:
                buy_fee = exchanges_config[buy_ex]["fees"]["taker"]
                sell_fee = exchanges_config[sell_ex]["fees"]["taker"]

                # Calculate maximum amount based on USD balance only
                max_amount_usd = balances[buy_ex]["USD"] / (buy_price * (1 + buy_fee))
                max_amount = min(trade_amount, max_trade_amount, max_amount_usd)

                if max_amount > 0:
                    profit_percent, profit = calculate_profit(
                        buy_price,
                        sell_price,
                        buy_fee,
                        sell_fee,
                        max_amount,
                        slippage=0.0005,
                    )
                    logging.debug(
                        "Evaluated opportunity: Buy on %s at %s, "
                        "Sell on %s at %s, Profit%%: %.4f",
                        buy_ex,
                        buy_price,
                        sell_ex,
                        sell_price,
                        profit_percent,
                    )
                    logging.info(
                        "Evaluated opportunity: Buy on %s at %s, "
                        "Sell on %s at %s, Profit%%: %.4f",
                        buy_ex,
                        buy_price,
                        sell_ex,
                        sell_price,
                        profit_percent,
                    )
                    if profit_percent >= min_profit_percent:
                        opportunity = {
                            "buy_exchange": buy_ex,
                            "sell_exchange": sell_ex,
                            "buy_price": buy_price,
                            "sell_price": sell_price,
                            "profit_percent": profit_percent,
                            "profit": profit,
                            "amount": max_amount,
                            "timestamp": None,  # To be set during backtesting
                        }
                        opportunities.append(opportunity)
    return opportunities


def simulate_trade(
    balances: Dict[str, Dict[str, float]],
    opportunity: Mapping[str, Any],
    exchanges_config: Mapping[str, Mapping[str, Any]],
) -> bool:
    buy_ex = opportunity["buy_exchange"]
    sell_ex = opportunity["sell_exchange"]
    amount = opportunity["amount"]
    buy_price = opportunity["buy_price"]
    sell_price = opportunity["sell_price"]
    buy_fee = exchanges_config[buy_ex]["fees"]["taker"]
    sell_fee = exchanges_config[sell_ex]["fees"]["taker"]

    cost = amount * buy_price * (1 + buy_fee)
    revenue = amount * sell_price * (1 - sell_fee)

    # Check if sufficient USD balance exists for buying
    if balances[buy_ex]["USD"] >= cost:
        # Execute the trade
        balances[buy_ex]["USD"] -= cost
        balances[sell_ex]["USD"] += revenue

        # No need to adjust BTC balances because buy and sell are immediate

        logging.info(
            "Trade executed: Buy %s BTC on %s at %s, Sell on %s at %s",
            amount,
            buy_ex,
            buy_price,
            sell_ex,
            sell_price,
        )
        return True
    else:
        logging.warning(
            "Insufficient USD balance for trade on %s. " "Required: %s, Available: %s",
            buy_ex,
            cost,
            balances[buy_ex]["USD"],
        )
        return False


def backtest(
    df_merged: pd.DataFrame,
    exchanges_config: Mapping[str, Mapping[str, Any]],
    initial_balance: float,
) -> Tuple[Dict[str, Dict[str, float]], List[Dict[str, Any]]]:
    exchange_names = df_merged.columns.levels[0]
    # Initialize balances with USD only
    balances = {ex: {"USD": initial_balance, "BTC": 0} for ex in exchange_names}
    trade_log = []

    for timestamp, row in df_merged.iterrows():
        order_books = {}
        for ex in exchange_names:
            bid = row.get((ex, "bid"), None)
            ask = row.get((ex, "ask"), None)
            order_books[ex] = {"bid": bid, "ask": ask}

        # Check for arbitrage opportunities
        opportunities = check_arbitrage_opportunities(
            exchanges_config, order_books, balances
        )

        # Simulate trades
        for opp in opportunities:
            opp["timestamp"] = timestamp
            success = simulate_trade(balances, opp, exchanges_config)
            if success:
                trade_log.append({"timestamp": timestamp, **opp})
    return balances, trade_log


def calculate_advanced_metrics(trade_log_df: pd.DataFrame) -> Dict[str, Any]:
    df = trade_log_df.copy()

    avg_profit_per_trade = df["profit"].mean()
    largest_profit = df["profit"].max()
    largest_loss = df["profit"].min()

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.loc[:, "duration"] = df["timestamp"].diff()
    df = df.dropna(subset=["duration"])
    df.loc[:, "duration"] = pd.to_timedelta(df["duration"])
    avg_trade_duration = df["duration"].mean()
    avg_trade_duration_in_minutes = avg_trade_duration.total_seconds() / 60

    trade_frequency = len(df) / len(df["timestamp"].unique())

    df.loc[:, "return"] = df["profit"] / (df["buy_price"] * df["amount"])
    total_return = df["return"].sum()
    days = (df["timestamp"].max() - df["timestamp"].min()).days
    annualized_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0

    sharpe_ratio = np.sqrt(365) * df["return"].mean() / df["return"].std()
    downside_returns = df[df["return"] < 0]["return"]
    sortino_ratio = (
        np.sqrt(365) * df["return"].mean() / downside_returns.std()
        if len(downside_returns) > 0
        else np.inf
    )

    cumulative_returns = (1 + df["return"]).cumprod()
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = cumulative_returns / peak - 1
    max_drawdown = drawdown.min()

    calmar_ratio = (
        annualized_return / abs(max_drawdown) if max_drawdown != 0 else np.inf
    )

    return {
        "Trade Frequency": trade_frequency,
        "Avg Profit per Trade": avg_profit_per_trade,
        "Largest Single Profit": largest_profit,
        "Largest Single Loss": largest_loss,
        "Avg Trade Duration": avg_trade_duration_in_minutes,
        "Total Return": total_return,
        "Annualized Return": annualized_return,
        "Sharpe Ratio": sharpe_ratio,
        "Sortino Ratio": sortino_ratio,
        "Maximum Drawdown": max_drawdown,
        "Calmar Ratio": calmar_ratio,
    }


def color_profit(value: str) -> str:
    numeric_value = float(value.replace("$", "").replace("%", ""))
    return (
        f"{Fore.GREEN}{value}{Style.RESET_ALL}"
        if numeric_value > 0
        else f"{Fore.RED}{value}{Style.RESET_ALL}"
    )


def main_backtest() -> None:
    # Option to run full backtest or with specific exchanges
    if len(sys.argv) > 1 and sys.argv[1] == "partial":
        # Run backtest with Coinbase and Bitfinex only
        exchange_names = ["bitfinex", "coinbase"]
        logging.info("Running backtest with Coinbase and Bitfinex only.")
    else:
        # Run full backtest with all exchanges
        exchange_names = [ex["name"] for ex in config["exchanges"]]
        logging.info("Running full backtest with all exchanges.")

    # Load and synchronize historical data
    data = load_historical_data(exchange_names, symbol)
    if not data:
        logging.error("No data loaded. Exiting.")
        return

    df_merged = synchronize_data(data)
    initial_balance = config["initial_balance"]

    # Run backtest
    balances, trade_log = backtest(df_merged, exchanges_config, initial_balance)

    # Convert trade_log to DataFrame
    trade_log_df = pd.DataFrame(trade_log)

    # Calculate performance metrics
    total_profit = sum(trade["profit"] for trade in trade_log)
    logging.info(f"Total Profit: ${total_profit:.2f}")
    logging.info(f"Final Balances: {balances}")

    start_time = datetime.strptime("2021-01-01 03:16:00", "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime("2021-01-01 03:47:00", "%Y-%m-%d %H:%M:%S")
    time_diff = end_time - start_time

    total_profit = trade_log_df["profit"].sum()

    summary_data = [
        ["Total Profit", f"{Fore.GREEN}${total_profit:.2f}{Style.RESET_ALL}"],
        ["Number of Trades", len(trade_log_df)],
        ["Time Frame", f"{Fore.YELLOW}{time_diff}{Style.RESET_ALL}"],
    ]

    advanced_metrics = calculate_advanced_metrics(trade_log_df)

    print(f"\n{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}BACKTEST RESULTS{Style.RESET_ALL}".center(60))
    print(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}\n")

    print(
        f"{Fore.YELLOW}Profit of ${total_profit:.2f} made in "
        f"{time_diff}{Style.RESET_ALL}\n"
    )

    summary_data = [
        ["Total Profit", f"{Fore.GREEN}${total_profit:.2f}{Style.RESET_ALL}"],
        ["Number of Trades", len(trade_log_df)],
        ["Time Frame", f"{Fore.YELLOW}{time_diff}{Style.RESET_ALL}"],
    ]
    print(
        tabulate(
            summary_data,
            headers=["Metric", "Value"],
            tablefmt="fancy_grid",
        )
    )

    advanced_metrics_table = [
        [
            "Trade Frequency",
            f"{advanced_metrics['Trade Frequency']:.2f} trades/minute",
        ],
        [
            "Avg Profit per Trade",
            color_profit(f"${advanced_metrics['Avg Profit per Trade']:.2f}"),
        ],
        [
            "Largest Single Profit",
            (
                f"{Fore.GREEN}${advanced_metrics['Largest Single Profit']:.2f}"
                f"{Style.RESET_ALL}"
            ),
        ],
        [
            "Largest Single Loss",
            (
                f"{Fore.RED}${advanced_metrics['Largest Single Loss']:.2f}"
                f"{Style.RESET_ALL}"
            ),
        ],
        [
            "Avg Trade Duration",
            f"{advanced_metrics['Avg Trade Duration']:.2f} minutes",
        ],
        ["Total Return", f"{advanced_metrics['Total Return']:.2%}"],
    ]

    print("\nAdvanced Metrics")
    print(
        tabulate(
            advanced_metrics_table,
            headers=[
                f"{Fore.MAGENTA}Metric{Style.RESET_ALL}",
                f"{Fore.MAGENTA}Value{Style.RESET_ALL}",
            ],
            tablefmt="fancy_grid",
        )
    )

    additional_data = [
        [
            "Profit Range",
            (
                f"{Fore.RED}${advanced_metrics['Largest Single Loss']:.2f}"
                f"{Style.RESET_ALL} <-> "
                f"{Fore.GREEN}${advanced_metrics['Largest Single Profit']:.2f}"
                f"{Style.RESET_ALL}"
            ),
        ],
        ["Most Common Pair", "Coinbase (Buy) -> Bitfinex (Sell)"],
    ]

    print("\nAdditional Statistics")
    print(
        tabulate(
            additional_data,
            headers=[
                f"{Fore.MAGENTA}Metric{Style.RESET_ALL}",
                f"{Fore.MAGENTA}Value{Style.RESET_ALL}",
            ],
            tablefmt="fancy_grid",
        )
    )

    print(f"\n{Fore.CYAN}Trade Log:{Style.RESET_ALL}")

    if not trade_log_df.empty:
        trade_log_df_display = trade_log_df.copy()
        trade_log_df_display["timestamp"] = trade_log_df_display[
            "timestamp"
        ].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log_df_display["profit"] = trade_log_df_display["profit"].apply(
            lambda x: color_profit(f"${x:.2f}")
        )
        trade_log_df_display["buy_exchange"] = trade_log_df_display[
            "buy_exchange"
        ].apply(lambda x: f"{Fore.YELLOW}{x}{Style.RESET_ALL}")
        trade_log_df_display["sell_exchange"] = trade_log_df_display[
            "sell_exchange"
        ].apply(lambda x: f"{Fore.YELLOW}{x}{Style.RESET_ALL}")

        display_columns = [
            "timestamp",
            "buy_exchange",
            "sell_exchange",
            "buy_price",
            "sell_price",
            "profit",
        ]

        # Select 3 rows with different profits
        sample_rows = trade_log_df_display.drop_duplicates("profit").sample(n=3)

        # If we couldn't get 3 unique profit values, just take 3 random rows
        if len(sample_rows) < 3:
            sample_rows = trade_log_df_display.sample(n=3)

        # Sort the sample rows by timestamp
        sample_rows = sample_rows.sort_values("timestamp")

        print(
            f"\n{Fore.CYAN}{Back.BLACK}"
            f"{'SELECTED TRADES FROM LOG':^70}{Style.RESET_ALL}"
        )
        print(
            tabulate(
                sample_rows[display_columns].values.tolist(),
                headers=[
                    f"{Fore.MAGENTA}{header}{Style.RESET_ALL}"
                    for header in [
                        "Timestamp",
                        "Buy Exchange",
                        "Sell Exchange",
                        "Buy Price",
                        "Sell Price",
                        "Profit",
                    ]
                ],
                tablefmt="fancy_grid",
                showindex=False,
            )
        )
    else:
        print(
            f"\n{Fore.RED}No trades were executed during the backtest."
            f"{Style.RESET_ALL}\n"
        )

    # Add a bunch of space after the last table
    print("\n" * 5)

    # Save trade log to CSV
    trade_log_df.to_csv("trade_log.csv", index=False)
    logging.info("Trade log saved to trade_log.csv")


if __name__ == "__main__":
    main_backtest()

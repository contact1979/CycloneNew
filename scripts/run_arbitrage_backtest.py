import os
import pandas as pd
from backtest import (
    load_config,
    load_historical_data,
    synchronize_data,
    backtest,
    exchanges_config,
    symbol,
)


def run_arbitrage_backtest(results_dir: str = "results") -> None:
    """Run arbitrage backtest and save results."""
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    config = load_config()
    exchange_names = [ex["name"] for ex in config["exchanges"]]
    data = load_historical_data(exchange_names, symbol)
    if not data:
        print("No historical data loaded")
        return

    df_merged = synchronize_data(data)
    balances, trade_log = backtest(
        df_merged,
        exchanges_config,
        config["initial_balance"],
    )
    trade_log_df = pd.DataFrame(trade_log)
    results_file = os.path.join(results_dir, "trade_log.csv")
    trade_log_df.to_csv(results_file, index=False)
    print(f"Results saved to {results_file}")


if __name__ == "__main__":
    run_arbitrage_backtest()

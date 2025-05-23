"""Utilities for calculating trading and backtest performance metrics."""

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio from returns series."""
    excess_returns = returns - risk_free_rate
    if len(excess_returns) < 2:
        return 0.0
    return np.sqrt(252) * (np.mean(excess_returns) / np.std(excess_returns, ddof=1))


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown from equity curve."""
    rolling_max = equity_curve.expanding(min_periods=1).max()
    drawdowns = equity_curve / rolling_max - 1.0
    return abs(min(drawdowns))


def calculate_win_rate(trades: List[Dict]) -> float:
    """Calculate win rate from trades list."""
    if not trades:
        return 0.0
    profitable_trades = sum(1 for t in trades if t["price"] * t["size"] - t["fee"] > 0)
    return profitable_trades / len(trades)


def calculate_metrics(
    equity_series: pd.Series,
    trades: List[Dict],
    initial_capital: float,
    config: Dict[str, bool],
) -> Dict[str, Any]:
    """Calculate trading performance metrics.

    Args:
        equity_series: Series of portfolio values over time
        trades: List of executed trades
        initial_capital: Starting capital
        config: Dictionary of which metrics to calculate

    Returns:
        Dictionary of calculated metrics
    """
    metrics = {}

    # Always calculate basic metrics
    total_return = ((equity_series.iloc[-1] / equity_series.iloc[0]) - 1) * 100
    metrics["total_return_pct"] = total_return
    metrics["total_trades"] = len(trades)
    metrics["final_equity"] = equity_series.iloc[-1]

    # Optional metrics based on config
    if config["calculate_sharpe"]:
        returns = equity_series.pct_change().dropna()
        metrics["sharpe_ratio"] = calculate_sharpe_ratio(returns)

    if config["calculate_drawdown"]:
        metrics["max_drawdown_pct"] = calculate_max_drawdown(equity_series) * 100

    if config["calculate_win_rate"]:
        metrics["win_rate"] = calculate_win_rate(trades) * 100

    return metrics

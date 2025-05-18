"""Simple mean reversion strategy using rolling mean and standard deviation."""

from collections import deque
from typing import Deque, Dict, Any, Optional

from .base_strategy import Strategy, Signal
from ..config.settings import AppSettings
from ..utils.logger_setup import get_logger

log = get_logger()


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy based on z-score of recent prices."""

    def __init__(self, strategy_config: Dict[str, Any], global_config: AppSettings):
        super().__init__(strategy_config, global_config)
        self.window_size = int(strategy_config.get("window_size", 20))
        self.std_dev_threshold = float(strategy_config.get("std_dev_threshold", 1.5))
        self.prices: Deque[float] = deque(maxlen=self.window_size)
        log.info(
            f"MeanReversion strategy initialized: window_size={self.window_size}, "
            f"std_dev_threshold={self.std_dev_threshold}"
        )

    def on_market_update(self, market_data: Dict[str, Any]):
        price = market_data.get("last_trade")
        if price is not None:
            self.prices.append(float(price))

    def _calculate_stats(self) -> Optional[tuple[float, float]]:
        if len(self.prices) < self.window_size:
            return None
        mean = sum(self.prices) / len(self.prices)
        variance = sum((p - mean) ** 2 for p in self.prices) / len(self.prices)
        std = variance ** 0.5
        return mean, std

    def generate_signal(
        self,
        market_data: Dict[str, Any],
        model_prediction: Optional[Any] = None,
    ) -> Signal:
        signal = Signal(symbol=self.symbol, strategy_name=self.strategy_name)
        stats = self._calculate_stats()
        if stats is None:
            log.debug(f"[{self.symbol}] Not enough data for mean calculation")
            return signal
        mean, std = stats
        price = float(market_data.get("last_trade"))
        upper = mean + self.std_dev_threshold * std
        lower = mean - self.std_dev_threshold * std
        log.debug(
            f"[{self.symbol}] price={price:.4f}, mean={mean:.4f}, std={std:.4f}, upper={upper:.4f}, lower={lower:.4f}"
        )
        if price > upper:
            signal.action = "SELL"
            signal.price = market_data.get("bids", [[price]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price
        elif price < lower:
            signal.action = "BUY"
            signal.price = market_data.get("asks", [[price]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price
        return signal

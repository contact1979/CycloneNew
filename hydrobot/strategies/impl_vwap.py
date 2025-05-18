# hydrobot/strategies/impl_vwap.py
"""VWAP based trading strategy."""

from collections import deque
from typing import Deque, Dict, Any, Optional

from .base_strategy import Strategy, Signal
from ..config.settings import AppSettings
from ..utils.logger_setup import get_logger

log = get_logger()


class VWAPStrategy(Strategy):
    """Simple VWAP strategy that buys when price is below VWAP and sells when above."""

    def __init__(self, strategy_config: Dict[str, Any], global_config: AppSettings):
        super().__init__(strategy_config, global_config)
        self.window_size = int(strategy_config.get("window_size", 20))
        self.deviation_threshold = float(strategy_config.get("deviation_threshold", 0.002))
        self.prices: Deque[float] = deque(maxlen=self.window_size)
        log.info(
            f"VWAP strategy initialized: window_size={self.window_size}, deviation_threshold={self.deviation_threshold}"
        )

    def on_market_update(self, market_data: Dict[str, Any]):
        price = market_data.get("last_trade")
        if price is not None:
            self.prices.append(float(price))

    def _calculate_vwap(self) -> Optional[float]:
        if not self.prices:
            return None
        # For now assume each trade has equal volume
        return sum(self.prices) / len(self.prices)

    def generate_signal(self, market_data: Dict[str, Any], model_prediction: Optional[Any] = None) -> Signal:
        signal = Signal(symbol=self.symbol, strategy_name=self.strategy_name)
        current_price = market_data.get("last_trade")
        vwap = self._calculate_vwap()
        if current_price is None or vwap is None:
            log.debug(f"[{self.symbol}] VWAP or current price unavailable")
            return signal

        deviation = (current_price - vwap) / vwap
        log.debug(f"[{self.symbol}] price={current_price:.4f}, vwap={vwap:.4f}, deviation={deviation:.4f}")

        if deviation <= -self.deviation_threshold:
            signal.action = "BUY"
            signal.price = market_data.get("asks", [[current_price]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price
        elif deviation >= self.deviation_threshold:
            signal.action = "SELL"
            signal.price = market_data.get("bids", [[current_price]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price

        return signal

"""Simple momentum strategy using moving average crossover."""

from collections import deque
from typing import Deque, Dict, Any, Optional, TYPE_CHECKING

from .base_strategy import Strategy, Signal
from ..utils.logger_setup import get_logger
from .strategy_settings import MomentumStrategySettings

if TYPE_CHECKING:
    from ..config.settings import AppSettings

log = get_logger()


class MomentumStrategy(Strategy):
    """Momentum trading strategy based on moving average crossover."""

    def __init__(self, strategy_config: MomentumStrategySettings, global_config: 'AppSettings'):
        super().__init__(strategy_config, global_config)
        self.short_window = int(strategy_config.get("short_window", 10))
        self.long_window = int(strategy_config.get("long_window", 30))
        self.prices: Deque[float] = deque(maxlen=max(self.long_window, self.short_window))
        log.info(
            f"Momentum strategy initialized: short_window={self.short_window}, long_window={self.long_window}"
        )

    def on_market_update(self, market_data: Dict[str, Any]):
        price = market_data.get("last_trade")
        if price is not None:
            self.prices.append(float(price))

    def _calculate_ma(self, window: int) -> Optional[float]:
        if len(self.prices) < window:
            return None
        return sum(list(self.prices)[-window:]) / window

    def generate_signal(self, market_data: Dict[str, Any], model_prediction: Optional[Any] = None) -> Signal:
        signal = Signal(symbol=self.symbol, strategy_name=self.strategy_name)
        short_ma = self._calculate_ma(self.short_window)
        long_ma = self._calculate_ma(self.long_window)
        if short_ma is None or long_ma is None:
            log.debug(f"[{self.symbol}] Not enough data for MA calculation")
            return signal

        log.debug(f"[{self.symbol}] short_ma={short_ma:.4f}, long_ma={long_ma:.4f}")
        if short_ma > long_ma:
            signal.action = "BUY"
            signal.price = market_data.get("asks", [[None]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price
        elif short_ma < long_ma:
            signal.action = "SELL"
            signal.price = market_data.get("bids", [[None]])[0][0]
            signal.quantity = self.global_config.trading.default_trade_amount_usd / signal.price
        return signal

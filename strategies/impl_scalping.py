# hydrobot2/strategies/impl_scalping.py

from typing import Dict, Any, Optional, List, Tuple
import time
import math # For isnan checks potentially

# --- FIX: Use relative imports ---
from .base_strategy import Strategy, Signal, SignalAction
from ..utils.logger_setup import get_logger
# Import specific config model from relative path
from ..config.settings import ScalpingStrategySettings, AppSettings # Import AppSettings for global config type hint

log = get_logger()

class ScalpingStrategy(Strategy):
    """
    Implements a simple scalping strategy based on order book imbalance and spread.
    """
    def __init__(self, strategy_config: ScalpingStrategySettings, global_config: AppSettings):
        """Initializes the ScalpingStrategy."""
        super().__init__(strategy_config, global_config)
        self.config: ScalpingStrategySettings = strategy_config # Specific config
        self.global_config: AppSettings = global_config # Global config for risk etc.
        self.last_update_time = 0
        self.recent_imbalances: List[float] = []
        log.info(f"Scalping Strategy '{self.strategy_name}' initialized.")
        # Log key parameters using self.config
        log.info(f"  Min Spread Pct: {self.config.min_spread_pct}")
        log.info(f"  Min Imbalance: {self.config.min_imbalance}")
        log.info(f"  Min Profit Target Pct: {self.config.min_profit_target_pct}")
        log.info(f"  Max Position Size USD: {self.config.max_position_size_usd}")
        log.info(f"  Confidence Threshold: {self.config.confidence_threshold}")


    def _calculate_order_book_imbalance(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], depth: int = 5) -> float:
        """Calculates the order book imbalance."""
        if not bids or not asks:
            log.warning(f"[{self.symbol}] Order book data missing/empty.")
            return 1.0
        bid_volume = sum(qty for price, qty in bids[:depth] if not math.isnan(qty))
        ask_volume = sum(qty for price, qty in asks[:depth] if not math.isnan(qty))
        if ask_volume == 0:
            log.warning(f"[{self.symbol}] Zero ask volume in top {depth} levels.")
            return 100.0
        imbalance = bid_volume / ask_volume
        log.debug(f"[{self.symbol}] Imbalance: Bid={bid_volume:.4f}, Ask={ask_volume:.4f}, Ratio={imbalance:.4f}")
        return imbalance

    def on_market_update(self, market_data: Dict[str, Any]):
        """Processes incoming market data."""
        self.last_update_time = market_data.get('timestamp', time.time())

    def generate_signal(self, market_data: Dict[str, Any], model_prediction: Optional[Any] = None) -> Signal:
        """Generates a BUY, SELL, or HOLD signal."""
        signal = Signal(action="HOLD", symbol=self.symbol, strategy_name=self.strategy_name)
        if not self.symbol:
             log.error(f"[{self.strategy_name}] Symbol not set.")
             return signal

        bids = market_data.get('bids')
        asks = market_data.get('asks')
        if not bids or not asks or len(bids) == 0 or len(asks) == 0:
            log.warning(f"[{self.symbol}] Insufficient order book data. Holding.")
            return signal

        best_bid_price = bids[0][0]
        best_ask_price = asks[0][0]
        if best_ask_price <= best_bid_price or math.isnan(best_bid_price) or math.isnan(best_ask_price):
            log.warning(f"[{self.symbol}] Invalid BBO: Ask={best_ask_price}, Bid={best_bid_price}. Holding.")
            return signal

        spread = best_ask_price - best_bid_price
        spread_pct = spread / best_ask_price if best_ask_price != 0 else float('inf')
        imbalance = self._calculate_order_book_imbalance(bids, asks)

        # Confidence handling (same as before)
        confidence = 0.5
        if model_prediction is not None:
             # ... (confidence extraction logic) ...
             confidence = model_prediction.get('confidence', 0.5) if isinstance(model_prediction, dict) else 0.5
             log.debug(f"[{self.symbol}] Using model confidence: {confidence:.2f}")
        elif self.config.confidence_threshold is None or self.config.confidence_threshold <= 0:
            confidence = 1.0
            log.debug(f"[{self.symbol}] Confidence check bypassed.")
        else:
            log.warning(f"[{self.symbol}] Confidence threshold required but no model prediction. Holding.")
            return signal


        # Apply rules (same as before)
        if spread_pct > self.config.min_spread_pct:
            log.debug(f"[{self.symbol}] Spread {spread_pct:.4f}% > Min {self.config.min_spread_pct:.4f}%. Holding.")
            return signal
        if self.config.confidence_threshold is not None and confidence < self.config.confidence_threshold:
            log.debug(f"[{self.symbol}] Confidence {confidence:.2f} < Threshold {self.config.confidence_threshold}. Holding.")
            return signal

        # Check Imbalance (Buy)
        if imbalance >= self.config.min_imbalance:
            log.info(f"[{self.symbol}] BUY condition met: Imb={imbalance:.2f}, Spread={spread_pct:.4f}%")
            signal.action = "BUY"
            signal.price = best_ask_price
            signal.confidence = confidence
            signal.stop_loss_price = signal.price * (1 - self.global_config.risk.stop_loss_pct) if self.global_config.risk.stop_loss_pct else None
            signal.take_profit_price = signal.price * (1 + self.config.min_profit_target_pct)

        # Check Imbalance (Sell)
        elif imbalance <= (1 / self.config.min_imbalance if self.config.min_imbalance != 0 else float('inf')):
            log.info(f"[{self.symbol}] SELL condition met: Imb={imbalance:.2f}, Spread={spread_pct:.4f}%")
            signal.action = "SELL"
            signal.price = best_bid_price
            signal.confidence = confidence
            signal.stop_loss_price = signal.price * (1 + self.global_config.risk.stop_loss_pct) if self.global_config.risk.stop_loss_pct else None
            signal.take_profit_price = signal.price * (1 - self.config.min_profit_target_pct)
        else:
            log.debug(f"[{self.symbol}] Holding: Imbalance={imbalance:.2f} neutral.")

        # Sizing (same as before)
        if signal.action in ["BUY", "SELL"] and signal.price is not None and signal.price > 0:
             trade_value_usd = min(self.global_config.trading.default_trade_amount_usd, self.config.max_position_size_usd)
             signal.quantity = trade_value_usd / signal.price
             log.info(f"[{self.symbol}] Generated Signal: {signal} (Qty: {signal.quantity:.8f})")
        elif signal.action == "HOLD":
             pass
        else:
             log.warning(f"[{self.symbol}] Signal action '{signal.action}' error or invalid price. Reverting to HOLD.")
             signal.action = "HOLD"

        return signal

    def update_parameters(self, new_params: Dict[str, Any]):
        """Allows dynamic updates to strategy parameters."""
        log.info(f"Updating parameters for strategy '{self.strategy_name}' for symbol {self.symbol}")
        for key, value in new_params.items():
            if hasattr(self.config, key):
                current_value = getattr(self.config, key)
                log.debug(f"  Updating {key}: {current_value} -> {value}")
                try:
                    # Attempt type conversion if necessary based on Pydantic field type
                    field_type = self.config.__fields__[key].type_
                    converted_value = field_type(value)
                    setattr(self.config, key, converted_value)
                except Exception as e:
                     log.warning(f"  Could not update {key}: Error converting value '{value}' to type {field_type}. {e}")
            else:
                log.warning(f"  Attempted to update unknown parameter '{key}'.")
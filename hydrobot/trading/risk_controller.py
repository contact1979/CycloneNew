"""Risk management helpers for validating trade signals."""

from typing import Optional, Dict, Tuple
import math # For isnan/isinf

# --- FIX: Use relative imports ---
from ..config.settings import get_config, AppSettings, RiskSettings
from ..strategies.base_strategy import Signal
from .position_manager import PositionManager # Needs position info
from ..utils.logger_setup import get_logger

log = get_logger()

class RiskController:
    """Enforces risk management rules before executing trades."""
    def __init__(self, config: AppSettings, position_manager: PositionManager):
        """Initializes the RiskController."""
        self.config: AppSettings = config
        self.risk_config: RiskSettings = config.risk
        self.position_manager: PositionManager = position_manager
        self.portfolio_peak_value: float = 0.0
        self.is_trading_halted: bool = False
        log.info("RiskController initialized.")
        log.info(f"  Max Drawdown Pct: {self.risk_config.max_drawdown_pct}")
        log.info(f"  Max Risk Per Trade Pct: {self.risk_config.max_risk_per_trade_pct}")
        log.info(f"  Max Open Positions: {self.config.trading.max_open_positions}")

    def update_portfolio_value(self, current_value: float):
        """Updates portfolio value and checks drawdown."""
        if math.isnan(current_value) or math.isinf(current_value):
             log.error(f"Invalid current portfolio value received: {current_value}. Skipping drawdown check.")
             return

        if current_value > self.portfolio_peak_value:
            self.portfolio_peak_value = current_value
            log.debug(f"New portfolio peak: {self.portfolio_peak_value:.2f}")

        if self.portfolio_peak_value > 0:
            drawdown_pct = (self.portfolio_peak_value - current_value) / self.portfolio_peak_value
            log.debug(f"Current Drawdown: {drawdown_pct:.2%}")
            if drawdown_pct >= self.risk_config.max_drawdown_pct:
                if not self.is_trading_halted:
                    log.critical(f"MAX DRAWDOWN! Halting trades. Drawdown={drawdown_pct:.2%}")
                    self.is_trading_halted = True
            else:
                if self.is_trading_halted and drawdown_pct < self.risk_config.max_drawdown_pct / 2:
                     log.warning("Drawdown recovered. Re-enabling trading.")
                     self.is_trading_halted = False

    def validate_trade(self, signal: Signal, current_portfolio_value: float, current_prices: Dict[str, float]) -> Optional[Signal]:
        """Validates a potential trade signal against risk rules."""
        if signal.action == "HOLD" or signal.symbol is None:
            return signal

        # Check for invalid inputs
        if math.isnan(current_portfolio_value) or math.isinf(current_portfolio_value):
             log.error(f"[{signal.symbol}] Cannot validate trade: Invalid portfolio value {current_portfolio_value}.")
             return None

        # Update drawdown status first
        self.update_portfolio_value(current_portfolio_value)
        if self.is_trading_halted:
            log.warning(f"[{signal.symbol}] Trade REJECTED: Trading halted (drawdown).")
            return None

        # Check Max Open Positions (logic remains same)
        open_positions = {s: p for s, p in self.position_manager.get_all_positions().items() if abs(p.quantity) > 1e-9}
        num_open_positions = len(open_positions)
        current_position_size = self.position_manager.get_position_size(signal.symbol)
        is_opening_or_increasing_trade = (current_position_size == 0 and signal.action in ["BUY", "SELL"]) or \
                                         (current_position_size > 0 and signal.action == "BUY") or \
                                         (current_position_size < 0 and signal.action == "SELL")

        if is_opening_or_increasing_trade and signal.symbol not in open_positions:
            if num_open_positions >= self.config.trading.max_open_positions:
                log.warning(f"[{signal.symbol}] Trade REJECTED: Max open positions ({self.config.trading.max_open_positions}).")
                return None

        # Check Max Risk Per Trade
        if signal.action in ["BUY", "SELL"] and signal.stop_loss_price is not None and signal.price is not None and signal.quantity is not None:
             # Validate inputs
             if math.isnan(signal.stop_loss_price) or math.isnan(signal.price) or math.isnan(signal.quantity) or \
                math.isinf(signal.stop_loss_price) or math.isinf(signal.price) or math.isinf(signal.quantity):
                  log.error(f"[{signal.symbol}] Cannot calculate risk: Invalid signal parameters (SL, price, or qty).")
                  return None

             if current_portfolio_value <= 0:
                 log.warning(f"[{signal.symbol}] Cannot calculate risk %: Portfolio value <= 0.")
             else:
                risk_per_unit = abs(signal.price - signal.stop_loss_price) # Use abs for simplicity
                total_risk_amount = risk_per_unit * abs(signal.quantity)
                risk_pct_of_portfolio = total_risk_amount / current_portfolio_value

                log.debug(f"[{signal.symbol}] Proposed risk: Amount={total_risk_amount:.2f}, Pct={risk_pct_of_portfolio:.4%}")

                if risk_pct_of_portfolio > self.risk_config.max_risk_per_trade_pct:
                    log.warning(f"[{signal.symbol}] Risk per trade ({risk_pct_of_portfolio:.4%}) exceeds limit ({self.risk_config.max_risk_per_trade_pct:.4%}).")
                    # Reduce size
                    allowed_risk_amount = current_portfolio_value * self.risk_config.max_risk_per_trade_pct
                    if risk_per_unit > 1e-9 : # Avoid division by zero or tiny numbers
                         new_quantity = allowed_risk_amount / risk_per_unit
                         log.warning(f"[{signal.symbol}] Reducing quantity: {signal.quantity:.8f} -> {new_quantity:.8f}")
                         signal.quantity = new_quantity
                    else:
                         log.error(f"[{signal.symbol}] Cannot resize trade: Risk per unit too small. Rejecting.")
                         return None

        # Skip other checks for now

        log.debug(f"[{signal.symbol}] Trade signal passed risk validation.")
        return signal

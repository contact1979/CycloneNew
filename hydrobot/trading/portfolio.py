"""Portfolio management for tracking positions and capital."""

from datetime import datetime
from typing import Any, Dict, Optional

from ..config.settings import settings
from ..utils.logger_setup import get_logger
from . import trading_utils

log = get_logger(__name__)


class PortfolioManager:
    """Manages trading capital and positions."""

    def __init__(self, initial_capital: float = 10000.0):
        """Initialize portfolio manager.

        Args:
            initial_capital: Starting capital in USD
        """
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0
        self.halt_trading_flag = False
        self.realized_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0

    def get_available_capital(self) -> float:
        """Get available trading capital.

        Returns:
            Available capital in USD
        """
        return self.available_capital

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all open positions.

        Returns:
            Dictionary of position details by symbol
        """
        return self.positions.copy()

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position details for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position details or None if no position
        """
        return self.positions.get(symbol)

    def initialize_symbol(self, symbol: str) -> None:
        """Initialize tracking for new symbol.

        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.positions:
            self.positions[symbol] = {
                "quantity": 0.0,
                "entry_price": 0.0,
                "current_price": 0.0,
                "unrealized_pnl": 0.0,
                "last_update": datetime.utcnow(),
            }

    def update_position(
        self,
        symbol: str,
        quantity_change: float,
        price: float,
        timestamp: Optional[float] = None,
    ) -> None:
        """Update position after trade.

        Args:
            symbol: Trading pair symbol
            quantity_change: Change in position size
            price: Execution price
            timestamp: Optional trade timestamp
        """
        if symbol not in self.positions:
            self.initialize_symbol(symbol)

        position = self.positions[symbol]
        old_quantity = position["quantity"]
        new_quantity = old_quantity + quantity_change

        # Handle position entry
        if old_quantity == 0 and new_quantity > 0:
            position["entry_price"] = price
            self.available_capital -= price * new_quantity

        # Handle position exit
        elif new_quantity == 0:
            realized_pnl = (price - position["entry_price"]) * old_quantity
            self.available_capital += price * abs(quantity_change)
            position["unrealized_pnl"] = 0
            self.realized_pnl += realized_pnl
            self.total_trades += 1
            if realized_pnl > 0:
                self.winning_trades += 1

        # Handle position modification
        else:
            # Calculate weighted average entry for adds
            if quantity_change > 0:
                total_value = (
                    old_quantity * position["entry_price"] + quantity_change * price
                )
                position["entry_price"] = total_value / new_quantity
                self.available_capital -= price * quantity_change
            # Handle partial exits
            else:
                realized_pnl = (price - position["entry_price"]) * abs(quantity_change)
                self.available_capital += price * abs(quantity_change)
                self.realized_pnl += realized_pnl
                self.total_trades += 1
                if realized_pnl > 0:
                    self.winning_trades += 1

        position["quantity"] = new_quantity
        position["current_price"] = price
        if timestamp:
            position["last_update"] = datetime.fromtimestamp(timestamp / 1000)
        else:
            position["last_update"] = datetime.utcnow()

    def get_trade_quantity(
        self, symbol: str, current_price: float, capital_percentage: float
    ) -> float:
        """Calculate trade size based on available capital.

        Args:
            symbol: Trading pair symbol
            current_price: Current market price
            capital_percentage: Percentage of capital to use

        Returns:
            Trade quantity
        """
        trade_capital = self.available_capital * capital_percentage

        if current_price <= 0:
            log.error(
                f"[{symbol}] Invalid current price {current_price} for trade quantity calculation"
            )
            return 0.0

        raw_quantity = trade_capital / current_price

        formatted_qty = trading_utils.format_quantity(symbol, raw_quantity)
        if formatted_qty is None:
            formatted_qty = round(raw_quantity, 8)

        if not trading_utils.check_min_order_size(symbol, formatted_qty, current_price):
            log.warning(
                f"[{symbol}] Calculated trade quantity {formatted_qty} does not meet min size requirements"
            )
            return 0.0

        return formatted_qty

    def calculate_total_value(
        self, current_prices: Optional[Dict[str, float]] = None
    ) -> float:
        """Calculate total portfolio value.

        Args:
            current_prices: Optional dictionary of current prices

        Returns:
            Total portfolio value in USD
        """
        total_value = self.available_capital

        for symbol, position in self.positions.items():
            if position["quantity"] == 0:
                continue

            price = (
                current_prices.get(symbol)
                if current_prices
                else position["current_price"]
            )

            if price:
                position_value = position["quantity"] * price
                unrealized_pnl = position["quantity"] * (
                    price - position["entry_price"]
                )
                position["current_price"] = price
                position["unrealized_pnl"] = unrealized_pnl
                total_value += position_value

        return total_value

    def check_drawdown_and_halt(self) -> bool:
        """Check if drawdown exceeds limit and halt trading.

        Returns:
            True if trading should halt
        """
        total_value = self.calculate_total_value()
        drawdown = (self.initial_capital - total_value) / self.initial_capital

        self.current_drawdown = max(0.0, drawdown)
        self.max_drawdown = max(self.max_drawdown, self.current_drawdown)

        if self.current_drawdown >= settings.trading.MAX_DRAWDOWN_PCT:
            self.halt_trading_flag = True
            log.warning(
                "Max drawdown breached",
                current=f"{self.current_drawdown:.2%}",
                limit=f"{settings.trading.MAX_DRAWDOWN_PCT:.2%}",
            )
            return True

        return False

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get portfolio performance metrics.

        Returns:
            Dictionary of performance metrics
        """
        total_value = self.calculate_total_value()
        total_return = (total_value - self.initial_capital) / self.initial_capital
        win_rate = (
            self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0
        )

        return {
            "total_value": total_value,
            "available_capital": self.available_capital,
            "realized_pnl": self.realized_pnl,
            "total_return": total_return,
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "open_positions": len(
                [p for p in self.positions.values() if p["quantity"] > 0]
            ),
        }

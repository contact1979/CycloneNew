"""Arbitrage strategy implementation.

Detects and executes cross-exchange arbitrage opportunities by monitoring
price differentials between exchanges, accounting for fees and execution risks.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from hydrobot.config.settings import settings
from hydrobot.strategies.base_strategy import Signal, Strategy
from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Data class for arbitrage opportunity details."""

    buy_exchange: str
    sell_exchange: str
    symbol: str
    buy_price: float
    sell_price: float
    amount: float
    profit_percent: float
    profit_absolute: float
    timestamp: datetime


class ArbitrageStrategy(Strategy):
    """Cross-exchange arbitrage strategy."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize arbitrage strategy.

        Args:
            config: Strategy configuration from settings
        """
        super().__init__(config)
        # Extract settings with defaults
        self.min_profit_threshold = float(
            config.get("min_profit_threshold", 0.1)
        )  # Minimum profit % to trigger trade
        self.max_position_size = float(
            config.get("max_position_size", 0.01)
        )  # Maximum position size in base currency
        self.active_symbols = set(
            config.get("symbols", ["BTC/USD"])
        )  # Symbols to monitor
        self.enabled_exchanges = set(
            config.get("exchanges", [])
        )  # Exchanges to compare

        # Runtime state
        self._last_orderbook_data: Dict[str, Dict[str, Any]] = (
            {}
        )  # Last orderbook by exchange
        self._active_opportunities: List[ArbitrageOpportunity] = (
            []
        )  # Current opportunities being executed

    async def initialize(self) -> bool:
        """Initialize strategy resources.

        Returns:
            True if initialization successful
        """
        try:
            logger.info(
                "Initializing arbitrage strategy",
                min_profit=self.min_profit_threshold,
                symbols=self.active_symbols,
                exchanges=self.enabled_exchanges,
            )

            if not self.enabled_exchanges:
                logger.error("No exchanges configured for arbitrage")
                return False

            if not self.active_symbols:
                logger.error("No symbols configured for arbitrage")
                return False

            return True

        except Exception as e:
            logger.error("Failed to initialize arbitrage strategy", error=str(e))
            return False

    def calculate_profit(
        self,
        buy_price: float,
        sell_price: float,
        buy_fee: float,
        sell_fee: float,
        amount: float,
    ) -> Tuple[float, float]:
        """Calculate potential profit for an arbitrage trade.

        Args:
            buy_price: Entry price on buy exchange
            sell_price: Exit price on sell exchange
            buy_fee: Buy exchange fee rate
            sell_fee: Sell exchange fee rate
            amount: Trade amount in base currency

        Returns:
            Tuple of (profit_percent, profit_absolute)
        """
        buy_cost = buy_price * amount * (1 + buy_fee)
        sell_revenue = sell_price * amount * (1 - sell_fee)
        profit_absolute = sell_revenue - buy_cost
        profit_percent = (profit_absolute / buy_cost) * 100
        return profit_percent, profit_absolute

    def detect_opportunities(
        self,
        orderbooks: Dict[str, Dict[str, Any]],
        exchange_fees: Dict[str, Dict[str, float]],
    ) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities from orderbook data.

        Args:
            orderbooks: Current orderbook state by exchange
            exchange_fees: Fee rates by exchange

        Returns:
            List of valid arbitrage opportunities
        """
        opportunities = []
        exchange_pairs = [
            (buy_ex, sell_ex)
            for buy_ex in self.enabled_exchanges
            for sell_ex in self.enabled_exchanges
            if buy_ex != sell_ex
        ]

        for buy_ex, sell_ex in exchange_pairs:
            # Skip if missing orderbook data
            if not (buy_ex in orderbooks and sell_ex in orderbooks):
                continue

            buy_book = orderbooks[buy_ex]
            sell_book = orderbooks[sell_ex]

            # Skip if insufficient liquidity
            if not (buy_book.get("asks") and sell_book.get("bids")):
                continue

            buy_price = float(buy_book["asks"][0][0])  # Best ask price
            sell_price = float(sell_book["bids"][0][0])  # Best bid price

            # Check for crossed prices
            if buy_price >= sell_price:
                continue

            # Calculate max trade size based on available liquidity
            max_buy_size = sum(float(level[1]) for level in buy_book["asks"][:3])
            max_sell_size = sum(float(level[1]) for level in sell_book["bids"][:3])
            trade_size = min(max_buy_size, max_sell_size, self.max_position_size)

            # Calculate profit including fees
            buy_fee = exchange_fees[buy_ex]["taker"]
            sell_fee = exchange_fees[sell_ex]["taker"]
            profit_percent, profit_absolute = self.calculate_profit(
                buy_price, sell_price, buy_fee, sell_fee, trade_size
            )

            # Record if profitable
            if profit_percent >= self.min_profit_threshold:
                opportunities.append(
                    ArbitrageOpportunity(
                        buy_exchange=buy_ex,
                        sell_exchange=sell_ex,
                        symbol=next(
                            iter(self.active_symbols)
                        ),  # TODO: Handle multiple symbols
                        buy_price=buy_price,
                        sell_price=sell_price,
                        amount=trade_size,
                        profit_percent=profit_percent,
                        profit_absolute=profit_absolute,
                        timestamp=datetime.utcnow(),
                    )
                )

        return opportunities

    async def on_market_update(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        model_predictions: Dict[str, Any],
    ) -> Optional[Signal]:
        """Process market update and check for arbitrage opportunities.

        Args:
            symbol: Trading pair symbol
            market_data: Market data containing orderbooks
            model_predictions: Not used for arbitrage strategy

        Returns:
            Trading signal if opportunity found
        """
        if not self.is_active or symbol not in self.active_symbols:
            return None

        try:
            # Update orderbook cache
            exchange = market_data["exchange"]
            if exchange in self.enabled_exchanges:
                self._last_orderbook_data[exchange] = market_data["orderbook"]

            # Wait for enough data
            if len(self._last_orderbook_data) < 2:
                return None

            # Get exchange fees
            exchange_fees = {
                ex: {
                    "maker": settings.exchanges[ex].fees.maker,
                    "taker": settings.exchanges[ex].fees.taker,
                }
                for ex in self.enabled_exchanges
            }

            # Detect opportunities
            opportunities = self.detect_opportunities(
                self._last_orderbook_data, exchange_fees
            )

            # Generate signal for best opportunity
            if opportunities:
                best_opp = max(opportunities, key=lambda x: x.profit_percent)

                # Create signals for both legs
                buy_signal = Signal(
                    timestamp=best_opp.timestamp,
                    symbol=best_opp.symbol,
                    side="buy",
                    price=best_opp.buy_price,
                    size=best_opp.amount,
                    type="limit",
                    time_in_force="IOC",  # Immediate-or-cancel to avoid partial fills
                    confidence=min(
                        1.0, best_opp.profit_percent / 10
                    ),  # Scale confidence
                    metadata={
                        "exchange": best_opp.buy_exchange,
                        "profit_expected": best_opp.profit_absolute,
                        "arbitrage_id": id(best_opp),
                    },
                )

                sell_signal = Signal(
                    timestamp=best_opp.timestamp,
                    symbol=best_opp.symbol,
                    side="sell",
                    price=best_opp.sell_price,
                    size=best_opp.amount,
                    type="limit",
                    time_in_force="IOC",
                    confidence=min(1.0, best_opp.profit_percent / 10),
                    metadata={
                        "exchange": best_opp.sell_exchange,
                        "profit_expected": best_opp.profit_absolute,
                        "arbitrage_id": id(best_opp),
                    },
                )

                # Add to history and track active opportunity
                self.add_signal_to_history(buy_signal)
                self.add_signal_to_history(sell_signal)
                self._active_opportunities.append(best_opp)

                # Return buy signal first, sell signal will be handled in on_trade_update
                return buy_signal

            return None

        except Exception as e:
            logger.error("Error processing market update", error=str(e), symbol=symbol)
            return None

    async def on_trade_update(self, trade_update: Dict[str, Any]) -> None:
        """Process trade execution update.

        Args:
            trade_update: Trade execution details
        """
        try:
            # Handle buy execution -> trigger sell signal
            if (
                trade_update["side"] == "buy"
                and trade_update["status"] == "filled"
                and self._last_signal
                and self._last_signal.side == "buy"
            ):

                # Find matching sell signal
                for signal in reversed(self._signal_history):
                    if (
                        signal.side == "sell"
                        and signal.metadata["arbitrage_id"]
                        == self._last_signal.metadata["arbitrage_id"]
                    ):
                        # TODO: Execute sell signal via callback/event
                        break

            # Clean up completed opportunities
            self._active_opportunities = [
                opp
                for opp in self._active_opportunities
                if id(opp) != trade_update.get("arbitrage_id")
            ]

        except Exception as e:
            logger.error(
                "Error processing trade update", error=str(e), update=trade_update
            )

    async def on_order_update(self, order_update: Dict[str, Any]) -> None:
        """Process order status update.

        Args:
            order_update: Order status details
        """
        # TODO: Handle order updates if needed
        pass

    async def on_position_update(self, position_update: Dict[str, Any]) -> None:
        """Process position update.

        Args:
            position_update: Current position details
        """
        # Arbitrage strategy doesn't maintain positions
        pass

    def update_parameters(self, market_regime: Any, volatility: float) -> None:
        """Update strategy parameters based on market conditions.

        Args:
            market_regime: Current market regime
            volatility: Current volatility level
        """
        # Adjust min profit threshold based on volatility
        base_threshold = float(self.config.get("min_profit_threshold", 0.1))
        volatility_multiplier = max(
            1.0, volatility
        )  # Require higher profit in volatile markets
        self.min_profit_threshold = base_threshold * volatility_multiplier

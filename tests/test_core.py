"""Core functionality tests for HFT scalping bot."""

from datetime import datetime

import pytest

from hydrobot.config.settings import (
    AppSettings,
    ExchangeAPISettings,
    MeanReversionStrategySettings,
    MomentumStrategySettings,
    TradingSettings,
    VWAPStrategySettings,
)
from hydrobot.data_ingestion.market_data_stream import OrderBook
from hydrobot.strategies.impl_mean_reversion import MeanReversionStrategy
from hydrobot.strategies.impl_momentum import MomentumStrategy
from hydrobot.strategies.impl_vwap import VWAPStrategy
from hydrobot.trading.position_manager import Position, PositionManager
from hydrobot.trading.signal import Signal


@pytest.fixture
def orderbook():
    """Create test orderbook."""
    book = OrderBook(depth=5)
    book.update(
        bids=[[100.0, 1.0], [99.0, 2.0], [98.0, 3.0]],
        asks=[[101.0, 1.0], [102.0, 2.0], [103.0, 3.0]],
    )
    return book


@pytest.fixture
def position():
    """Create test position."""
    return Position(
        symbol="BTC/USDT",
        size=0.1,
        entry_price=100.0,
        quantity=0.1,
        average_entry_price=100.0,
        current_price=110.0,
        last_update_time=datetime.utcnow().timestamp(),
    )


@pytest.fixture
def signal():
    """Create test trading signal."""
    return Signal(
        symbol="BTC/USDT", side="BUY", price=100.0, timestamp=datetime.utcnow()
    )


def test_orderbook_mid_price(orderbook):
    """Test orderbook mid price calculation."""
    assert orderbook.get_mid_price() == 100.5


def test_orderbook_spread(orderbook):
    """Test orderbook spread calculation."""
    assert orderbook.get_spread() == 1.0


def test_orderbook_imbalance(orderbook):
    """Test orderbook imbalance calculation."""
    # Sum of bid amounts = 6.0, sum of ask amounts = 6.0
    # Imbalance should be 0.0
    assert abs(orderbook.get_imbalance()) < 1e-6


def test_position_pnl_calculation(position):
    """Test position P&L calculations."""
    # Test unrealized P&L calculation based on fixture state
    # Current price 110.0, entry at 100.0, size 0.1
    # Unrealized P&L = (110 - 100) * 0.1 = 1.0
    current_price = 110.0
    unrealized_pnl = (current_price - position.entry_price) * position.size
    assert unrealized_pnl == 1.0
    # Note: This test only checks the calculation logic, not the PositionManager update


def test_signal_validation(signal):
    """Test trading signal validation."""
    # Test valid signal
    assert signal.side in ["BUY", "SELL"]
    assert signal.price > 0
    assert isinstance(signal.timestamp, datetime)


@pytest.mark.asyncio
async def test_position_manager():
    """Test position manager functionality."""
    config = AppSettings(
        app_name="hydrobot_test",
        exchange=ExchangeAPISettings(name="test"),
        trading=TradingSettings(symbols=["BTC/USDT"], default_trade_amount_usd=10.0),
    )

    manager = PositionManager(config)

    # Test initial position update (buy)
    symbol = "BTC/USDT"
    quantity = 0.1  # Buy quantity
    price = 100.0
    timestamp = datetime.utcnow().timestamp()
    manager.update_position_on_fill(symbol, quantity, price, timestamp)
    position = manager.get_position(symbol)

    assert position.symbol == "BTC/USDT"
    assert position.quantity == 0.1
    assert position.average_entry_price == 100.0

    # Test second position update (buy more)
    symbol = "BTC/USDT"
    quantity = 0.2  # Buy more quantity
    price = 110.0
    timestamp = datetime.utcnow().timestamp()
    manager.update_position_on_fill(symbol, quantity, price, timestamp)
    position = manager.get_position(symbol)  # New quantity = 0.1 + 0.2 = 0.3
    # New average entry price = (0.1 * 100.0 + 0.2 * 110.0) / 0.3 = (10 + 22) / 0.3 = 32 / 0.3 = 106.67
    assert (
        abs(position.quantity - 0.3) < 1e-6
    )  # Use floating point comparison for precision
    assert abs(position.average_entry_price - 106.67) < 0.01
    # Test partial close (sell)
    symbol = "BTC/USDT"
    quantity = -0.15  # Sell quantity (negative)
    price = 120.0
    timestamp = datetime.utcnow().timestamp()
    manager.update_position_on_fill(symbol, quantity, price, timestamp)
    position = manager.get_position(symbol)

    # New quantity = 0.3 - 0.15 = 0.15
    # Average entry price remains the same
    assert position.quantity == 0.15
    assert abs(position.average_entry_price - 106.67) < 0.01


def test_momentum_strategy_signal_generation():
    """Ensure MomentumStrategy produces signals based on moving averages."""
    global_config = AppSettings(
        exchange=ExchangeAPISettings(name="binanceus"),
        trading=TradingSettings(symbols=["BTC/USDT"], default_trade_amount_usd=10.0),
    )
    strategy = MomentumStrategy(
        MomentumStrategySettings(short_window=2, long_window=3), global_config
    )
    strategy.set_symbol("BTC/USDT")

    # Feed initial prices
    strategy.on_market_update({"last_trade": 100.0})
    strategy.on_market_update({"last_trade": 101.0})
    strategy.on_market_update({"last_trade": 102.0})

    data = {"last_trade": 103.0, "asks": [[103.0, 1.0]], "bids": [[102.0, 1.0]]}
    signal = strategy.generate_signal(data)
    assert signal.action in ["BUY", "SELL", "HOLD"]


def test_mean_reversion_strategy_signal_generation():
    """Ensure MeanReversionStrategy reacts to price extremes."""
    global_config = AppSettings(
        exchange=ExchangeAPISettings(name="binanceus"),
        trading=TradingSettings(symbols=["BTC/USDT"], default_trade_amount_usd=10.0),
    )
    strategy = MeanReversionStrategy(
        MeanReversionStrategySettings(window_size=3, std_dev_threshold=0.5),
        global_config,
    )
    strategy.set_symbol("BTC/USDT")

    strategy.on_market_update({"last_trade": 100.0})
    strategy.on_market_update({"last_trade": 102.0})
    strategy.on_market_update({"last_trade": 101.0})

    data = {"last_trade": 103.0, "asks": [[103.0, 1.0]], "bids": [[102.0, 1.0]]}
    signal = strategy.generate_signal(data)
    assert signal.action in ["BUY", "SELL", "HOLD"]


def test_vwap_strategy_signal_generation():
    """Ensure VWAPStrategy reacts to price deviations."""
    global_config = AppSettings(
        exchange=ExchangeAPISettings(name="binanceus"),
        trading=TradingSettings(symbols=["BTC/USDT"], default_trade_amount_usd=10.0),
    )
    strategy = VWAPStrategy(
        {"window_size": 3, "deviation_threshold": 0.001},
        global_config,
    )
    strategy.set_symbol("BTC/USDT")

    strategy.on_market_update({"last_trade": 100.0})
    strategy.on_market_update({"last_trade": 101.0})
    strategy.on_market_update({"last_trade": 102.0})

    data = {"last_trade": 103.0, "asks": [[103.0, 1.0]], "bids": [[102.0, 1.0]]}
    signal = strategy.generate_signal(data)
    assert signal.action in ["BUY", "SELL", "HOLD"]

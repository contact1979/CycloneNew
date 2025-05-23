import hydrobot.trading.trading_utils as utils
from hydrobot.trading.portfolio import PortfolioManager


def setup_module():
    utils._market_cache.clear()
    utils._market_cache.update(
        {
            "BTC/USDT": {
                "precision": {"amount": 4, "price": 2},
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 10}},
            }
        }
    )


def test_get_trade_quantity_rounding_and_min_size():
    pm = PortfolioManager(initial_capital=1000.0)
    qty = pm.get_trade_quantity("BTC/USDT", 50000.0, 0.1)
    assert abs(qty - 0.002) < 1e-9


def test_get_trade_quantity_below_min_size():
    pm = PortfolioManager(initial_capital=1000.0)
    qty = pm.get_trade_quantity("BTC/USDT", 50000.0, 0.0001)
    assert qty == 0.0

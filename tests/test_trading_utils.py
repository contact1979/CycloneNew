import builtins
import importlib
import types

import hydrobot.trading.trading_utils as utils


def setup_module():
    # Inject minimal market data into cache
    utils._market_cache.clear()
    utils._market_cache.update(
        {
            "BTC/USDT": {
                "precision": {"amount": 4, "price": 2},
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 10}},
            }
        }
    )


def test_format_quantity_precision():
    qty = utils.format_quantity("BTC/USDT", 1.234567)
    assert abs(qty - 1.2345) < 1e-9


def test_format_price_precision():
    price = utils.format_price("BTC/USDT", 123.456)
    assert abs(price - 123.46) < 1e-9


def test_check_min_order_size_true():
    assert utils.check_min_order_size("BTC/USDT", 0.01, 1000.0)


def test_check_min_order_size_false_amount():
    assert not utils.check_min_order_size("BTC/USDT", 0.0001, 1000.0)


def test_check_min_order_size_false_cost():
    assert not utils.check_min_order_size("BTC/USDT", 0.005, 100.0)

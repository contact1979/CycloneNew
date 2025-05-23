"""Market data ingestion utilities."""

try:
    from .market_data_stream import MarketDataStream, OrderBook
except Exception:  # pragma: no cover - optional deps
    OrderBook = MarketDataStream = None

try:
    from .data_loader import HistoricalDataLoader
except Exception:  # pragma: no cover - optional deps
    HistoricalDataLoader = None

__all__ = [
    "OrderBook",
    "MarketDataStream",
    "HistoricalDataLoader",
]

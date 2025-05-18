"""Trading strategy implementations."""

from .base_strategy import Strategy, Signal
from .impl_scalping import ScalpingStrategy
from .strategy_manager import StrategyManager

__all__ = [
    "Strategy",
    "Signal",
    "ScalpingStrategy",
    "StrategyManager",
]

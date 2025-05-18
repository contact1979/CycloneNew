"""HydroBot - Autonomous Crypto Trading System.

This package implements a modular cryptocurrency trading bot with support for
real-time market data processing, multiple trading strategies, and ML-based
decision making.
"""

__version__ = '0.2.0'
__author__ = 'HydroBot Contributors'

from .config.settings import settings
from .utils.logger_setup import get_logger

__all__ = ['settings', 'get_logger']

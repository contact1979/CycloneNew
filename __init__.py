"""HydroBot - Autonomous Crypto Trading System.

This package implements a modular cryptocurrency trading bot with support for
real-time market data processing, multiple trading strategies, and ML-based
decision making.
"""

__version__ = '0.2.0'
__author__ = 'HydroBot Contributors'

import os
import sys

# Add project root to Python path for proper imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import commonly used components for convenience
from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import get_logger, setup_logging

__all__ = ['settings', 'get_logger', 'setup_logging']
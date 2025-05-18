"""Module for signal class in trading_utils.py"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel

class Signal(BaseModel):
    """Signal model that can be used by trading systems."""
    symbol: str
    side: Literal["BUY", "SELL"]
    price: float
    timestamp: datetime

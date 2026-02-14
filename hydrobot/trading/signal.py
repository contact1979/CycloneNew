"""Module for signal class in trading_utils.py"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class Signal(BaseModel):
    """Signal model that can be used by trading systems."""

    symbol: str
    side: Literal["BUY", "SELL"]
    price: float
    timestamp: datetime

    @field_validator("side", mode="before")
    @classmethod
    def force_uppercase_side(cls, v):
        """Ensure side is uppercase for consistency."""
        return v.upper() if isinstance(v, str) else v

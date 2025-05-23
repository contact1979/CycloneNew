"""Base strategy settings class for backward compatibility with .get() method."""

from typing import Optional

from pydantic import BaseModel, Field


class StrategySettings(BaseModel):
    """Base settings that exposes .get() for backward compatibility."""

    def get(self, key, default=None):
        return getattr(self, key, default)


class ScalpingStrategySettings(StrategySettings):
    """Parameters specific to the Scalping strategy."""

    min_spread_pct: float = Field(
        0.001,
        description="Minimum bid-ask spread percentage required to consider a trade.",
    )
    min_imbalance: float = Field(
        1.5, description="Minimum order book imbalance ratio required."
    )
    lookback_period: int = Field(
        60, description="Lookback period (e.g., in seconds or ticks) for calculations."
    )
    min_profit_target_pct: float = Field(
        0.0005, description="Minimum profit target percentage for a scalp (0.05%)."
    )
    max_position_size_usd: float = Field(
        100.0, description="Maximum size of a single position in USD."
    )
    confidence_threshold: Optional[float] = Field(
        0.6,
        description="Minimum model confidence score needed to trade (if model is used).",
    )


class MomentumStrategySettings(StrategySettings):
    """Parameters for a simple moving average crossover momentum strategy."""

    short_window: int = Field(10, description="Short moving average window size.")
    long_window: int = Field(30, description="Long moving average window size.")


class MeanReversionStrategySettings(StrategySettings):
    """Parameters for a basic mean reversion strategy."""

    window_size: int = Field(
        20, description="Rolling window size for mean calculation."
    )
    std_dev_threshold: float = Field(
        1.5,
        description="Standard deviation multiplier for entry/exit thresholds.",
    )


class VWAPStrategySettings(StrategySettings):
    """Parameters for VWAP-based strategy."""

    window_size: int = Field(
        20, description="Rolling window size for VWAP calculation."
    )
    deviation_threshold: float = Field(
        0.002, description="Fractional deviation from VWAP required to trigger a trade."
    )

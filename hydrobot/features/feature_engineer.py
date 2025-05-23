"""Feature engineering module.

Computes advanced market features from orderbook and trade data
for use in ML prediction models.
"""

from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)


class FeatureEngineer:
    """Market feature computation engine."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize feature engineer.

        Args:
            config: Feature configuration
        """
        self.config = config

        # Feature windows
        self.price_windows = config.get("price_windows", [10, 30, 60])
        self.volume_windows = config.get("volume_windows", [10, 30, 60])
        self.orderbook_windows = config.get("orderbook_windows", [5, 10, 20])

        # Feature buffers
        self._price_buffer: deque = deque(maxlen=max(self.price_windows))
        self._volume_buffer: deque = deque(maxlen=max(self.volume_windows))
        self._spread_buffer: deque = deque(maxlen=max(self.orderbook_windows))
        self._imbalance_buffer: deque = deque(maxlen=max(self.orderbook_windows))

        # State tracking
        self._last_price: Optional[float] = None
        self._last_update = datetime.min

    def update(self, market_data: Dict[str, Any]) -> None:
        """Update feature state with new market data.

        Args:
            market_data: Current market state
        """
        try:
            # Extract data
            orderbook = market_data.get("orderbook", {})
            trades = market_data.get("trades", {})

            # Update price features
            if trades.get("last_price"):
                self._price_buffer.append(trades["last_price"])
                self._last_price = trades["last_price"]

            # Update volume features
            if trades.get("volume"):
                self._volume_buffer.append(trades["volume"])

            # Update orderbook features
            if orderbook:
                if orderbook.get("spread"):
                    self._spread_buffer.append(orderbook["spread"])
                if orderbook.get("imbalance"):
                    self._imbalance_buffer.append(orderbook["imbalance"])

            self._last_update = datetime.utcnow()

        except Exception as e:
            logger.error("feature_update_error", error=str(e), market_data=market_data)

    def compute_features(self) -> Dict[str, float]:
        """Compute current feature values.

        Returns:
            Dictionary of feature names and values
        """
        features = {}

        try:
            # Price features
            price_data = list(self._price_buffer)
            if price_data:
                # Returns over different windows
                for window in self.price_windows:
                    if len(price_data) >= window:
                        window_data = price_data[-window:]
                        features[f"return_{window}"] = (
                            window_data[-1] / window_data[0] - 1
                        )

                # Momentum indicators
                features["momentum_rsi_14"] = self._compute_rsi(price_data, 14)
                features["momentum_macd"] = self._compute_macd(price_data)

            # Volume features
            volume_data = list(self._volume_buffer)
            if volume_data:
                for window in self.volume_windows:
                    if len(volume_data) >= window:
                        window_data = volume_data[-window:]
                        features[f"volume_ma_{window}"] = np.mean(window_data)
                        features[f"volume_std_{window}"] = np.std(window_data)

            # Orderbook features
            spread_data = list(self._spread_buffer)
            imbalance_data = list(self._imbalance_buffer)

            for window in self.orderbook_windows:
                # Spread features
                if len(spread_data) >= window:
                    window_data = spread_data[-window:]
                    features[f"spread_ma_{window}"] = np.mean(window_data)
                    features[f"spread_std_{window}"] = np.std(window_data)

                # Imbalance features
                if len(imbalance_data) >= window:
                    window_data = imbalance_data[-window:]
                    features[f"imbalance_ma_{window}"] = np.mean(window_data)
                    features[f"imbalance_std_{window}"] = np.std(window_data)

            # Technical indicators
            if price_data:
                features.update(self._compute_technical_indicators(price_data))

            logger.info("features_computed", feature_count=len(features))

            return features

        except Exception as e:
            logger.error("feature_computation_error", error=str(e))
            return {}

    def _compute_rsi(self, prices: List[float], window: int = 14) -> Optional[float]:
        """Compute Relative Strength Index.

        Args:
            prices: Price history
            window: RSI window

        Returns:
            RSI value if enough data
        """
        if len(prices) < window + 1:
            return None

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.clip(deltas, 0, None)
        losses = -np.clip(deltas, None, 0)

        # Calculate average gains and losses
        avg_gain = np.mean(gains[-window:])
        avg_loss = np.mean(losses[-window:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _compute_macd(
        self, prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Optional[float]:
        """Compute MACD indicator.

        Args:
            prices: Price history
            fast: Fast EMA window
            slow: Slow EMA window
            signal: Signal line window

        Returns:
            MACD histogram value if enough data
        """
        if len(prices) < slow + signal:
            return None

        # Calculate EMAs
        ema_fast = self._compute_ema(prices, fast)
        ema_slow = self._compute_ema(prices, slow)

        if ema_fast is None or ema_slow is None:
            return None

        # Calculate MACD line
        macd_line = ema_fast - ema_slow

        # Calculate signal line
        macd_hist = []
        for i in range(len(prices) - slow):
            window_macd = macd_line[i : i + signal]
            if len(window_macd) == signal:
                macd_hist.append(macd_line[i + signal - 1] - np.mean(window_macd))

        return macd_hist[-1] if macd_hist else None

    def _compute_ema(self, data: List[float], window: int) -> Optional[float]:
        """Compute Exponential Moving Average.

        Args:
            data: Input data
            window: EMA window

        Returns:
            Latest EMA value if enough data
        """
        if len(data) < window:
            return None

        alpha = 2 / (window + 1)
        ema = [data[0]]  # Initialize with first value

        for price in data[1:]:
            ema.append(price * alpha + ema[-1] * (1 - alpha))

        return ema[-1]

    def _compute_technical_indicators(self, prices: List[float]) -> Dict[str, float]:
        """Compute additional technical indicators.

        Args:
            prices: Price history

        Returns:
            Dictionary of indicator values
        """
        indicators = {}

        if len(prices) >= 20:
            # Bollinger Bands
            ma_20 = np.mean(prices[-20:])
            std_20 = np.std(prices[-20:])

            indicators["bb_upper"] = ma_20 + 2 * std_20
            indicators["bb_lower"] = ma_20 - 2 * std_20
            indicators["bb_width"] = (
                indicators["bb_upper"] - indicators["bb_lower"]
            ) / ma_20

            # Price position relative to bands
            if self._last_price:
                indicators["bb_position"] = (
                    self._last_price - indicators["bb_lower"]
                ) / (indicators["bb_upper"] - indicators["bb_lower"])

        if len(prices) >= 50:
            # Trend strength indicators
            ma_20 = np.mean(prices[-20:])
            ma_50 = np.mean(prices[-50:])

            indicators["trend_strength"] = (ma_20 / ma_50 - 1) * 100

        return indicators

    @property
    def is_ready(self) -> bool:
        """Check if enough data for feature computation."""
        min_window = max(
            self.price_windows + self.volume_windows + self.orderbook_windows
        )
        return (
            len(self._price_buffer) >= min_window
            and len(self._volume_buffer) >= min_window
        )

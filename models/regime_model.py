"""Market regime classification model.

Classifies market state (e.g., trending, ranging, volatile)
to adapt strategy parameters to current conditions.
"""
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum
from sklearn.cluster import KMeans
import joblib
from utilities.logger_setup import get_logger

logger = get_logger(__name__)

class MarketRegime(Enum):
    """Possible market regime states."""
    UNKNOWN = 0
    TRENDING_UP = 1
    TRENDING_DOWN = 2
    RANGING_LOW_VOL = 3
    RANGING_HIGH_VOL = 4
    VOLATILE = 5

class RegimeClassifier:
    def __init__(self, config: Dict[str, Any]):
        """Initialize regime classifier.
        
        Args:
            config: Model configuration parameters
        """
        self.config = config
        self.regime_window = config.get('regime_window', 3600)  # 1 hour
        self.min_samples = config.get('min_samples', 100)
        
        self.model = None
        self.feature_scaler = None
        self.last_training_time = None
        
        # Feature buffer for regime detection
        self._feature_buffer: List[Dict[str, float]] = []
        self._current_regime = MarketRegime.UNKNOWN
    
    def _extract_regime_features(self, 
                               price_data: List[float],
                               volume_data: List[float]
                               ) -> Dict[str, float]:
        """Extract features for regime classification.
        
        Args:
            price_data: List of historical prices
            volume_data: List of historical volumes
        
        Returns:
            Dict of regime classification features
        """
        if len(price_data) < 2:
            return {}
        
        # Price based features
        returns = np.diff(price_data) / price_data[:-1]
        
        features = {
            'volatility': np.std(returns),
            'trend_strength': abs(np.mean(returns)) / np.std(returns),
            'price_range': (max(price_data) - min(price_data)) / np.mean(price_data),
            'volume_intensity': np.mean(volume_data) / np.median(volume_data),
            'return_autocorr': np.corrcoef(returns[:-1], returns[1:])[0, 1]
        }
        
        return features
    
    def _classify_regime(self, features: Dict[str, float]) -> MarketRegime:
        """Determine market regime from features.
        
        Args:
            features: Regime classification features
        
        Returns:
            Classified market regime
        
        TODO: Implement more sophisticated regime classification
        - Use clustering/classification models
        - Consider multiple timeframes
        - Add confidence scores
        """
        try:
            if not features or self.model is None:
                return MarketRegime.UNKNOWN
            
            # For now, use simple rule-based classification
            volatility = features['volatility']
            trend_strength = features['trend_strength']
            volume_intensity = features['volume_intensity']
            
            if volatility > 0.02:  # High volatility threshold
                return MarketRegime.VOLATILE
            
            if trend_strength > 1.5:  # Strong trend threshold
                return MarketRegime.TRENDING_UP if np.mean(self._feature_buffer) > 0 \
                    else MarketRegime.TRENDING_DOWN
            
            # Ranging market
            return MarketRegime.RANGING_HIGH_VOL if volume_intensity > 1.2 \
                else MarketRegime.RANGING_LOW_VOL
                
        except Exception as e:
            logger.error("regime_classification_error", error=str(e))
            return MarketRegime.UNKNOWN
    
    def update(self, current_features: Dict[str, float]) -> None:
        """Update regime classifier with new data.
        
        Args:
            current_features: Latest market features
        """
        self._feature_buffer.append(current_features)
        
        # Maintain window size
        if len(self._feature_buffer) > self.regime_window:
            self._feature_buffer = self._feature_buffer[-self.regime_window:]
    
    def detect_regime(self, price_history: List[float],
                     volume_history: List[float]) -> Tuple[MarketRegime, Dict[str, float]]:
        """Detect current market regime.
        
        Args:
            price_history: Recent price data
            volume_history: Recent volume data
        
        Returns:
            Tuple of (regime, regime features)
        """
        try:
            # Extract regime features
            regime_features = self._extract_regime_features(
                price_history, volume_history)
            
            if not regime_features:
                return MarketRegime.UNKNOWN, {}
            
            # Classify regime
            self._current_regime = self._classify_regime(regime_features)
            
            return self._current_regime, regime_features
            
        except Exception as e:
            logger.error("regime_detection_error", error=str(e))
            return MarketRegime.UNKNOWN, {}
    
    def train(self, price_history: List[float],
              volume_history: List[float],
              known_regimes: Optional[List[MarketRegime]] = None) -> bool:
        """Train regime classifier model.
        
        Args:
            price_history: Historical price data
            volume_history: Historical volume data
            known_regimes: Optional list of labeled regimes
        
        Returns:
            True if training was successful
        
        TODO: Implement proper regime classification training
        - Supervised learning if labels available
        - Unsupervised clustering if no labels
        - Cross-validation and hyperparameter tuning
        """
        try:
            if len(price_history) < self.min_samples:
                logger.info("insufficient_training_data",
                          samples=len(price_history),
                          required=self.min_samples)
                return False
            
            # Extract features for training
            features_list = []
            for i in range(len(price_history) - self.regime_window):
                window_prices = price_history[i:i + self.regime_window]
                window_volumes = volume_history[i:i + self.regime_window]
                features = self._extract_regime_features(window_prices, window_volumes)
                if features:
                    features_list.append(list(features.values()))
            
            if not features_list:
                return False
            
            # Train clustering model
            X = np.array(features_list)
            self.model = KMeans(n_clusters=len(MarketRegime) - 1)  # Exclude UNKNOWN
            self.model.fit(X)
            
            self.last_training_time = datetime.utcnow()
            
            logger.info("regime_model_trained",
                       samples=len(features_list),
                       timestamp=self.last_training_time)
            return True
            
        except Exception as e:
            logger.error("regime_training_error", error=str(e))
            return False
    
    def save_model(self, path: str) -> bool:
        """Save model to disk.
        
        Args:
            path: Path to save model file
        
        Returns:
            True if save was successful
        """
        try:
            if self.model is None:
                return False
            
            joblib.dump({
                'model': self.model,
                'scaler': self.feature_scaler,
                'config': self.config,
                'training_time': self.last_training_time
            }, path)
            
            logger.info("regime_model_saved", path=path)
            return True
            
        except Exception as e:
            logger.error("regime_model_save_error", error=str(e))
            return False
    
    def load_model(self, path: str) -> bool:
        """Load model from disk.
        
        Args:
            path: Path to model file
        
        Returns:
            True if load was successful
        """
        try:
            data = joblib.load(path)
            
            self.model = data['model']
            self.feature_scaler = data['scaler']
            self.config = data['config']
            self.last_training_time = data['training_time']
            
            logger.info("regime_model_loaded",
                       path=path,
                       training_time=self.last_training_time)
            return True
            
        except Exception as e:
            logger.error("regime_model_load_error", error=str(e))
            return False
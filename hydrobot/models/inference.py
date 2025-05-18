"""Model inference coordination module.

Manages real-time predictions from price prediction and regime classification
models to provide unified trading signals.
"""
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio
from .prediction_model import PredictionModel
from .regime_model import RegimeClassifier, MarketRegime
from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)

class ModelInference:
    def __init__(self, config: Dict[str, Any]):
        """Initialize inference coordinator.
        
        Args:
            config: Model configuration parameters
        """
        self.config = config
        
        # Initialize models
        self.prediction_model = PredictionModel(config)
        self.regime_classifier = RegimeClassifier(config)
        
        # Prediction history for validation
        self._prediction_history: List[Dict[str, Any]] = []
        self._last_training_time = None
        
        # Training state
        self._is_training = False
    
    async def initialize_models(self, model_paths: Optional[Dict[str, str]] = None) -> bool:
        """Initialize or load pre-trained models.
        
        Args:
            model_paths: Optional paths to saved models
        
        Returns:
            True if initialization successful
        """
        try:
            if model_paths:
                # Load saved models
                price_model_loaded = self.prediction_model.load_model(
                    model_paths.get('prediction_model'))
                regime_model_loaded = self.regime_classifier.load_model(
                    model_paths.get('regime_model'))
                
                return price_model_loaded and regime_model_loaded
            
            return True
            
        except Exception as e:
            logger.error("model_initialization_error", error=str(e))
            return False
    
    def _should_train(self) -> bool:
        """Check if models need retraining.
        
        Returns:
            True if training is needed
        """
        if self._is_training:
            return False
            
        training_interval = self.config.get('training_interval', 86400)  # 1 day default
        
        if self._last_training_time is None:
            return True
        
        time_since_training = (datetime.utcnow() - self._last_training_time).total_seconds()
        return time_since_training >= training_interval
    
    async def train_models(self, historical_data: Dict[str, Any]) -> None:
        """Train or update models with new data.
        
        Args:
            historical_data: Dict containing historical market data
        """
        if not self._should_train():
            return
        
        try:
            self._is_training = True
            
            # Train price prediction model
            price_trained = await asyncio.get_event_loop().run_in_executor(
                None, self.prediction_model.train)
            
            # Train regime classifier
            regime_trained = await asyncio.get_event_loop().run_in_executor(
                None, self.regime_classifier.train,
                historical_data['prices'],
                historical_data['volumes'])
            
            if price_trained and regime_trained:
                self._last_training_time = datetime.utcnow()
                logger.info("models_trained",
                          timestamp=self._last_training_time)
            
        except Exception as e:
            logger.error("model_training_error", error=str(e))
        
        finally:
            self._is_training = False
    
    async def get_predictions(self, features: Dict[str, float],
                            market_data: Dict[str, Any]
                            ) -> Tuple[Optional[float], MarketRegime]:
        """Get price and regime predictions.
        
        Args:
            features: Current market features
            market_data: Recent market data for regime detection
        
        Returns:
            Tuple of (price prediction, market regime)
        """
        try:
            # Get price prediction
            price_prediction = await asyncio.get_event_loop().run_in_executor(
                None, self.prediction_model.predict, features)
            
            # Get regime prediction
            regime, _ = await asyncio.get_event_loop().run_in_executor(
                None, self.regime_classifier.detect_regime,
                market_data['prices'],
                market_data['volumes'])
            
            # Store prediction for validation
            self._prediction_history.append({
                'timestamp': datetime.utcnow(),
                'features': features,
                'price_prediction': price_prediction,
                'regime': regime
            })
            
            # Limit history size
            if len(self._prediction_history) > 1000:
                self._prediction_history = self._prediction_history[-1000:]
            
            return price_prediction, regime
            
        except Exception as e:
            logger.error("prediction_error", error=str(e))
            return None, MarketRegime.UNKNOWN
    
    def get_prediction_confidence(self, 
                                price_prediction: float,
                                regime: MarketRegime
                                ) -> float:
        """Estimate confidence in current predictions.
        
        Args:
            price_prediction: Current price prediction
            regime: Current market regime
        
        Returns:
            Confidence score between 0 and 1
        
        TODO: Implement proper confidence estimation
        - Use prediction model uncertainty
        - Consider regime stability
        - Validate against recent performance
        """
        if regime == MarketRegime.UNKNOWN:
            return 0.0
        
        # For now, use simple heuristic
        # Higher confidence in ranging markets, lower in volatile
        base_confidence = {
            MarketRegime.RANGING_LOW_VOL: 0.8,
            MarketRegime.RANGING_HIGH_VOL: 0.7,
            MarketRegime.TRENDING_UP: 0.6,
            MarketRegime.TRENDING_DOWN: 0.6,
            MarketRegime.VOLATILE: 0.4,
            MarketRegime.UNKNOWN: 0.0
        }
        
        return base_confidence[regime]
    
    async def save_models(self, paths: Dict[str, str]) -> bool:
        """Save current model states.
        
        Args:
            paths: Dict with paths for each model
        
        Returns:
            True if save successful
        """
        try:
            # Save price prediction model
            price_saved = await asyncio.get_event_loop().run_in_executor(
                None, self.prediction_model.save_model,
                paths.get('prediction_model'))
            
            # Save regime classifier
            regime_saved = await asyncio.get_event_loop().run_in_executor(
                None, self.regime_classifier.save_model,
                paths.get('regime_model'))
            
            return price_saved and regime_saved
            
        except Exception as e:
            logger.error("model_save_error", error=str(e))
            return False
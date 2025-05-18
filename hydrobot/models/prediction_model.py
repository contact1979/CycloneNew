"""Price prediction model.

Handles short-term price movement forecasting using
gradient boosting for high-frequency trading decisions.
"""
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import lightgbm as lgb
from datetime import datetime
from sklearn.preprocessing import StandardScaler
import joblib
from hydrobot.utils.logger_setup import get_logger

logger = get_logger(__name__)

class PredictionModel:
    """Price movement prediction model."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize prediction model.
        
        Args:
            config: Model configuration
        """
        self.config = config
        
        # Model parameters
        self.feature_columns = config['feature_columns']
        self.target_horizon = config.get('target_horizon', 10)  # ticks
        self.threshold = config.get('movement_threshold', 0.0001)
        
        # Initialize model components
        self.scaler: Optional[StandardScaler] = None
        self.model: Optional[lgb.Booster] = None
        
        # Performance tracking
        self._predictions: List[Tuple[datetime, float]] = []
        self._accuracies: List[float] = []
        
        self._initialize_model()
    
    def _initialize_model(self) -> None:
        """Initialize or load pre-trained model."""
        try:
            model_path = self.config.get('model_path')
            if model_path:
                self.model = lgb.Booster(model_file=model_path)
                self.scaler = joblib.load(f"{model_path}_scaler.pkl")
                logger.info("model_loaded",
                          path=model_path)
            else:
                self._train_new_model()
                
        except Exception as e:
            logger.error("model_init_error",
                        error=str(e))
    
    def _train_new_model(self) -> None:
        """Train a new prediction model."""
        try:
            # Training parameters
            params = {
                'boosting_type': 'gbdt',
                'objective': 'binary',
                'metric': 'auc',
                'num_leaves': 32,
                'learning_rate': 0.1,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1
            }
            
            # Load training data
            X_train, y_train = self._load_training_data()
            
            if X_train is None or y_train is None:
                raise ValueError("No training data available")
            
            # Initialize and fit scaler
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X_train)
            
            # Create dataset
            train_data = lgb.Dataset(X_scaled, label=y_train)
            
            # Train model
            self.model = lgb.train(
                params,
                train_data,
                num_boost_round=100,
                valid_sets=[train_data],
                early_stopping_rounds=10
            )
            
            logger.info("model_trained",
                       params=params)
            
            # Save model if path specified
            if self.config.get('model_path'):
                self._save_model()
                
        except Exception as e:
            logger.error("model_training_error",
                        error=str(e))
    
    def _load_training_data(self) -> Tuple[Optional[np.ndarray],
                                         Optional[np.ndarray]]:
        """Load historical training data.
        
        Returns:
            Features and labels for training
        """
        try:
            data_path = self.config.get('training_data_path')
            if not data_path:
                return None, None
            
            # Load and preprocess historical data
            data = np.load(data_path)
            
            X = data['features']
            y = data['labels']
            
            return X, y
            
        except Exception as e:
            logger.error("data_loading_error",
                        error=str(e))
            return None, None
    
    def _save_model(self) -> None:
        """Save trained model and scaler."""
        try:
            model_path = self.config['model_path']
            self.model.save_model(model_path)
            joblib.dump(self.scaler, f"{model_path}_scaler.pkl")
            
            logger.info("model_saved",
                       path=model_path)
            
        except Exception as e:
            logger.error("model_save_error",
                        error=str(e))
    
    def predict(self, features: Dict[str, float]) -> Optional[float]:
        """Make price movement prediction.
        
        Args:
            features: Current market features
        
        Returns:
            Prediction probability if successful
        """
        try:
            if not self.model or not self.scaler:
                return None
            
            # Extract and validate features
            feature_vector = []
            for col in self.feature_columns:
                if col not in features:
                    logger.warning("missing_feature",
                                 feature=col)
                    return None
                feature_vector.append(features[col])
            
            # Scale features
            X = self.scaler.transform([feature_vector])
            
            # Make prediction
            prob = self.model.predict(X)[0]
            
            # Track prediction
            self._predictions.append(
                (datetime.utcnow(), prob)
            )
            
            return prob
            
        except Exception as e:
            logger.error("prediction_error",
                        error=str(e),
                        features=features)
            return None
    
    def update_accuracy(self, actual_movement: float) -> None:
        """Update model accuracy tracking.
        
        Args:
            actual_movement: Realized price movement
        """
        try:
            if not self._predictions:
                return
            
            # Get most recent prediction
            _, prob = self._predictions[-1]
            
            # Compare prediction to actual
            predicted_direction = 1 if prob > 0.5 else 0
            actual_direction = 1 if actual_movement > self.threshold else 0
            
            # Update accuracy
            accuracy = 1.0 if predicted_direction == actual_direction else 0.0
            self._accuracies.append(accuracy)
            
            # Keep last 1000 accuracy measurements
            if len(self._accuracies) > 1000:
                self._accuracies.pop(0)
            
            logger.info("accuracy_updated",
                       current_accuracy=accuracy,
                       rolling_accuracy=self.get_accuracy())
            
        except Exception as e:
            logger.error("accuracy_update_error",
                        error=str(e))
    
    def get_accuracy(self, window: int = 100) -> float:
        """Get recent prediction accuracy.
        
        Args:
            window: Number of recent predictions to consider
        
        Returns:
            Rolling accuracy metric
        """
        if not self._accuracies:
            return 0.0
        
        recent = self._accuracies[-window:]
        return sum(recent) / len(recent)
    
    def should_retrain(self) -> bool:
        """Check if model should be retrained.
        
        Returns:
            True if retraining is recommended
        """
        # Check accuracy threshold
        min_accuracy = self.config.get('min_accuracy', 0.55)
        if self.get_accuracy() < min_accuracy:
            return True
        
        # Check prediction count threshold
        retrain_interval = self.config.get('retrain_interval', 10000)
        if len(self._predictions) >= retrain_interval:
            return True
        
        return False
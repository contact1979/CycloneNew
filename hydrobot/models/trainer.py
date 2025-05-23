"""ML model training coordinator.

Handles model training lifecycle, including feature loading, training,
validation, serialization, and metrics logging.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import mlflow
import numpy as np
import pandas as pd
import torch
from mlflow.tracking import MlflowClient
from sklearn.model_selection import train_test_split

from hydrobot.utils.logger_setup import get_logger
from hydrobot.utils.metrics import MODEL_ACCURACY

from .prediction_model import PredictionModel
from .regime_model import RegimeClassifier

logger = get_logger(__name__)


class ModelTrainer:
    """ML model training coordinator."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize model trainer.

        Args:
            config: Training configuration
        """
        self.config = config

        # Model paths
        self.models_dir = Path(config.get("models_dir", "models"))
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # MLflow setup
        mlflow.set_tracking_uri(config.get("mlflow_uri", "mlruns"))
        self.experiment = config.get("mlflow_experiment", "hft_models")
        mlflow.set_experiment(self.experiment)

        # Training parameters
        self.train_split = config.get("train_split", 0.8)
        self.val_split = config.get("val_split", 0.1)
        self.min_samples = config.get("min_samples", 1000)

        # Initialize models
        self.prediction_model = PredictionModel(config)
        self.regime_model = RegimeClassifier(config)

    def _load_training_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load and preprocess training data.

        Returns:
            Tuple of (features, labels) DataFrames
        """
        try:
            data_path = Path(self.config["data_path"])

            # Load processed feature data
            features = pd.read_parquet(data_path / "processed_features.parquet")

            # Load labels
            labels = pd.read_parquet(data_path / "labels.parquet")

            return features, labels

        except Exception as e:
            logger.error("data_loading_error", error=str(e))
            return pd.DataFrame(), pd.DataFrame()

    def _split_data(
        self, features: pd.DataFrame, labels: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split data into train/val/test sets.

        Args:
            features: Feature DataFrame
            labels: Label DataFrame

        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        # First split into train and temp
        X_train, X_temp, y_train, y_temp = train_test_split(
            features.values,
            labels.values,
            train_size=self.train_split,
            shuffle=False,  # Maintain time series order
        )

        # Split temp into val and test
        val_ratio = self.val_split / (1 - self.train_split)
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, train_size=val_ratio, shuffle=False
        )

        return X_train, X_val, X_test, y_train, y_val, y_test

    async def train_prediction_model(self) -> bool:
        """Train price prediction model.

        Returns:
            True if training successful
        """
        try:
            # Load data
            features, labels = self._load_training_data()
            if len(features) < self.min_samples:
                logger.warning(
                    "insufficient_training_data",
                    samples=len(features),
                    required=self.min_samples,
                )
                return False

            # Split data
            X_train, X_val, X_test, y_train, y_val, y_test = self._split_data(
                features, labels
            )

            # Start MLflow run
            with mlflow.start_run(run_name="prediction_model") as run:
                # Log parameters
                mlflow.log_params(self.config)

                # Train model
                self.prediction_model.train(X_train, y_train)

                # Evaluate
                train_metrics = self.prediction_model.evaluate(X_train, y_train)
                val_metrics = self.prediction_model.evaluate(X_val, y_val)
                test_metrics = self.prediction_model.evaluate(X_test, y_test)

                # Log metrics
                mlflow.log_metrics(
                    {
                        "train_accuracy": train_metrics["accuracy"],
                        "train_f1": train_metrics["f1"],
                        "val_accuracy": val_metrics["accuracy"],
                        "val_f1": val_metrics["f1"],
                        "test_accuracy": test_metrics["accuracy"],
                        "test_f1": test_metrics["f1"],
                    }
                )

                # Update Prometheus metrics
                MODEL_ACCURACY.labels(
                    symbol="all", model="prediction", window="test"
                ).set(test_metrics["accuracy"])

                # Save model
                model_path = self.models_dir / f"prediction_model_{run.info.run_id}.pkl"
                self.prediction_model.save_model(str(model_path))
                mlflow.log_artifact(model_path)

                logger.info(
                    "prediction_model_trained",
                    metrics=test_metrics,
                    model_path=str(model_path),
                )

                return True

        except Exception as e:
            logger.error("prediction_model_training_error", error=str(e))
            return False

    async def train_regime_model(self) -> bool:
        """Train regime classification model.

        Returns:
            True if training successful
        """
        try:
            # Load data
            features, _ = self._load_training_data()
            if len(features) < self.min_samples:
                logger.warning(
                    "insufficient_training_data",
                    samples=len(features),
                    required=self.min_samples,
                )
                return False

            # Extract price and volume data
            price_data = features["price"].values
            volume_data = features["volume"].values

            # Start MLflow run
            with mlflow.start_run(run_name="regime_model") as run:
                # Log parameters
                mlflow.log_params(self.config)

                # Train model
                success = await self.regime_model.train(price_data, volume_data)

                if not success:
                    return False

                # Save model
                model_path = self.models_dir / f"regime_model_{run.info.run_id}.pkl"
                self.regime_model.save_model(str(model_path))
                mlflow.log_artifact(model_path)

                logger.info("regime_model_trained", model_path=str(model_path))

                return True

        except Exception as e:
            logger.error("regime_model_training_error", error=str(e))
            return False

    async def load_latest_models(self) -> bool:
        """Load latest model versions.

        Returns:
            True if loading successful
        """
        try:
            client = MlflowClient()

            # Get latest prediction model
            runs = client.search_runs(
                experiment_ids=[
                    client.get_experiment_by_name(self.experiment).experiment_id
                ],
                filter_string="tags.mlflow.runName = 'prediction_model'",
                order_by=["start_time DESC"],
                max_results=1,
            )

            if runs:
                latest_run = runs[0]
                artifacts = client.list_artifacts(latest_run.info.run_id)
                model_path = next(
                    (a.path for a in artifacts if a.path.endswith(".pkl")), None
                )

                if model_path:
                    full_path = os.path.join(
                        client.get_run(latest_run.info.run_id).info.artifact_uri,
                        model_path,
                    ).replace("file://", "")

                    self.prediction_model.load_model(full_path)

            # Get latest regime model
            runs = client.search_runs(
                experiment_ids=[
                    client.get_experiment_by_name(self.experiment).experiment_id
                ],
                filter_string="tags.mlflow.runName = 'regime_model'",
                order_by=["start_time DESC"],
                max_results=1,
            )

            if runs:
                latest_run = runs[0]
                artifacts = client.list_artifacts(latest_run.info.run_id)
                model_path = next(
                    (a.path for a in artifacts if a.path.endswith(".pkl")), None
                )

                if model_path:
                    full_path = os.path.join(
                        client.get_run(latest_run.info.run_id).info.artifact_uri,
                        model_path,
                    ).replace("file://", "")

                    self.regime_model.load_model(full_path)

            return True

        except Exception as e:
            logger.error("model_loading_error", error=str(e))
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get current model information.

        Returns:
            Dict with model details
        """
        return {
            "prediction_model": {
                "training_time": self.prediction_model.last_training_time,
                "accuracy": self.prediction_model.get_accuracy(),
            },
            "regime_model": {"training_time": self.regime_model.last_training_time},
        }

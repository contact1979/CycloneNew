"""Core ML prediction utilities."""

import json
import logging
import os
import datetime
import pytz
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from feature_engineering.feature_generator import preprocess_backfill_data

# Use absolute imports assuming 'cyclonev2' is the project root added to PYTHONPATH
from hydrobot import config
from hydrobot.models.trainer import (  # Import constants
    MODEL_DIR,
    MODEL_FILENAME,
    MODEL_METADATA_FILENAME,
)

log = logging.getLogger(__name__)

# --- Model Loading ---
_loaded_model = None
_model_metadata = None


def load_model_and_metadata() -> Optional[Tuple[Any, Dict]]:
    """Load the saved model and its metadata if not already loaded."""

    global _loaded_model, _model_metadata
    if _loaded_model is None:
        model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)
        metadata_path = os.path.join(MODEL_DIR, MODEL_METADATA_FILENAME)

        if not os.path.exists(model_path) or not os.path.exists(metadata_path):
            log.error(
                "Model file '%s' or metadata file '%s' not found. Cannot load model.",
                model_path,
                metadata_path,
            )
            return None

        try:
            log.info("Loading model from: %s", model_path)
            _loaded_model = joblib.load(model_path)
            log.info("Model loaded successfully.")

            log.info("Loading metadata from: %s", metadata_path)
            with open(metadata_path, "r") as f:
                _model_metadata = json.load(f)
            log.info(
                "Metadata loaded successfully. Model trained on %s features.",
                len(_model_metadata.get("feature_names", [])),
            )

        except Exception as e:
            log.error("Error loading model or metadata: %s", e, exc_info=True)
            _loaded_model = None
            _model_metadata = None

    return _loaded_model, _model_metadata


def load_model(model_path="trained_models/random_forest_model.joblib"):
    """
    Load the trained model from the specified path.

    Args:
        model_path (str): Path to the trained model file.

    Returns:
        model: The loaded model.
    """
    try:
        model = joblib.load(model_path)
        print(f"Model loaded from {model_path}")
        return model
    except Exception as e:
        print(f"Error loading model: {e}")
        return None


# --- Prediction Function ---


def make_prediction(latest_features_df: pd.DataFrame) -> Optional[Tuple[int, float]]:
    """
    Makes a prediction using the loaded model on the latest feature data.

    Args:
        latest_features_df (pd.DataFrame): A DataFrame containing the most recent
                                           feature set for a single timestamp/symbol.
                                           Must contain the columns the model was trained on.

    Returns:
        Optional[Tuple[int, float]]: A tuple containing:
                                     - prediction (int): The predicted class (0 or 1).
                                     - confidence (float): The probability of the predicted class 1.
                                     Returns None if prediction fails.
    """
    model_info = load_model_and_metadata()
    if not model_info:
        log.error("Model not loaded. Cannot make prediction.")
        return None

    model, metadata = model_info
    required_features = metadata.get("feature_names")

    if not required_features:
        log.error(
            "Model metadata does not contain feature names. Cannot ensure feature consistency."
        )
        return None

    if latest_features_df.empty:
        log.error("Received empty DataFrame for prediction.")
        return None

    # Ensure input DataFrame has the correct features in the correct order
    try:
        # Select only the required features
        features_for_prediction = latest_features_df[required_features]

        # Check for NaNs in the input features for this prediction step
        if features_for_prediction.isnull().values.any():
            nan_cols = features_for_prediction.columns[
                features_for_prediction.isnull().any()
            ].tolist()
            log.warning(
                f"NaN values detected in features for prediction: {nan_cols}. Attempting imputation with 0."
            )
            # Apply the same imputation used during training (assuming 0 for simplicity)
            features_for_prediction = features_for_prediction.fillna(0)
            # If a different imputation was used in training, apply that here.

        # Ensure only one row is passed for prediction
        if len(features_for_prediction) > 1:
            log.warning(
                f"Prediction input DataFrame has {len(features_for_prediction)} rows. Using the last row."
            )
            features_for_prediction = features_for_prediction.tail(1)

        log.debug(
            f"Making prediction on features: {features_for_prediction.columns.tolist()}"
        )

        # Predict probability (returns array of shape [n_samples, n_classes])
        probabilities = model.predict_proba(features_for_prediction)

        # Probability of class 1 (assuming class 1 is 'UP')
        prob_class_1 = probabilities[0, 1]

        # Get predicted class (0 or 1)
        prediction = int(model.predict(features_for_prediction)[0])

        log.info(
            f"Prediction successful. Class: {prediction}, Probability(Class 1): {prob_class_1:.4f}"
        )
        return prediction, prob_class_1

    except KeyError as e:
        log.error(
            f"Feature mismatch during prediction. Missing feature: {e}. Required: {required_features}",
            exc_info=True,
        )
        return None
    except Exception as e:
        log.error(f"Error during prediction: {e}", exc_info=True)
        return None


def make_predictions():
    """
    Use the trained model to make predictions on new data.
    """
    # Load the trained model
    model = load_model()
    if model is None:
        return

    # Preprocess the data
    data = preprocess_backfill_data()

    # Ensure the target column is not included in the prediction data
    if "target" in data.columns:
        data = data.drop(columns=["target"])

    # Make predictions
    predictions = model.predict(data)
    print("Predictions:")
    print(predictions)


# --- Example Usage (for testing) ---
if __name__ == "__main__":
    # Setup basic logging for direct script run
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s - %(levelname)s [%(name)s] %(message)s",
    )

    print("--- Testing Model Predictor ---")

    # --- Prerequisites ---
    # 1. Ensure a model has been trained and saved by trainer.py
    # 2. Need feature data for prediction. We can try generating features for the latest point.

    # Attempt to load model and metadata
    model_info = load_model_and_metadata()
    if not model_info:
        print("Model or metadata not found or failed to load. Run trainer.py first.")
    else:
        _, metadata = model_info
        print("Model and metadata loaded.")

        # --- Generate Sample Features for Prediction ---
        # In a real run, this would come from feature_generator using the latest available data
        print("\nGenerating sample features for prediction (using latest data)...")
        from feature_engineering import feature_generator  # Import here for testing
        import datetime
        import pytz

        test_symbol = "BTCUSDT"  # Use a symbol likely trained on
        # Use current time to get the very latest features possible
        pred_time = datetime.datetime.now(pytz.utc)
        # Need enough history to calculate lags/rolling features for the *single* prediction point
        hist_for_pred = pd.Timedelta(
            days=3
        )  # Adjust as needed based on longest lookback

        latest_features = feature_generator.generate_features_for_symbol(
            symbol=test_symbol, end_time_utc=pred_time, history_duration=hist_for_pred
        )

        if latest_features is not None and not latest_features.empty:
            # Get the single most recent row of features
            prediction_input_df = latest_features.tail(1)
            print(
                f"Generated {len(prediction_input_df)} row(s) of features for prediction."
            )
            # print(prediction_input_df) # Optionally print the feature row

            # --- Make Prediction ---
            prediction_result = make_prediction(prediction_input_df)

            if prediction_result:
                pred_class, pred_prob = prediction_result
                print(f"\nPrediction for {test_symbol} at ~{pred_time}:")
                print(f"  Predicted Class: {pred_class} (0=DOWN/SIDEWAYS, 1=UP)")
                print(f"  Probability (Class 1): {pred_prob:.4f}")
            else:
                print("\nFailed to make prediction. Check logs.")
        else:
            print(
                "\nFailed to generate features for prediction input. Cannot test predictor."
            )

    make_predictions()

    print("\n--- Test Complete ---")

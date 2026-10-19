"""
train_models.py — Per-Key ARIMA + LSTM Training Pipeline.

For each unique cache key in the processed features dataset:
  1. Trains an ARIMA(5,1,0) baseline on request_count.
  2. Trains an LSTM on [request_count, hour_sin, hour_cos, dow_sin, dow_cos].
  3. Evaluates both models on a held-out test set.
     CRITICAL: Both RMSEs are computed on the ORIGINAL (unscaled) scale so
     that the comparison is meaningful.
  4. Selects the better model (Dynamic Model Selector).
  5. Saves models, scalers, and a JSON metadata file.

Output files:
  - models/lstm_<safe_key>.keras
  - models/scaler_<safe_key>.pkl
  - models/model_metadata.json

Windows note: cache keys like "user:1:data" are sanitised to "user_1_data"
before being used in file names.
"""

import json
import logging
import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from statsmodels.tsa.arima.model import ARIMA
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import Dense, Dropout, LSTM
from tensorflow.keras.models import Sequential

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("train_models")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def sanitise_key(key: str) -> str:
    """
    Replace characters that are illegal in Windows filenames.
    e.g. "user:1:data" -> "user_1_data"
    """
    return key.replace(":", "_").replace("/", "_").replace("\\", "_")


def prepare_lstm_sequences(scaled_data: np.ndarray, seq_len: int):
    """
    Build (X, y) sequences for LSTM training.

    Args:
        scaled_data: 2-D array of shape (timesteps, features).
        seq_len: Number of historical timesteps per input window.

    Returns:
        X: shape (samples, seq_len, features)
        y: shape (samples, features)  — the full feature vector at t+1
    """
    X, y = [], []
    for i in range(seq_len, len(scaled_data)):
        X.append(scaled_data[i - seq_len : i])
        y.append(scaled_data[i])
    return np.array(X), np.array(y)


# ─────────────────────────────────────────────────────────────────────────────
# Per-Key Training
# ─────────────────────────────────────────────────────────────────────────────

def train_models_for_key(
    key: str,
    df: pd.DataFrame,
    seq_len: int = 60,
    epochs: int = 30,
    batch_size: int = 32,
    train_split: float = 0.7,
    model_dir: str = "models",
) -> dict:
    """
    Train ARIMA and LSTM for one cache key, select the winner, and persist
    both the model file and its scaler.

    Returns:
        A dict with keys: key, safe_key, arima_rmse, lstm_rmse,
                          selected_model, winner_rmse.
    """
    safe_key = sanitise_key(key)
    logger.info("─── Training for key='%s' (safe='%s') ───", key, safe_key)

    # ── Filter & sort data for this key ─────────────────────────────────────
    key_data = df[df["cache_key"] == key].copy().sort_values("bucket")
    n_rows = len(key_data)
    logger.info("  Data rows: %d", n_rows)

    feature_cols = ["request_count", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    split_idx = int(n_rows * train_split)

    train_data = key_data.iloc[:split_idx]
    test_data  = key_data.iloc[split_idx:]

    logger.info(
        "  Train/test split: %d / %d rows (%.0f%%)",
        len(train_data), len(test_data), train_split * 100,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 1. ARIMA — trained on raw request_count
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("  [ARIMA] Fitting ARIMA(5,1,0)...")
    arima_fit   = None
    arima_saved = False
    try:
        arima_model = ARIMA(train_data["request_count"], order=(5, 1, 0))
        arima_fit   = arima_model.fit()
        arima_preds = arima_fit.forecast(steps=len(test_data))
        arima_preds = np.maximum(arima_preds, 0)  # Counts can't be negative
        arima_rmse  = float(
            np.sqrt(np.mean((arima_preds - test_data["request_count"].values) ** 2))
        )
        logger.info("  [ARIMA] RMSE (raw scale) = %.4f", arima_rmse)
    except Exception as exc:
        logger.warning("  [ARIMA] Fit failed: %s — defaulting RMSE to inf", exc)
        arima_rmse = float("inf")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LSTM — trained on MinMaxScaled features, RMSE on ORIGINAL scale
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("  [LSTM] Scaling data and preparing sequences...")
    scaler      = MinMaxScaler(feature_range=(0, 1))
    scaled_all  = scaler.fit_transform(key_data[feature_cols].values)

    X, y = prepare_lstm_sequences(scaled_all, seq_len)

    train_seq_n         = int(len(X) * train_split)
    X_train, X_test     = X[:train_seq_n], X[train_seq_n:]
    y_train, y_test_sc  = y[:train_seq_n], y[train_seq_n:]   # still scaled

    logger.info(
        "  [LSTM] Sequences: train=%d, test=%d, shape=%s",
        len(X_train), len(X_test), X_train.shape,
    )

    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])),
        Dropout(0.2),
        LSTM(32),
        Dense(len(feature_cols)),   # Predict all features so inversion is exact
    ])
    model.compile(optimizer="adam", loss="mse")

    early_stop = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)

    logger.info("  [LSTM] Training (max %d epochs)...", epochs)
    model.fit(
        X_train, y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=0.2,
        callbacks=[early_stop],
        verbose=0,
    )
    logger.info("  [LSTM] Training complete.")

    # Predict on test set (scaled) then invert to raw scale
    lstm_preds_scaled = model.predict(X_test, verbose=0)          # shape (n, n_features)
    lstm_preds_raw    = scaler.inverse_transform(lstm_preds_scaled)  # shape (n, n_features)
    y_test_raw        = scaler.inverse_transform(y_test_sc)          # shape (n, n_features)

    # ★ RMSE on original scale — request_count is column index 0
    lstm_rmse = float(
        np.sqrt(np.mean((lstm_preds_raw[:, 0] - y_test_raw[:, 0]) ** 2))
    )
    logger.info(
        "  [LSTM] RMSE (raw scale, request_count) = %.4f", lstm_rmse
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Dynamic Model Selector
    # ─────────────────────────────────────────────────────────────────────────
    if lstm_rmse < arima_rmse:
        winner      = "LSTM"
        winner_rmse = lstm_rmse
    else:
        winner      = "ARIMA"
        winner_rmse = arima_rmse

    logger.info(
        "  [SELECTOR] Winner=%s (LSTM=%.4f, ARIMA=%.4f)",
        winner, lstm_rmse, arima_rmse,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Persist model + scaler + ARIMA fit
    # ─────────────────────────────────────────────────────────────────────────
    model_path  = os.path.join(model_dir, f"lstm_{safe_key}.keras")
    scaler_path = os.path.join(model_dir, f"scaler_{safe_key}.pkl")
    arima_path  = os.path.join(model_dir, f"arima_{safe_key}.pkl")

    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    logger.info("  Saved LSTM model  → %s", model_path)
    logger.info("  Saved scaler      → %s", scaler_path)

    # Always persist ARIMA fit so the API can serve it if ARIMA wins
    if arima_fit is not None:
        joblib.dump(arima_fit, arima_path)
        arima_saved = True
        logger.info("  Saved ARIMA fit   → %s", arima_path)
    else:
        logger.warning("  ARIMA fit not available — skipping ARIMA pkl save.")

    return {
        "key":            key,
        "safe_key":       safe_key,
        "arima_rmse":     arima_rmse,
        "lstm_rmse":      lstm_rmse,
        "selected_model": winner,
        "winner_rmse":    winner_rmse,
        "arima_saved":    arima_saved,
        "trained_at":     datetime.utcnow().isoformat() + "Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import cfg

    logger.info("=== Model Training Pipeline Start ===")
    logger.info("Loading processed features from: %s", cfg.PROCESSED_FEATURES_PATH)

    df = pd.read_csv(cfg.PROCESSED_FEATURES_PATH, parse_dates=["bucket"])
    keys = df["cache_key"].unique()
    logger.info("Found %d unique cache keys to train.", len(keys))

    results = []
    for i, key in enumerate(keys, start=1):
        logger.info(">>> [%d/%d] Processing key: %s", i, len(keys), key)
        result = train_models_for_key(
            key=key,
            df=df,
            seq_len=cfg.SEQUENCE_LENGTH,
            epochs=cfg.LSTM_EPOCHS,
            batch_size=cfg.LSTM_BATCH_SIZE,
            train_split=cfg.TRAIN_SPLIT,
            model_dir=str(cfg.MODEL_DIR),
        )
        results.append(result)
        logger.info(
            "<<< [%d/%d] Done: key='%s' selected=%s winner_rmse=%.4f",
            i, len(keys), key, result["selected_model"], result["winner_rmse"],
        )

    # ── Save metadata as JSON ─────────────────────────────────────────────────
    metadata = {
        "version":     "1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "models":       results,
    }
    metadata_path = cfg.METADATA_PATH
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Metadata saved → %s", metadata_path)
    logger.info("=== Model Training Pipeline Complete ===")

    # Summary table
    logger.info("\n%-20s | %-10s | %-10s | %-10s", "Key", "ARIMA RMSE", "LSTM RMSE", "Winner")
    logger.info("-" * 60)
    for r in results:
        logger.info(
            "%-20s | %-10.4f | %-10.4f | %-10s",
            r["key"], r["arima_rmse"], r["lstm_rmse"], r["selected_model"],
        )
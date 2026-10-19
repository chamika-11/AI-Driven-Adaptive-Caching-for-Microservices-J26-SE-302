import json
import logging
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from statsmodels.tsa.arima.model import ARIMA  # noqa: F401  (needed for joblib unpickling)
from tensorflow.keras.models import load_model

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("api")

# ── Config & Custom Modules ───────────────────────────────────────────────────
# Add src/ to path so imports work when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import cfg
from fusion_engine import TTLFusionEngine
from hotkey_detector import HotKeyDetector
from volatility import VolatilityEngine

app = Flask(__name__)

logger.info("=== API Startup: Loading models and data ===")
_startup_start = time.perf_counter()

# 1. Model metadata (JSON)
logger.info("Loading model metadata from: %s", cfg.METADATA_PATH)
try:
    with open(cfg.METADATA_PATH) as f:
        _raw_meta = json.load(f)
    _metadata: list[dict] = _raw_meta["models"]
    _model_version: str   = _raw_meta.get("version", "unknown")
    _generated_at: str    = _raw_meta.get("generated_at", "unknown")
    logger.info(
        "Metadata loaded: version=%s, %d keys, generated_at=%s",
        _model_version, len(_metadata), _generated_at,
    )
except Exception as exc:
    logger.error("FATAL: Could not load model metadata: %s", exc)
    _metadata, _model_version, _generated_at = [], "error", "unknown"

# 2. Per-key models and scalers
logger.info("Loading per-key LSTM models and scalers...")
_models:  dict[str, object] = {}
_scalers: dict[str, object] = {}
_key_model_map: dict[str, str] = {}

for entry in _metadata:
    key       = entry["key"]
    safe_key  = entry.get("safe_key", key.replace(":", "_").replace("/", "_"))
    selected  = entry["selected_model"]
    _key_model_map[key] = selected

    if selected == "LSTM":
        model_path  = cfg.MODEL_DIR / f"lstm_{safe_key}.keras"
        scaler_path = cfg.MODEL_DIR / f"scaler_{safe_key}.pkl"
        try:
            _models[key]  = load_model(str(model_path))
            _scalers[key] = joblib.load(str(scaler_path))
            logger.info("  Loaded LSTM model  for key='%s'", key)
        except Exception as exc:
            logger.warning("  Could not load LSTM for key='%s': %s", key, exc)
    else:  # ARIMA
        arima_path = cfg.MODEL_DIR / f"arima_{safe_key}.pkl"
        try:
            _models[key] = joblib.load(str(arima_path))
            logger.info("  Loaded ARIMA model for key='%s'", key)
        except Exception as exc:
            logger.warning(
                "  Could not load ARIMA pkl for key='%s': %s — will use fallback", key, exc
            )
            _models[key] = None  # None signals fallback in _predict_popularity

# 3. Historical feature data (for LSTM input construction)
logger.info("Loading processed features from: %s", cfg.PROCESSED_FEATURES_PATH)
try:
    _feature_df = pd.read_csv(cfg.PROCESSED_FEATURES_PATH, parse_dates=["bucket"])
    logger.info("Feature data loaded: %d rows.", len(_feature_df))
except Exception as exc:
    logger.error("Could not load feature data: %s", exc)
    _feature_df = pd.DataFrame()

# 4. DB update logs — pre-loaded to avoid per-request disk reads
logger.info("Loading DB update logs from: %s", cfg.DB_UPDATES_PATH)
try:
    _db_updates_df = pd.read_csv(cfg.DB_UPDATES_PATH, parse_dates=["timestamp"])
    logger.info("DB update log loaded: %d rows.", len(_db_updates_df))
except Exception as exc:
    logger.error("Could not load DB update log: %s", exc)
    _db_updates_df = pd.DataFrame(columns=["timestamp", "cache_key"])

# 5. Engine instances
_volatility_engine = VolatilityEngine(alpha=cfg.EWMA_ALPHA)
_hotkey_detector   = HotKeyDetector(
    threshold=cfg.HOTKEY_THRESHOLD,
    window_seconds=cfg.HOTKEY_WINDOW_SECONDS,
)
_ttl_engine = TTLFusionEngine(min_ttl=cfg.MIN_TTL, max_ttl=cfg.MAX_TTL)

_startup_ms = (time.perf_counter() - _startup_start) * 1000
logger.info("=== API Startup complete in %.0f ms ===", _startup_ms)

# ── Shared state guards ───────────────────────────────────────────────────────
_reload_lock: threading.Lock = threading.Lock()

# Per-key TTL overrides written by POST /api/v1/prewarm/<key>.
# Structure: {cache_key: {"ttl": int, "expires_at": float (epoch)}}
_ttl_overrides: dict[str, dict] = {}

# Feature columns must match training order in train_models.py
_FEATURE_COLS = ["request_count", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
_N_FEATURES   = len(_FEATURE_COLS)
_SEQ_LEN      = cfg.SEQUENCE_LENGTH
_MAX_COUNT    = 150  # Used to normalise raw count into a popularity score

def _get_features_for_key(key: str) -> np.ndarray | None:
    """
    Return the last `_SEQ_LEN` rows of feature data for `key`.
    Returns None if insufficient history exists.
    """
    if _feature_df.empty:
        return None
    key_data = _feature_df[_feature_df["cache_key"] == key].sort_values("bucket")
    if len(key_data) < _SEQ_LEN:
        logger.debug(
            "Insufficient history for key='%s': have %d, need %d",
            key, len(key_data), _SEQ_LEN,
        )
        return None
    return key_data[_FEATURE_COLS].values[-_SEQ_LEN:]


def _predict_popularity(key: str) -> float:
    """
    Run the selected model and return a normalised popularity score [0, 1].
    Falls back to 0.5 if the key is unknown or prediction fails.
    """
    if key not in _models:
        logger.debug("Unknown key='%s'; using default popularity 0.5", key)
        return 0.5

    selected = _key_model_map.get(key, "ARIMA")

    if selected == "LSTM":
        raw_features = _get_features_for_key(key)
        if raw_features is None:
            return 0.5

        scaler = _scalers[key]
        scaled = scaler.transform(raw_features)

        # Reshape to (1, seq_len, n_features)
        lstm_input = scaled.reshape(1, _SEQ_LEN, _N_FEATURES)

        # Predict — model may output shape (1,1) or (1,n_features) depending
        # on whether it was trained with the old Dense(1) or new Dense(n_features).
        pred_scaled = _models[key].predict(lstm_input, verbose=0)

        # Normalise to shape (1, n_features) by padding with zeros so
        # scaler.inverse_transform always receives the expected column count.
        n_out = pred_scaled.shape[1]
        if n_out < _N_FEATURES:
            dummy = np.zeros((1, _N_FEATURES))
            dummy[0, :n_out] = pred_scaled[0, :n_out]
            pred_scaled = dummy

        # Invert scaling to get raw request count (column 0)
        pred_raw   = scaler.inverse_transform(pred_scaled)   # (1, n_features)
        pred_count = float(pred_raw[0, 0])

        popularity = min(1.0, max(0.0, pred_count / _MAX_COUNT))
        logger.debug(
            "LSTM prediction for key='%s': raw_count=%.2f, popularity=%.3f",
            key, pred_count, popularity,
        )
        return popularity

    else:  # ARIMA — run the persisted forecast
        arima_fit = _models.get(key)
        if arima_fit is None:
            # pkl not found at startup — safe fallback
            logger.debug("ARIMA model unavailable for key='%s'; using fallback 0.5", key)
            return 0.5
        try:
            forecast   = arima_fit.forecast(steps=1)
            pred_count = float(np.maximum(forecast.iloc[0], 0))
            popularity = min(1.0, max(0.0, pred_count / _MAX_COUNT))
            logger.debug(
                "ARIMA forecast for key='%s': raw_count=%.2f, popularity=%.3f",
                key, pred_count, popularity,
            )
            return popularity
        except Exception as exc:
            logger.warning("ARIMA forecast failed for key='%s': %s", key, exc)
            return 0.5


def _build_response(
    cache_key: str,
    popularity: float,
    volatility: float,
    is_hot: bool,
    suggested_ttl: int,
    confidence: float,
) -> dict:
    return {
        "cache_key":     cache_key,
        "popularity":    round(popularity, 4),
        "volatility":    round(volatility, 4),
        "is_hot":        is_hot,
        "suggested_ttl": suggested_ttl,
        "confidence":    round(confidence, 4),
        "model_version": _model_version,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/v1/predict/<path:cache_key>", methods=["POST"])
def predict_ttl(cache_key: str):
    """
    Predict the optimal TTL for a cache key.

    Returns JSON with: cache_key, popularity, volatility, is_hot,
                       suggested_ttl, confidence, model_version.
    """
    t_start = time.perf_counter()
    logger.info("POST /api/v1/predict/%s", cache_key)

    try:
        current_time = datetime.now()

        # Unknown key — return safe default immediately, no model inference
        if cache_key not in _key_model_map:
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "Unknown key='%s': returning default TTL=%ds, confidence=0.1 [%.1f ms]",
                cache_key, cfg.DEFAULT_TTL, elapsed_ms,
            )
            return jsonify(
                _build_response(
                    cache_key=cache_key,
                    popularity=0.5,
                    volatility=0.0,
                    is_hot=False,
                    suggested_ttl=cfg.DEFAULT_TTL,
                    confidence=0.1,
                )
            ), 200

        # 1. Volatility — uses pre-loaded db_updates_df (no disk I/O)
        volatility_score = _volatility_engine.update(
            cache_key, current_time, _db_updates_df
        )

        # 2. Popularity prediction
        popularity_score = _predict_popularity(cache_key)

        # 3. Hot-key detection (records this request)
        is_hot = _hotkey_detector.record_request(cache_key)

        # 4. Fuse into final TTL
        # Check for an active pre-warm override before running fusion engine
        override_entry = _ttl_overrides.get(cache_key)
        if override_entry and time.time() < override_entry["expires_at"]:
            suggested_ttl = override_entry["ttl"]
            logger.info(
                "Pre-warm TTL override active for key='%s': ttl=%ds (expires in %.0fs)",
                cache_key, suggested_ttl, override_entry["expires_at"] - time.time(),
            )
        else:
            if override_entry:
                # Expired — clean up
                _ttl_overrides.pop(cache_key, None)
            suggested_ttl = int(_ttl_engine.calculate_ttl(
                popularity_score, volatility_score, is_hot
            ))

        # 5. Confidence: based on historical data volume for this key
        key_rows = (_feature_df["cache_key"] == cache_key).sum()
        confidence = 0.9 if key_rows >= 100 else 0.3

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            "Prediction for key='%s': ttl=%ds, pop=%.3f, vol=%.3f, hot=%s, conf=%.2f [%.1f ms]",
            cache_key, suggested_ttl, popularity_score, volatility_score,
            is_hot, confidence, elapsed_ms,
        )

        return jsonify(
            _build_response(
                cache_key, popularity_score, volatility_score,
                is_hot, suggested_ttl, confidence,
            )
        ), 200

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.error(
            "Error predicting for key='%s': %s [%.1f ms]",
            cache_key, exc, elapsed_ms, exc_info=True,
        )
        # Safe default response — never return a 500 to the caller
        return jsonify(
            _build_response(
                cache_key=cache_key,
                popularity=0.5,
                volatility=0.0,
                is_hot=False,
                suggested_ttl=cfg.DEFAULT_TTL,
                confidence=0.1,
            )
        ), 200


@app.route("/health", methods=["GET"])
def health():
    """Liveness probe — returns service status and current model version."""
    return jsonify({
        "status":        "ok",
        "model_version": _model_version,
        "generated_at":  _generated_at,
        "keys_loaded":   len(_models),
    }), 200


@app.route("/api/v1/reload", methods=["POST"])
def reload_models():
    """
    Hot-reload all models from disk without restarting the process.

    Reads model_metadata.json, then reloads every LSTM/ARIMA model
    and scaler into the in-memory dicts under a threading lock so
    in-flight requests using the old models finish cleanly.

    Returns JSON with: status, keys_reloaded, model_version.
    """
    global _model_version, _generated_at

    logger.info("POST /api/v1/reload — acquiring reload lock...")
    if not _reload_lock.acquire(blocking=False):
        return jsonify({"status": "busy", "message": "A reload is already in progress."}), 409

    try:
        # 1. Re-read metadata
        with open(cfg.METADATA_PATH) as f:
            raw_meta = json.load(f)
        new_meta: list[dict] = raw_meta["models"]
        new_version: str     = raw_meta.get("version", "unknown")
        new_generated_at: str = raw_meta.get("generated_at", "unknown")
        logger.info(
            "Reload: metadata loaded (%d keys, version=%s)", len(new_meta), new_version
        )

        # 2. Build replacement dicts (do the heavy I/O outside the swap)
        new_models: dict[str, object]  = {}
        new_scalers: dict[str, object] = {}
        new_key_map: dict[str, str]    = {}
        n_ok = 0

        for entry in new_meta:
            key      = entry["key"]
            safe_key = entry.get("safe_key", key.replace(":", "_").replace("/", "_"))
            selected = entry["selected_model"]
            new_key_map[key] = selected

            if selected == "LSTM":
                model_path  = cfg.MODEL_DIR / f"lstm_{safe_key}.keras"
                scaler_path = cfg.MODEL_DIR / f"scaler_{safe_key}.pkl"
                try:
                    new_models[key]  = load_model(str(model_path))
                    new_scalers[key] = joblib.load(str(scaler_path))
                    n_ok += 1
                except Exception as exc:
                    logger.warning("  Reload: LSTM load failed for key='%s': %s", key, exc)
            else:  # ARIMA
                arima_path = cfg.MODEL_DIR / f"arima_{safe_key}.pkl"
                try:
                    new_models[key] = joblib.load(str(arima_path))
                    n_ok += 1
                except Exception as exc:
                    logger.warning("  Reload: ARIMA load failed for key='%s': %s", key, exc)
                    new_models[key] = None

        # 3. Atomic swap into module-level globals
        _models.clear()
        _models.update(new_models)
        _scalers.clear()
        _scalers.update(new_scalers)
        _key_model_map.clear()
        _key_model_map.update(new_key_map)
        _model_version  = new_version
        _generated_at   = new_generated_at

        logger.info(
            "Reload complete: %d/%d keys loaded successfully (version=%s)",
            n_ok, len(new_meta), new_version,
        )
        return jsonify({
            "status":        "ok",
            "keys_reloaded": n_ok,
            "keys_total":    len(new_meta),
            "model_version": new_version,
            "generated_at":  new_generated_at,
        }), 200

    except Exception as exc:
        logger.error("Reload failed: %s", exc, exc_info=True)
        return jsonify({"status": "error", "message": str(exc)}), 500

    finally:
        _reload_lock.release()


@app.route("/api/v1/prewarm/<path:cache_key>", methods=["POST"])
def prewarm_key(cache_key: str):
    """
    Pre-warm (pin) a cache key ahead of an expected traffic spike.

    Optional JSON body:
        {"ttl_override": 3600}  — TTL (seconds) to force for this key.
                                   The override expires after ttl_override seconds.

    The key is also immediately registered as a hot key in HotKeyDetector
    for the current sliding window.

    Returns JSON: cache_key, pinned, ttl_override (or null).
    """
    logger.info("POST /api/v1/prewarm/%s", cache_key)

    body         = request.get_json(silent=True) or {}
    ttl_override = body.get("ttl_override")

    # Clamp override to configured bounds if provided
    if ttl_override is not None:
        try:
            ttl_override = int(ttl_override)
            ttl_override = max(cfg.MIN_TTL, min(cfg.MAX_TTL, ttl_override))
            _ttl_overrides[cache_key] = {
                "ttl":        ttl_override,
                "expires_at": time.time() + ttl_override,
            }
            logger.info(
                "Pre-warm TTL override set for key='%s': ttl=%ds", cache_key, ttl_override
            )
        except (TypeError, ValueError):
            ttl_override = None

    # Mark as hot in the sliding-window detector
    _hotkey_detector.record_request(cache_key)

    return jsonify({
        "cache_key":    cache_key,
        "pinned":       True,
        "ttl_override": ttl_override,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting Flask dev server on %s:%d (debug=%s)",
        cfg.HOST, cfg.PORT, cfg.DEBUG,
    )
    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
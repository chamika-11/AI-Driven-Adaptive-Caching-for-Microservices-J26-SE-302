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

# ── Global model metadata ────────────────────────────────────────────────────
logger.info("Loading model metadata from: %s", cfg.METADATA_PATH)
try:
    with open(cfg.METADATA_PATH) as f:
        _raw_meta = json.load(f)
    _metadata: list[dict] = _raw_meta["models"]
    _model_version: str   = _raw_meta.get("version", "unknown")
    _generated_at: str    = _raw_meta.get("generated_at", "unknown")
    _mode: str            = _raw_meta.get("mode", "global_shared")
    logger.info(
        "Metadata loaded: version=%s, mode=%s, generated_at=%s",
        _model_version, _mode, _generated_at,
    )
except Exception as exc:
    logger.error("FATAL: Could not load model metadata: %s", exc)
    _metadata, _model_version, _generated_at, _mode = [], "error", "unknown", "global_shared"

# ── Load single shared global model + scaler + label encoder ─────────────────
logger.info("Loading global LSTM model and shared scaler...")
_global_model  = None
_global_scaler = None
_global_le     = None       # LabelEncoder: cache_key -> int index
_known_keys: set[str] = set()

try:
    _global_model  = load_model(str(cfg.MODEL_DIR / "lstm_global.keras"))
    _global_scaler = joblib.load(str(cfg.MODEL_DIR / "scaler_global.pkl"))
    _global_le     = joblib.load(str(cfg.MODEL_DIR / "label_encoder_global.pkl"))
    _known_keys    = set(_global_le.classes_)
    logger.info(
        "Global model loaded: %d parameters | %d known keys",
        _global_model.count_params(), len(_known_keys),
    )
except Exception as exc:
    logger.error("Could not load global model: %s", exc)

# ── Historical feature data (for LSTM input construction) ─────────────────────
logger.info("Loading processed features from: %s", cfg.PROCESSED_FEATURES_PATH)
try:
    _feature_df = pd.read_csv(cfg.PROCESSED_FEATURES_PATH, parse_dates=["bucket"])
    logger.info("Feature data loaded: %d rows.", len(_feature_df))
except Exception as exc:
    logger.error("Could not load feature data: %s", exc)
    _feature_df = pd.DataFrame()

# ── DB update logs — pre-loaded to avoid per-request disk reads ───────────────
logger.info("Loading DB update logs from: %s", cfg.DB_UPDATES_PATH)
try:
    _db_updates_df = pd.read_csv(cfg.DB_UPDATES_PATH, parse_dates=["timestamp"])
    logger.info("DB update log loaded: %d rows.", len(_db_updates_df))
except Exception as exc:
    logger.error("Could not load DB update log: %s", exc)
    _db_updates_df = pd.DataFrame(columns=["timestamp", "cache_key"])

# ── Engine instances ──────────────────────────────────────────────────────────
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

# Feature columns — must match train_models.py (global mode includes key_label)
_FEATURE_COLS = ["request_count", "hour_sin", "hour_cos", "dow_sin", "dow_cos", "key_label"]
_N_FEATURES   = len(_FEATURE_COLS)
_SEQ_LEN      = cfg.SEQUENCE_LENGTH
_MAX_COUNT    = 150  # Normalise raw count into a popularity score [0, 1]

def _get_features_for_key(key: str) -> np.ndarray | None:
    """
    Return the last `_SEQ_LEN` rows of feature data for `key`, with the
    key_label column appended (required by the global shared model).
    Returns None if insufficient history exists.
    """
    if _feature_df.empty or _global_le is None:
        return None

    key_data = _feature_df[_feature_df["cache_key"] == key].sort_values("bucket")
    if len(key_data) < _SEQ_LEN:
        logger.debug(
            "Insufficient history for key='%s': have %d, need %d",
            key, len(key_data), _SEQ_LEN,
        )
        return None

    # Base time-series features (request_count, cyclicals)
    base_cols = ["request_count", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    base_arr = key_data[base_cols].values[-_SEQ_LEN:]   # (seq_len, 5)

    # Encode key label — normalise to [0, 1] using same range as training
    n_classes = max(len(_global_le.classes_) - 1, 1)
    try:
        label_int = _global_le.transform([key])[0]
    except ValueError:
        # Unseen key: place at the midpoint of the label range
        label_int = n_classes / 2
    key_label_col = np.full((len(base_arr), 1), label_int / n_classes)  # (seq_len, 1)

    return np.hstack([base_arr, key_label_col])   # (seq_len, 6)


def _predict_popularity(key: str) -> float:
    """
    Run the single global LSTM and return a normalised popularity score [0, 1].
    Falls back to 0.5 if the model is unavailable or prediction fails.
    """
    if _global_model is None or _global_scaler is None:
        logger.debug("Global model not loaded; using default popularity 0.5")
        return 0.5

    raw_features = _get_features_for_key(key)
    if raw_features is None:
        return 0.5

    try:
        scaled = _global_scaler.transform(raw_features)          # (seq_len, 6)
        lstm_input = scaled.reshape(1, _SEQ_LEN, _N_FEATURES)    # (1, seq_len, 6)

        pred_scaled = _global_model.predict(lstm_input, verbose=0).flatten()  # (1,)

        # Invert scaling: pad with zeros to reconstruct the full feature row
        dummy = np.zeros((1, _N_FEATURES))
        dummy[0, 0] = pred_scaled[0]
        pred_raw   = _global_scaler.inverse_transform(dummy)
        pred_count = float(pred_raw[0, 0])

        popularity = min(1.0, max(0.0, pred_count / _MAX_COUNT))
        logger.debug(
            "Global LSTM prediction for key='%s': raw_count=%.2f, popularity=%.3f",
            key, pred_count, popularity,
        )
        return popularity

    except Exception as exc:
        logger.warning("Global LSTM prediction failed for key='%s': %s", key, exc)
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

        # Unknown key — still serve via global model (unseen key gets midpoint label)
        # Only fall back to default if global model itself is unavailable
        if _global_model is None:
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "Global model unavailable; returning default TTL=%ds for key='%s' [%.1f ms]",
                cfg.DEFAULT_TTL, cache_key, elapsed_ms,
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

        # 5. Confidence: 0.9 if key was seen during training, 0.5 if unseen (global model generalises)
        key_rows = (_feature_df["cache_key"] == cache_key).sum() if not _feature_df.empty else 0
        if cache_key in _known_keys and key_rows >= 100:
            confidence = 0.9
        elif cache_key in _known_keys:
            confidence = 0.6
        else:
            confidence = 0.4  # Unseen key — global model generalises but less certain

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
        "model_loaded":  _global_model is not None,
        "keys_known":    len(_known_keys),
    }), 200


@app.route("/api/v1/reload", methods=["POST"])
def reload_models():
    """
    Hot-reload the global model from disk without restarting the process.

    Reloads lstm_global.keras, scaler_global.pkl, label_encoder_global.pkl
    atomically under a threading lock so in-flight requests finish cleanly.

    Returns JSON with: status, keys_known, model_version.
    """
    global _model_version, _generated_at, _global_model, _global_scaler, _global_le, _known_keys

    logger.info("POST /api/v1/reload — acquiring reload lock...")
    if not _reload_lock.acquire(blocking=False):
        return jsonify({"status": "busy", "message": "A reload is already in progress."}), 409

    try:
        # 1. Re-read metadata
        with open(cfg.METADATA_PATH) as f:
            raw_meta = json.load(f)
        new_version: str      = raw_meta.get("version", "unknown")
        new_generated_at: str = raw_meta.get("generated_at", "unknown")
        logger.info("Reload: metadata loaded (version=%s)", new_version)

        # 2. Load new model artefacts (heavy I/O before atomic swap)
        new_model  = load_model(str(cfg.MODEL_DIR / "lstm_global.keras"))
        new_scaler = joblib.load(str(cfg.MODEL_DIR / "scaler_global.pkl"))
        new_le     = joblib.load(str(cfg.MODEL_DIR / "label_encoder_global.pkl"))
        new_known  = set(new_le.classes_)

        # 3. Atomic swap
        _global_model  = new_model
        _global_scaler = new_scaler
        _global_le     = new_le
        _known_keys    = new_known
        _model_version = new_version
        _generated_at  = new_generated_at

        logger.info(
            "Reload complete: global model loaded | %d known keys (version=%s)",
            len(_known_keys), new_version,
        )
        return jsonify({
            "status":        "ok",
            "keys_known":    len(_known_keys),
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
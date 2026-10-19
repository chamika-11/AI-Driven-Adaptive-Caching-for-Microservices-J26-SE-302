"""
retrain.py — Nightly Model Retraining Script with Rollback Gate.

Workflow:
    1. Back up existing model files (*.keras, *.pkl) to models/backup/.
    2. Regenerate fresh synthetic data.
    3. Re-run preprocessing.
    4. Retrain all models (writes new model_metadata.json).
    5. ROLLBACK GATE: Compare new RMSE vs old RMSE per key.
       - If ANY key degrades by more than ROLLBACK_TOLERANCE (default 5%),
         reject the new models and restore the backup.
       - Otherwise, commit the new models.

Usage:
    python src/retrain.py

    Schedule with cron (Linux/Mac):
        0 2 * * * /usr/local/bin/python /app/src/retrain.py >> /var/log/retrain.log 2>&1

    Schedule with Task Scheduler (Windows):
        Action: python retrain.py
        Trigger: Daily at 02:00
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("retrain")

# ── Config ────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg


# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _load_metadata(path: Path) -> dict | None:
    """Load model_metadata.json. Returns None if the file doesn't exist."""
    if not path.exists():
        logger.warning("Metadata file not found at: %s", path)
        return None
    with open(path) as f:
        return json.load(f)


def _run_script(script_rel_path: str) -> None:
    """
    Run a Python script relative to the project root as a subprocess,
    propagating any failures as exceptions.
    """
    script_path = Path(__file__).resolve().parent / script_rel_path
    logger.info("Running: python %s", script_path)
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,
        check=True,
    )


def _backup_models(backup_dir: Path) -> bool:
    """
    Copy all *.keras and *.pkl files + model_metadata.json from MODEL_DIR
    to backup_dir. Returns True on success.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed_up = 0

    for pattern in ("*.keras", "*.pkl", "model_metadata.json"):
        for src in cfg.MODEL_DIR.glob(pattern):
            dst = backup_dir / src.name
            shutil.copy2(src, dst)
            backed_up += 1
            logger.debug("  Backed up: %s → %s", src.name, dst)

    logger.info("Backup complete: %d files copied to %s", backed_up, backup_dir)
    return backed_up > 0


def _restore_models(backup_dir: Path) -> None:
    """
    Restore all files from backup_dir back to MODEL_DIR,
    overwriting anything that was written during this retraining run.
    """
    logger.warning("=== ROLLBACK: Restoring models from backup ===")
    restored = 0

    for src in backup_dir.iterdir():
        if src.is_file():
            dst = cfg.MODEL_DIR / src.name
            shutil.copy2(src, dst)
            restored += 1
            logger.debug("  Restored: %s", src.name)

    logger.warning("Rollback complete: %d files restored.", restored)


def _build_rmse_map(metadata: dict) -> dict[str, float]:
    """Build a {key: winner_rmse} mapping from metadata JSON."""
    return {
        entry["key"]: entry["winner_rmse"]
        for entry in metadata.get("models", [])
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main Retraining Routine
# ─────────────────────────────────────────────────────────────────────────────

def run_retraining() -> bool:
    """
    Execute the full nightly retraining pipeline.

    Returns:
        True if retraining succeeded and new models were committed.
        False if retraining was rolled back due to degraded RMSE.
    """
    run_id   = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    t_start  = time.time()
    logger.info("=" * 60)
    logger.info("=== Nightly Retraining Started — run_id=%s ===", run_id)
    logger.info("=" * 60)

    # ── Step 1: Snapshot current model metadata ──────────────────────────────
    logger.info("[1/5] Loading current model metadata (baseline RMSE)...")
    old_metadata = _load_metadata(cfg.METADATA_PATH)

    if old_metadata is None:
        logger.warning(
            "No existing metadata found. Skipping rollback gate for first run."
        )
        old_rmse_map: dict[str, float] = {}
    else:
        old_rmse_map = _build_rmse_map(old_metadata)
        logger.info("Baseline RMSE loaded for %d keys.", len(old_rmse_map))

    # ── Step 2: Backup existing model files ──────────────────────────────────
    logger.info("[2/5] Backing up existing model files...")
    backup_dir = cfg.BACKUP_DIR / run_id
    backup_ok  = _backup_models(backup_dir)
    if not backup_ok:
        logger.warning("No model files found to back up (first run?).")

    # ── Step 3: Generate fresh data + preprocess ─────────────────────────────
    logger.info("[3/5] Generating fresh synthetic data and preprocessing...")
    try:
        _run_script("synthetic_data.py")
        _run_script("preprocess.py")
    except subprocess.CalledProcessError as exc:
        logger.error("Data pipeline failed: %s", exc)
        _restore_models(backup_dir)
        return False

    # ── Step 4: Retrain models ────────────────────────────────────────────────
    logger.info("[4/5] Retraining models (this may take a while)...")
    try:
        _run_script("train_models.py")
    except subprocess.CalledProcessError as exc:
        logger.error("Model training failed: %s", exc)
        _restore_models(backup_dir)
        return False

    # ── Step 5: Rollback Gate ─────────────────────────────────────────────────
    logger.info("[5/5] Running rollback gate (tolerance=%.0f%%)...", cfg.ROLLBACK_TOLERANCE * 100)

    new_metadata = _load_metadata(cfg.METADATA_PATH)
    if new_metadata is None:
        logger.error("New metadata not found after training. Rolling back.")
        _restore_models(backup_dir)
        return False

    new_rmse_map = _build_rmse_map(new_metadata)

    failures: list[dict] = []
    improvements: list[dict] = []

    for key, new_rmse in new_rmse_map.items():
        if key not in old_rmse_map:
            # Brand-new key — always accept
            logger.info("  ✅ NEW key='%s' new_rmse=%.4f — accepted", key, new_rmse)
            improvements.append({"key": key, "old": None, "new": new_rmse})
            continue

        old_rmse  = old_rmse_map[key]
        threshold = old_rmse * (1.0 + cfg.ROLLBACK_TOLERANCE)

        if new_rmse > threshold:
            logger.warning(
                "  ❌ DEGRADED key='%s' old_rmse=%.4f new_rmse=%.4f "
                "(%.1f%% worse, limit=%.0f%%)",
                key, old_rmse, new_rmse,
                ((new_rmse - old_rmse) / old_rmse) * 100,
                cfg.ROLLBACK_TOLERANCE * 100,
            )
            failures.append({"key": key, "old": old_rmse, "new": new_rmse})
        else:
            change_pct = ((new_rmse - old_rmse) / old_rmse) * 100
            symbol = "✅" if new_rmse <= old_rmse else "⚠️ "
            logger.info(
                "  %s key='%s' old=%.4f new=%.4f (%+.1f%%)",
                symbol, key, old_rmse, new_rmse, change_pct,
            )
            improvements.append({"key": key, "old": old_rmse, "new": new_rmse})

    elapsed = time.time() - t_start

    if failures:
        logger.warning(
            "ROLLBACK TRIGGERED — %d/%d keys degraded beyond %.0f%% tolerance.",
            len(failures), len(new_rmse_map), cfg.ROLLBACK_TOLERANCE * 100,
        )
        for f in failures:
            logger.warning(
                "  Rejected key='%s': old_rmse=%.4f → new_rmse=%.4f",
                f["key"], f["old"], f["new"],
            )
        _restore_models(backup_dir)
        logger.info("=== Retraining REJECTED in %.1f s (run_id=%s) ===", elapsed, run_id)
        return False

    # All keys passed — commit new metadata
    logger.info(
        "All %d keys passed the rollback gate. Committing new models.",
        len(new_rmse_map),
    )

    # Stamp the run_id into the metadata so the API can surface it
    new_metadata["run_id"] = run_id
    with open(cfg.METADATA_PATH, "w") as f:
        json.dump(new_metadata, f, indent=2)
    logger.info("model_metadata.json updated with run_id=%s", run_id)

    # ── Notify the running API to hot-reload models ───────────────────────────
    reload_url = f"http://localhost:{cfg.PORT}/api/v1/reload"
    logger.info("Triggering API hot-reload at %s ...", reload_url)
    try:
        req = urllib.request.Request(
            reload_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            logger.info(
                "API reload successful: keys_known=%s, version=%s",
                body.get("keys_known") or body.get("keys_reloaded"), body.get("model_version"),
            )
    except Exception as exc:
        # Non-fatal: models on disk are correct; API will use them on next restart.
        logger.warning(
            "Could not notify API to reload (will take effect on next restart): %s", exc
        )

    logger.info("=" * 60)
    logger.info(
        "=== Retraining COMMITTED in %.1f s (run_id=%s) ===", elapsed, run_id
    )
    logger.info("=" * 60)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    success = run_retraining()
    sys.exit(0 if success else 1)
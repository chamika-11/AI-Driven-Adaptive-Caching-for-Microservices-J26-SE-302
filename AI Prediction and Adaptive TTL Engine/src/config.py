import os
import logging
from pathlib import Path

# Load .env file from the project root
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

logger = logging.getLogger(__name__)


class Config:
    MIN_TTL: int = int(os.getenv("MIN_TTL", "10"))
    MAX_TTL: int = int(os.getenv("MAX_TTL", "3600"))
    DEFAULT_TTL: int = int(os.getenv("DEFAULT_TTL", "300"))

    # ── API Server ───────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "5001"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── Paths ────────────────────────────────────────────────────────────────
    _PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    MODEL_DIR: Path = Path(os.getenv("MODEL_DIR", str(_PROJECT_ROOT / "models")))
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data")))

    # Derived paths
    METADATA_PATH: Path = MODEL_DIR / "model_metadata.json"
    BACKUP_DIR: Path = MODEL_DIR / "backup"
    RAW_LOGS_PATH: Path = DATA_DIR / "raw_logs.csv"
    DB_UPDATES_PATH: Path = DATA_DIR / "db_updates.csv"
    PROCESSED_FEATURES_PATH: Path = DATA_DIR / "processed_features.csv"

    # ── Model Behaviour ──────────────────────────────────────────────────────
    HOTKEY_THRESHOLD: int = int(os.getenv("HOTKEY_THRESHOLD", "1000"))
    HOTKEY_WINDOW_SECONDS: int = int(os.getenv("HOTKEY_WINDOW_SECONDS", "60"))
    EWMA_ALPHA: float = float(os.getenv("EWMA_ALPHA", "0.3"))

    # ── LSTM Training ────────────────────────────────────────────────────────
    SEQUENCE_LENGTH: int = int(os.getenv("SEQUENCE_LENGTH", "60"))
    LSTM_EPOCHS: int = int(os.getenv("LSTM_EPOCHS", "30"))
    LSTM_BATCH_SIZE: int = int(os.getenv("LSTM_BATCH_SIZE", "32"))
    TRAIN_SPLIT: float = float(os.getenv("TRAIN_SPLIT", "0.7"))

    # ── Retraining ───────────────────────────────────────────────────────────
    ROLLBACK_TOLERANCE: float = float(os.getenv("ROLLBACK_TOLERANCE", "0.05"))

    def __repr__(self) -> str:
        return (
            f"Config(MIN_TTL={self.MIN_TTL}, MAX_TTL={self.MAX_TTL}, "
            f"PORT={self.PORT}, MODEL_DIR={self.MODEL_DIR}, "
            f"HOTKEY_THRESHOLD={self.HOTKEY_THRESHOLD})"
        )


# Singleton instance
cfg = Config()

logger.debug("Config loaded: %s", cfg)

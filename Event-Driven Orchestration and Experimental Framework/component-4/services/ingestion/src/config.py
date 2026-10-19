"""Configuration module for the API Documentation Ingestion service."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables or .env file."""

    SERVICE_NAME: str = "api-docs-ingestion"
    PORT: int = 8001
    HOST: str = "0.0.0.0"
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB default limit
    LOG_LEVEL: str = "INFO"
    MONGODB_URI: Optional[str] = None
    DATABASE_NAME: str = "component4"
    ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

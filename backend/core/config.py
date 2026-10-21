"""
VisionX Configuration Management
Centralized, environment-based configuration using Pydantic Settings v2.
All configuration is loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, SecretStr


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Supports .env file for local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    APP_NAME: str = "VisionX"
    APP_VERSION: str = "4.0.0"
    APP_DESCRIPTION: str = "AI-powered Digital Forensics Platform"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    SECRET_KEY: str = Field(default="change-me-in-production", min_length=32)
    API_PREFIX: str = "/api/v4"
    CORS_ORIGINS: str = "*"

    # ---- Database (PostgreSQL / AWS RDS) ----
    DATABASE_URL: Optional[str] = None  # Direct PostgreSQL connection string
    DATABASE_SCHEMA: str = "visionx"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # ---- Authentication ----
    JWT_SECRET_KEY: str = Field(default="change-me-in-production-jwt-secret-key-min-32-chars", min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "visionx"
    PASSWORD_BCRYPT_ROUNDS: int = 12

    # ---- Storage ----
    STORAGE_BACKEND: Literal["s3", "local"] = "local"
    STORAGE_BUCKET_ANALYSIS: str = "analysis-files"
    STORAGE_BUCKET_REPORTS: str = "reports"
    STORAGE_BUCKET_EVIDENCE: str = "evidence"
    STORAGE_LOCAL_PATH: str = "./storage"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_REGION: str = "us-east-1"
    S3_BUCKET: Optional[str] = None

    # ---- AI / LLM ----
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-haiku-20240307"
    NEMOTRON_API_KEY: Optional[str] = None
    NEMOTRON_MODEL: str = "nemotron-4-340b-instruct"
    LLM_PROVIDER: Literal["gemini", "openai", "claude", "none"] = "none"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT_SECONDS: int = 30

    # ---- Analysis Pipeline ----
    MAX_CONCURRENT_AGENTS: int = 5
    AGENT_TIMEOUT_SECONDS: int = 120
    AGENT_MAX_RETRIES: int = 3
    AGENT_RETRY_DELAY_SECONDS: int = 2
    PIPELINE_DEFAULT_TIMEOUT: int = 300
    EVIDENCE_FUSION_MIN_AGENTS: int = 1

    # ---- Upload ----
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_IMAGE_TYPES: List[str] = [
        "image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"
    ]
    ALLOWED_VIDEO_TYPES: List[str] = [
        "video/mp4", "video/webm", "video/avi", "video/mov"
    ]
    ALLOWED_DOCUMENT_TYPES: List[str] = [
        "application/pdf", "text/plain", "text/html"
    ]
    ALLOWED_AUDIO_TYPES: List[str] = [
        "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4"
    ]

    # ---- Monitoring ----
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ---- Rate Limiting ----
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_REQUESTS_PER_HOUR: int = 1000

    # ---- Feature Flags ----
    FEATURE_NEWS_VERIFICATION: bool = True
    FEATURE_VIDEO_VERIFICATION: bool = True
    FEATURE_DOCUMENT_VERIFICATION: bool = True
    FEATURE_AUDIO_VERIFICATION: bool = True
    FEATURE_IMAGE_VERIFICATION: bool = True
    FEATURE_LLM_REASONING: bool = True
    FEATURE_REVERSE_IMAGE_SEARCH: bool = False
    FEATURE_PDF_REPORTS: bool = True

    # ---- Derived Properties ----
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_staging(self) -> bool:
        return self.ENVIRONMENT == "staging"

    @property
    def database_url_safe(self) -> str:
        """Return database URL with password masked for logging."""
        if not self.DATABASE_URL:
            return "not-configured"
        url = str(self.DATABASE_URL)
        if "@" in url:
            parts = url.split("@")
            credentials = parts[0].split("://")[1] if "://" in parts[0] else parts[0]
            if ":" in credentials:
                masked = credentials.split(":")[0] + ":****"
                url = url.replace(credentials, masked)
        return url

    @property
    def allowed_mime_types(self) -> List[str]:
        """All allowed MIME types across all modules."""
        return (
            self.ALLOWED_IMAGE_TYPES
            + self.ALLOWED_VIDEO_TYPES
            + self.ALLOWED_DOCUMENT_TYPES
            + self.ALLOWED_AUDIO_TYPES
        )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS into a list."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        v = str(self.CORS_ORIGINS).strip()
        if not v or v == "*":
            return ["*"]
        if "," in v:
            return [item.strip() for item in v.split(",") if item.strip()]
        return [v]

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Normalize LOG_FORMAT to valid values. Default to text if invalid."""
        if isinstance(v, str):
            v = v.strip().lower()
            if v in ("json", "text"):
                return v
            # If it looks like a Python logging format string, default to text
            if "%(" in v:
                return "text"
        return "text"
    
    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def validate_secret_keys(cls, v: str) -> str:
        if v == "change-me-in-production" or v == "change-me-jwt-secret":
            import warnings
            warnings.warn(
                "Using default secret key. Set a secure value in production.",
                RuntimeWarning,
                stacklevel=2,
            )
        return v
    
    
    @field_validator(
        "ALLOWED_IMAGE_TYPES",
        "ALLOWED_VIDEO_TYPES",
        "ALLOWED_DOCUMENT_TYPES",
        "ALLOWED_AUDIO_TYPES",
        mode="before",
    )
    @classmethod
    def parse_list_fields(cls, v):
        """Parse list fields from env var (JSON array or comma-separated)."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            if "\n" in v:
                return [item.strip() for item in v.split("\n") if item.strip()]
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


# Global singleton
settings = Settings()

# Export commonly used constants
MAX_UPLOAD_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_MIME_TYPES = settings.allowed_mime_types
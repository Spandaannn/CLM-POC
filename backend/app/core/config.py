"""Application settings loaded from environment variables.

Only DATABASE_URL is required. Pydantic reads it from the process environment
or from backend/.env (useful during local development).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description=(
            "PostgreSQL connection URL, e.g. "
            "postgresql+psycopg://user:password@localhost:5432/clm_db"
        ),
    )
    database_echo: bool = Field(
        default=False,
        description="When true, SQLAlchemy logs every SQL statement.",
    )

    session_ttl_minutes: int = Field(
        default=480,
        ge=1,
        le=43200,
        description="Lifetime of a login session in minutes (default 8 hours).",
    )
    cookie_secure: bool = Field(
        default=False,
        description="Send cookies only over HTTPS. Must be true in production.",
    )
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite policy for the session and CSRF cookies.",
    )

    document_storage_path: Path = Field(
        default=Path("storage/documents"),
        description=(
            "Directory where uploaded contract files are stored. A relative "
            "path is resolved against the backend/ directory. It must never "
            "be inside a publicly served directory."
        ),
    )

    @property
    def document_storage_root(self) -> Path:
        """Absolute, resolved storage directory."""
        path = self.document_storage_path.expanduser()
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()

        # SQLAlchemy maps "postgresql://" to the psycopg2 driver, which this
        # project does not install. Rewrite it to the psycopg (v3) driver so a
        # ordinary PostgreSQL URL still works.
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]

        if not value.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL, for example "
                "postgresql+psycopg://clm_user:password@localhost:5432/clm_db"
            )
        return value

    @model_validator(mode="after")
    def validate_cookie_settings(self) -> "Settings":
        # Browsers reject SameSite=None cookies that are not also Secure.
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SECURE must be true when COOKIE_SAMESITE is 'none'"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return settings once per process (avoids re-reading .env repeatedly)."""
    return Settings()

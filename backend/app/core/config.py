"""Application settings loaded from environment variables.

Only DATABASE_URL is required. Pydantic reads it from the process environment
or from backend/.env (useful during local development).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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

    # --- AI review (optional: the app works without it) -------------------
    ai_provider: str | None = Field(
        default=None,
        description="AI provider name. Currently only 'groq' is supported.",
    )
    # SecretStr keeps the key out of repr() and accidental log output.
    groq_api_key: SecretStr | None = Field(default=None)
    groq_model: str = Field(default="openai/gpt-oss-20b")
    ai_timeout_seconds: float = Field(default=90.0, ge=5, le=300)
    ai_max_input_chars: int = Field(
        default=30_000,
        ge=1_000,
        le=400_000,
        description="Maximum contract characters sent to the AI provider.",
    )
    ai_max_output_tokens: int = Field(
        default=4000,
        ge=500,
        le=16000,
        description=(
            "Upper bound on the AI's answer length (including any reasoning). "
            "Providers count this against rate limits, so keep it modest."
        ),
    )
    groq_reasoning_effort: str | None = Field(
        default="low",
        description=(
            "Reasoning effort for Groq's gpt-oss models (low, medium, high). "
            "Leave empty for models that do not support it."
        ),
    )
    ai_playbook_path: Path | None = Field(
        default=None,
        description="Optional JSON playbook replacing the built-in baseline.",
    )

    @field_validator("ai_provider")
    @classmethod
    def normalize_ai_provider(cls, value: str | None) -> str | None:
        value = (value or "").strip().lower()
        return value or None

    @field_validator("groq_reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str | None) -> str | None:
        value = (value or "").strip().lower()
        if value and value not in ("low", "medium", "high"):
            raise ValueError("GROQ_REASONING_EFFORT must be low, medium, or high")
        return value or None

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def blank_api_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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

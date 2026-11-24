"""Build the configured AI provider, or explain why none is available."""

from dataclasses import dataclass

from app.ai.base import AIProvider
from app.ai.errors import AIConfigurationError
from app.ai.groq import GroqProvider
from app.core.config import Settings

SUPPORTED_PROVIDERS = ("groq",)


@dataclass(frozen=True)
class AIStatus:
    """Public, secret-free description of the AI configuration."""

    configured: bool
    provider: str | None
    model: str | None
    message: str | None


def build_provider(settings: Settings) -> AIProvider:
    """Return a provider, or raise ``AIConfigurationError``."""
    provider = settings.ai_provider
    if not provider:
        raise AIConfigurationError(
            "AI review is not configured on this server (no AI provider set)."
        )

    if provider == "groq":
        key = settings.groq_api_key
        if key is None or not key.get_secret_value().strip():
            raise AIConfigurationError(
                "AI review is not configured on this server "
                "(the Groq API key is missing)."
            )
        if not settings.groq_model.strip():
            raise AIConfigurationError(
                "AI review is not configured on this server "
                "(no Groq model is set)."
            )
        return GroqProvider(
            api_key=key.get_secret_value().strip(),
            model=settings.groq_model.strip(),
            timeout=settings.ai_timeout_seconds,
            reasoning_effort=settings.groq_reasoning_effort,
        )

    raise AIConfigurationError(
        f"AI provider '{provider}' is not supported. "
        f"Supported providers: {', '.join(SUPPORTED_PROVIDERS)}."
    )


def get_ai_status(settings: Settings) -> AIStatus:
    """Describe the configuration without ever returning the API key."""
    try:
        provider = build_provider(settings)
    except AIConfigurationError as error:
        return AIStatus(
            configured=False,
            provider=settings.ai_provider,
            model=None,
            message=error.message,
        )
    return AIStatus(
        configured=True,
        provider=provider.name,
        model=provider.model,
        message=None,
    )

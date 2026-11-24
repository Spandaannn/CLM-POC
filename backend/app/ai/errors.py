"""Errors raised by the AI layer.

Every error carries a short ``code`` and a ``message`` that is safe to show to
end users. Provider response bodies, request payloads, and credentials are
never placed in an error.
"""


class AIError(Exception):
    """Base class. ``message`` is safe to return to the frontend."""

    code = "ai_error"
    message = "The AI review could not be completed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class AIConfigurationError(AIError):
    code = "not_configured"
    message = "AI review is not configured on this server."


class AIAuthenticationError(AIError):
    code = "provider_authentication"
    message = (
        "The AI provider rejected the server's credentials. "
        "Ask an administrator to check the AI configuration."
    )


class AIRateLimitError(AIError):
    code = "rate_limited"
    message = (
        "The AI provider's rate limit or quota was reached. "
        "Please try again later."
    )


class AITimeoutError(AIError):
    code = "timeout"
    message = "The AI provider took too long to respond. Please try again."


class AIModelUnavailableError(AIError):
    code = "model_unavailable"
    message = (
        "The configured AI model is unavailable. "
        "Ask an administrator to check the AI configuration."
    )


class AIRequestTooLargeError(AIError):
    code = "request_too_large"
    message = (
        "The document is too large for the AI provider's limits. "
        "Try a shorter document."
    )


class AIProviderError(AIError):
    code = "provider_error"
    message = "The AI provider is unavailable right now. Please try again."


class AIResponseFormatError(AIError):
    code = "malformed_response"
    message = (
        "The AI response could not be understood. No review was saved; "
        "please try again."
    )


class AIResponseTruncatedError(AIResponseFormatError):
    code = "response_truncated"
    message = (
        "The AI's answer was cut off before it finished, so no review was "
        "saved. Try again, or ask an administrator to raise "
        "AI_MAX_OUTPUT_TOKENS."
    )

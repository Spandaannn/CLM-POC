"""Groq adapter (OpenAI-compatible chat completions API).

The API key is sent only in the Authorization header of a server-side request.
Request bodies (which contain contract text), response bodies, and the key are
never logged; only the HTTP status and Groq's short error code are.
"""

import logging
import re

import httpx

from app.ai.errors import (
    AIAuthenticationError,
    AIModelUnavailableError,
    AIProviderError,
    AIRateLimitError,
    AIRequestTooLargeError,
    AIResponseFormatError,
    AIResponseTruncatedError,
    AITimeoutError,
)

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_SAFE_CODE = re.compile(r"[^a-z0-9_.-]")


def _error_code(response: httpx.Response) -> str:
    """Extract Groq's short machine-readable error code, if present."""
    try:
        code = response.json().get("error", {}).get("code", "")
    except (ValueError, AttributeError):
        return ""
    return _SAFE_CODE.sub("", str(code).lower())[:64]


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 90.0,
        base_url: str = GROQ_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._transport = transport  # tests inject httpx.MockTransport
        self._reasoning_effort = reasoning_effort

    def __repr__(self) -> str:  # never show the key
        return f"GroqProvider(model={self.model!r})"

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 8000,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_completion_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort

        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException:
            logger.warning("Groq request timed out")
            raise AITimeoutError() from None
        except httpx.HTTPError:
            logger.warning("Groq request failed before a response")
            raise AIProviderError() from None

        if response.status_code != 200:
            self._raise_for_status(response)

        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIResponseFormatError() from None

        # A reply cut off at the output limit is incomplete: never use it.
        if choice.get("finish_reason") == "length":
            raise AIResponseTruncatedError()

        if not isinstance(content, str) or not content.strip():
            raise AIResponseFormatError()
        return content

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        code = _error_code(response)
        logger.warning("Groq returned status=%s code=%s", status, code or "-")

        if status in (401, 403):
            raise AIAuthenticationError()
        if status == 429:
            raise AIRateLimitError()
        if status == 413:
            raise AIRequestTooLargeError()
        if status == 404 or "model" in code:
            raise AIModelUnavailableError()
        if "json_validate" in code:
            # The model failed to produce valid JSON in JSON mode.
            raise AIResponseFormatError()
        raise AIProviderError()

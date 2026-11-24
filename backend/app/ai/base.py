"""The interface every AI provider adapter implements."""

from typing import Protocol


class AIProvider(Protocol):
    """A chat-style model that returns a JSON document as text."""

    name: str
    model: str

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 8000,
    ) -> str:
        """Return the model's reply text (expected to be one JSON object).

        Implementations must raise the exceptions in ``app.ai.errors`` and
        must never include credentials or provider response bodies in them.
        """
        ...

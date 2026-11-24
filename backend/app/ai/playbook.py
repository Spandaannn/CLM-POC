"""Legal playbook: the configurable rules a contract is compared against.

The project had no existing playbook, so a small baseline ships with the app
(``baseline_playbook.json``). It is only illustrative. To use a real one, point
``AI_PLAYBOOK_PATH`` at a JSON file with the same shape.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.errors import AIConfigurationError

BASELINE_PATH = Path(__file__).with_name("baseline_playbook.json")

Severity = Literal["low", "medium", "high", "critical"]


class PlaybookRule(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    requirement: str = Field(min_length=1, max_length=1000)
    severity_if_not_met: Severity = "medium"


class Playbook(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=32)
    disclaimer: str = Field(default="", max_length=1000)
    rules: list[PlaybookRule] = Field(min_length=1, max_length=40)

    @property
    def label(self) -> str:
        """Stored with each review, e.g. ``baseline-poc@1``."""
        return f"{self.id}@{self.version}"


@lru_cache
def _load(path: Path) -> Playbook:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        playbook = Playbook.model_validate(data)
    except (OSError, ValueError, ValidationError):
        raise AIConfigurationError(
            "The configured playbook could not be read. "
            "Ask an administrator to check AI_PLAYBOOK_PATH."
        ) from None

    ids = [rule.id for rule in playbook.rules]
    if len(ids) != len(set(ids)):
        raise AIConfigurationError(
            "The configured playbook has duplicate rule ids."
        )
    return playbook


def load_playbook(custom_path: Path | None = None) -> Playbook:
    """Return the custom playbook if configured, else the baseline."""
    return _load(custom_path.expanduser().resolve() if custom_path else BASELINE_PATH)

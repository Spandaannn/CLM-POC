"""Schemas for AI contract reviews.

Two groups:

* ``AI*`` models validate what the AI provider returns. They are lenient about
  wording (case, "not found" placeholders, over-long text) but strict about
  structure, so a malformed answer is rejected instead of stored.
* The remaining models are the API responses built from stored results.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)

REVIEW_DISCLAIMER = (
    "AI-generated suggestions for a human legal reviewer. They may be "
    "incomplete or wrong, are not legal advice, and do not approve, reject, "
    "or change the contract."
)

Severity = Literal["low", "medium", "high", "critical"]
PlaybookStatus = Literal["met", "partially_met", "not_met", "not_assessed"]
ExcerptStatus = Literal["verified", "not_verified", "not_provided"]

CLAUSE_CATEGORIES = (
    "payment_terms",
    "termination",
    "confidentiality",
    "indemnity",
    "limitation_of_liability",
    "intellectual_property",
    "data_protection",
    "dispute_resolution",
    "governing_law",
    "renewal",
    "other",
)

_NOT_FOUND = {
    "", "null", "none", "n/a", "na", "nil", "unknown", "not found",
    "not specified", "not stated", "not available", "not mentioned",
    "not provided", "not identified", "not applicable",
}


def _clip(limit: int):
    def convert(value: Any) -> Any:
        return value.strip()[:limit] if isinstance(value, str) else value

    return BeforeValidator(convert)


def _opt_text(limit: int):
    """Text that may be absent; 'not found' style answers become None."""

    def convert(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str):
            return value
        value = value.strip()
        return None if value.lower().rstrip(".") in _NOT_FOUND else value[:limit]

    return BeforeValidator(convert)


def _string_list(item_limit: int, max_items: int):
    def convert(value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            cleaned = [
                v.strip()[:item_limit]
                for v in value
                if isinstance(v, str) and v.strip()
            ]
            return cleaned[:max_items]
        return value

    return BeforeValidator(convert)


def _category(value: Any) -> Any:
    if not isinstance(value, str):
        return "other"
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return key if key in CLAUSE_CATEGORIES else "other"


def _severity(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _playbook_status(value: Any) -> Any:
    if not isinstance(value, str):
        return "not_assessed"
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "partial": "partially_met",
        "partially": "partially_met",
        "unmet": "not_met",
        "missing": "not_met",
        "not_found": "not_met",
        "fail": "not_met",
        "pass": "met",
        "compliant": "met",
    }
    key = aliases.get(key, key)
    return key if key in ("met", "partially_met", "not_met") else "not_assessed"


Category = Annotated[str, BeforeValidator(_category)]
SeverityLevel = Annotated[Severity, BeforeValidator(_severity)]
PlaybookStatusValue = Annotated[PlaybookStatus, BeforeValidator(_playbook_status)]


# ----------------------------- AI output -----------------------------------


class AISummary(BaseModel):
    overview: Annotated[str, _clip(4000)] = Field(min_length=1)
    parties: Annotated[list[str], _string_list(200, 20)] = []
    commercial_terms: Annotated[str | None, _opt_text(2000)] = None
    key_dates_and_obligations: Annotated[str | None, _opt_text(2500)] = None


class AIMetadata(BaseModel):
    parties: Annotated[list[str], _string_list(200, 20)] = []
    effective_date: Annotated[str | None, _opt_text(100)] = None
    expiry_date: Annotated[str | None, _opt_text(100)] = None
    contract_value: Annotated[str | None, _opt_text(100)] = None
    currency: Annotated[str | None, _opt_text(40)] = None
    governing_law: Annotated[str | None, _opt_text(300)] = None
    renewal_terms: Annotated[str | None, _opt_text(1000)] = None


class AIClause(BaseModel):
    category: Category = "other"
    title: Annotated[str, _clip(200)] = Field(min_length=1)
    summary: Annotated[str, _clip(1500)] = Field(min_length=1)
    excerpt: Annotated[str | None, _opt_text(600)] = None


class AIRiskFinding(BaseModel):
    title: Annotated[str, _clip(200)] = Field(min_length=1)
    description: Annotated[str, _clip(1500)] = Field(min_length=1)
    severity: SeverityLevel
    category: Category = "other"
    excerpt: Annotated[str | None, _opt_text(600)] = None
    concern: Annotated[str, _clip(1500)] = Field(min_length=1)
    suggested_action: Annotated[str, _clip(1500)] = Field(min_length=1)


class AIPlaybookResult(BaseModel):
    rule_id: Annotated[str, _clip(64)] = Field(min_length=1)
    status: PlaybookStatusValue
    explanation: Annotated[str, _clip(1500)] = ""
    excerpt: Annotated[str | None, _opt_text(600)] = None


class AIReviewOutput(BaseModel):
    """The JSON document the AI must return."""

    model_config = ConfigDict(extra="ignore")

    summary: AISummary
    metadata: AIMetadata = AIMetadata()
    clauses: list[AIClause] = Field(default_factory=list, max_length=40)
    risk_findings: list[AIRiskFinding] = Field(
        default_factory=list, max_length=40
    )
    playbook_results: list[AIPlaybookResult] = Field(
        default_factory=list, max_length=60
    )

    @field_validator("clauses", "risk_findings", "playbook_results", mode="before")
    @classmethod
    def none_is_empty_list(cls, value: Any) -> Any:
        return [] if value is None else value


# --------------------------- API responses ---------------------------------


class ReviewSummary(BaseModel):
    overview: str | None = None
    parties: list[str] = []
    commercial_terms: str | None = None
    key_dates_and_obligations: str | None = None


class ReviewMetadata(BaseModel):
    parties: list[str] = []
    effective_date: str | None = None
    expiry_date: str | None = None
    contract_value: str | None = None
    currency: str | None = None
    governing_law: str | None = None
    renewal_terms: str | None = None


class ReviewClause(BaseModel):
    category: str
    title: str
    summary: str
    excerpt: str | None = None
    excerpt_status: ExcerptStatus = "not_provided"


class ReviewRiskFinding(BaseModel):
    title: str
    description: str
    severity: Severity
    category: str
    concern: str
    suggested_action: str
    excerpt: str | None = None
    excerpt_status: ExcerptStatus = "not_provided"
    source: Literal["ai_observation"] = "ai_observation"


class ReviewPlaybookResult(BaseModel):
    rule_id: str
    category: str
    title: str
    requirement: str
    severity_if_not_met: Severity
    status: PlaybookStatus
    explanation: str = ""
    excerpt: str | None = None
    excerpt_status: ExcerptStatus = "not_provided"
    source: Literal["playbook"] = "playbook"


class ReviewPlaybookInfo(BaseModel):
    version: str | None = None
    results: list[ReviewPlaybookResult] = []
    disclaimer: str = (
        "Playbook rules are configured baseline rules, not an approved "
        "company legal policy."
    )


class ReviewSourceInfo(BaseModel):
    method: str | None = None
    pages: int | None = None
    characters_extracted: int | None = None
    characters_analyzed: int | None = None
    truncated: bool = False


class RiskCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ReviewListItem(BaseModel):
    id: UUID
    document_id: UUID | None
    document_version: int | None
    document_filename: str | None
    is_current_version: bool = Field(
        description="True if this review covers the document's latest version."
    )
    provider: str
    model: str
    status: str
    created_at: datetime
    initiated_by_name: str | None
    finding_count: int
    risk_counts: RiskCounts


class ReviewListResponse(BaseModel):
    """Review history, newest first."""

    items: list[ReviewListItem]
    total: int


class ReviewDetail(ReviewListItem):
    contract_id: UUID
    review_type: str
    summary: ReviewSummary
    metadata: ReviewMetadata
    clauses: list[ReviewClause]
    risk_findings: list[ReviewRiskFinding]
    playbook: ReviewPlaybookInfo
    source_info: ReviewSourceInfo
    disclaimer: str = REVIEW_DISCLAIMER


class AIStatusResponse(BaseModel):
    """Whether AI review is available. Never contains credentials."""

    configured: bool
    provider: str | None = None
    model: str | None = None
    message: str | None = None
    max_input_chars: int

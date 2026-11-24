"""AI contract review: orchestration, validation, storage, and history.

Flow for one review of a contract's current document version:
1. Locate the current document version and its stored file (read-only).
2. Check the AI provider is configured (nothing is sent before this).
3. Extract text locally from the stored PDF/DOCX.
4. Ask the provider for a structured JSON review.
5. Validate the JSON, then check every quotation against the real text;
   quotations that cannot be found are dropped, never shown as evidence.
6. Store structured results tied to the exact document version, plus an
   audit event. Contract text, prompts, and raw AI replies are not stored
   or logged.
"""

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.base import AIProvider
from app.ai.errors import AIError, AIResponseFormatError
from app.ai.playbook import Playbook, load_playbook
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.config import Settings
from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.contract_document import ContractDocument
from app.models.enums import ReviewStatus
from app.models.review_result import ReviewResult
from app.models.user import User
from app.schemas.review import (
    AIReviewOutput,
    ReviewClause,
    ReviewDetail,
    ReviewListItem,
    ReviewMetadata,
    ReviewPlaybookInfo,
    ReviewPlaybookResult,
    ReviewRiskFinding,
    ReviewSourceInfo,
    ReviewSummary,
    RiskCounts,
)
from app.services import contracts as contract_service
from app.services import documents as document_service
from app.services.text_extraction import TextExtractionError, extract_text

logger = logging.getLogger(__name__)

REVIEW_TYPE = "full_review"
AUDIT_ENTITY_TYPE = "review"
SEVERITY_ORDER = ("critical", "high", "medium", "low")


# --------------------------- excerpt verification --------------------------


def _compact(value: str) -> str:
    """Normalise for matching: quotes/dashes unified, no whitespace, lowercase."""
    value = (
        value.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
    )
    return re.sub(r"\s+", "", value).casefold()


def verify_excerpt(
    excerpt: str | None, source_compact: str
) -> tuple[str | None, str]:
    """Return ``(excerpt_or_None, status)``.

    An excerpt is kept only if it really occurs in the contract text.
    """
    if not excerpt:
        return None, "not_provided"
    needle = _compact(excerpt)
    if len(needle) >= 8 and needle in source_compact:
        return excerpt, "verified"
    return None, "not_verified"


# ------------------------------ parsing ------------------------------------


def parse_ai_output(raw: str) -> AIReviewOutput:
    """Parse and validate the provider's reply, or raise AIResponseFormatError."""
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIResponseFormatError() from None
        try:
            data = json.loads(text[start : end + 1])
        except ValueError:
            raise AIResponseFormatError() from None

    if not isinstance(data, dict):
        raise AIResponseFormatError()

    try:
        return AIReviewOutput.model_validate(data)
    except ValidationError:
        # Never log the error: it can quote the model's (contract-derived) text.
        raise AIResponseFormatError() from None


# ------------------------------ building -----------------------------------


def _build_results(
    output: AIReviewOutput, playbook: Playbook, source_compact: str
) -> dict:
    clauses = []
    for clause in output.clauses:
        excerpt, excerpt_status = verify_excerpt(clause.excerpt, source_compact)
        clauses.append(
            ReviewClause(
                category=clause.category,
                title=clause.title,
                summary=clause.summary,
                excerpt=excerpt,
                excerpt_status=excerpt_status,
            ).model_dump(mode="json")
        )

    findings = []
    for finding in output.risk_findings:
        excerpt, excerpt_status = verify_excerpt(finding.excerpt, source_compact)
        findings.append(
            ReviewRiskFinding(
                title=finding.title,
                description=finding.description,
                severity=finding.severity,
                category=finding.category,
                concern=finding.concern,
                suggested_action=finding.suggested_action,
                excerpt=excerpt,
                excerpt_status=excerpt_status,
            ).model_dump(mode="json")
        )
    findings.sort(key=lambda f: SEVERITY_ORDER.index(f["severity"]))

    # One result per configured rule, in playbook order. A rule the AI did not
    # answer is shown as "not_assessed" rather than guessed.
    answers = {r.rule_id: r for r in output.playbook_results}
    playbook_results = []
    for rule in playbook.rules:
        answer = answers.get(rule.id)
        excerpt, excerpt_status = (
            verify_excerpt(answer.excerpt, source_compact)
            if answer
            else (None, "not_provided")
        )
        playbook_results.append(
            ReviewPlaybookResult(
                rule_id=rule.id,
                category=rule.category,
                title=rule.title,
                requirement=rule.requirement,
                severity_if_not_met=rule.severity_if_not_met,
                status=answer.status if answer else "not_assessed",
                explanation=(
                    answer.explanation
                    if answer
                    else "The AI did not return an assessment for this rule."
                ),
                excerpt=excerpt,
                excerpt_status=excerpt_status,
            ).model_dump(mode="json")
        )

    return {
        "summary": output.summary.overview,
        "summary_details": ReviewSummary(
            overview=output.summary.overview,
            parties=output.summary.parties,
            commercial_terms=output.summary.commercial_terms,
            key_dates_and_obligations=output.summary.key_dates_and_obligations,
        ).model_dump(mode="json"),
        "metadata": ReviewMetadata(
            **output.metadata.model_dump()
        ).model_dump(mode="json"),
        "clauses": clauses,
        "findings": findings,
        "playbook_results": playbook_results,
    }


# ------------------------------ main flow ----------------------------------


def get_current_document(db: Session, contract_id: UUID) -> ContractDocument:
    document = db.execute(
        select(ContractDocument).where(
            ContractDocument.contract_id == contract_id,
            ContractDocument.is_current.is_(True),
        )
    ).scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload a document before starting an AI review.",
        )
    return document


def _record_audit(
    db: Session,
    *,
    contract: Contract,
    user: User,
    action: str,
    entity_id: str,
    details: dict,
) -> None:
    db.add(
        AuditEvent(
            contract_id=contract.id,
            actor_user_id=user.id,
            action=action,
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=entity_id,
            details={"contract_number": contract.contract_number, **details},
        )
    )


def run_review(
    db: Session,
    *,
    contract: Contract,
    user: User,
    storage_root: Path,
    provider_factory: Callable[[], AIProvider],
    settings: Settings,
) -> ReviewResult:
    document = get_current_document(db, contract.id)
    file_path = document_service.open_stored_file(storage_root, document)

    # Fail early, before reading the file or contacting anyone.
    provider = provider_factory()
    playbook = load_playbook(settings.ai_playbook_path)

    try:
        extracted = extract_text(file_path, document.mime_type)
    except TextExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error.message,
        ) from None

    analyzed = extracted.text[: settings.ai_max_input_chars]
    truncated = extracted.truncated or len(analyzed) < len(extracted.text)

    user_prompt = build_user_prompt(
        contract_text=analyzed,
        playbook=playbook,
        truncated=truncated,
        counterparty_name=contract.counterparty_name,
    )

    try:
        raw = provider.complete_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_output_tokens=settings.ai_max_output_tokens,
        )
        output = parse_ai_output(raw)
    except AIError as error:
        # Contract text was (or may have been) sent, so keep an audit trail of
        # the attempt. Only a short error code is recorded.
        _record_audit(
            db,
            contract=contract,
            user=user,
            action="ai_review.failed",
            entity_id=str(document.id),
            details={
                "document_version": document.version_number,
                "provider": provider.name,
                "model": provider.model,
                "error_code": error.code,
            },
        )
        db.commit()
        raise

    results = _build_results(output, playbook, _compact(analyzed))

    review = ReviewResult(
        # Set explicitly (not the DB default now()) so reviews created in one
        # transaction still order correctly in the history.
        created_at=datetime.now(UTC),
        contract_id=contract.id,
        document_id=document.id,
        document_version=document.version_number,
        provider=provider.name,
        model=provider.model,
        review_type=REVIEW_TYPE,
        status=ReviewStatus.COMPLETED.value,
        initiated_by=user.id,
        summary=results["summary"],
        summary_details=results["summary_details"],
        extracted_metadata=results["metadata"],
        clauses=results["clauses"],
        findings=results["findings"],
        playbook_results=results["playbook_results"],
        playbook_version=playbook.label,
        source_info={
            "method": extracted.method,
            "pages": extracted.pages,
            "characters_extracted": len(extracted.text),
            "characters_analyzed": len(analyzed),
            "truncated": truncated,
        },
    )
    db.add(review)
    db.flush()

    _record_audit(
        db,
        contract=contract,
        user=user,
        action="ai_review.completed",
        entity_id=str(review.id),
        details={
            "document_id": str(document.id),
            "document_version": document.version_number,
            "provider": provider.name,
            "model": provider.model,
            "finding_count": len(results["findings"]),
        },
    )
    db.commit()
    db.refresh(review)
    return review


# ------------------------------ reading ------------------------------------


def _risk_counts(findings: list[dict]) -> RiskCounts:
    counts = {level: 0 for level in SEVERITY_ORDER}
    for finding in findings:
        level = finding.get("severity")
        if level in counts:
            counts[level] += 1
    return RiskCounts(**counts)


def _latest_version(db: Session, contract_id: UUID) -> int | None:
    return db.execute(
        select(ContractDocument.version_number).where(
            ContractDocument.contract_id == contract_id,
            ContractDocument.is_current.is_(True),
        )
    ).scalar_one_or_none()


def _list_item_fields(review: ReviewResult, latest_version: int | None) -> dict:
    return {
        "id": review.id,
        "document_id": review.document_id,
        "document_version": review.document_version,
        "document_filename": (
            review.document.original_filename if review.document else None
        ),
        "is_current_version": (
            review.document_version is not None
            and review.document_version == latest_version
        ),
        "provider": review.provider,
        "model": review.model,
        "status": review.status,
        "created_at": review.created_at,
        "initiated_by_name": (
            review.initiator.full_name if review.initiator else None
        ),
        "finding_count": len(review.findings),
        "risk_counts": _risk_counts(review.findings),
    }


def to_list_item(db: Session, review: ReviewResult) -> ReviewListItem:
    return ReviewListItem(
        **_list_item_fields(review, _latest_version(db, review.contract_id))
    )


def to_detail(db: Session, review: ReviewResult) -> ReviewDetail:
    return ReviewDetail(
        **_list_item_fields(review, _latest_version(db, review.contract_id)),
        contract_id=review.contract_id,
        review_type=review.review_type,
        summary=ReviewSummary.model_validate(
            review.summary_details or {"overview": review.summary}
        ),
        metadata=ReviewMetadata.model_validate(review.extracted_metadata or {}),
        clauses=[ReviewClause.model_validate(c) for c in review.clauses],
        risk_findings=[
            ReviewRiskFinding.model_validate(f) for f in review.findings
        ],
        playbook=ReviewPlaybookInfo(
            version=review.playbook_version,
            results=[
                ReviewPlaybookResult.model_validate(r)
                for r in review.playbook_results
            ],
        ),
        source_info=ReviewSourceInfo.model_validate(review.source_info or {}),
    )


def list_reviews(db: Session, contract_id: UUID) -> list[ReviewResult]:
    return list(
        db.execute(
            select(ReviewResult)
            .options(
                selectinload(ReviewResult.document),
                selectinload(ReviewResult.initiator),
            )
            .where(ReviewResult.contract_id == contract_id)
            .order_by(ReviewResult.created_at.desc(), ReviewResult.id.desc())
        )
        .scalars()
        .all()
    )


def get_review_for_read(
    db: Session, review_id: UUID, user: User
) -> ReviewResult:
    """Load a review the user may read (via its contract), or 404/403."""
    review = db.execute(
        select(ReviewResult)
        .options(
            selectinload(ReviewResult.document),
            selectinload(ReviewResult.initiator),
        )
        .where(ReviewResult.id == review_id)
    ).scalar_one_or_none()

    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    contract_service.get_contract_for_read(db, review.contract_id, user)
    return review

"""AI review API tests. The AI provider is always a fake: no network, no quota."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

import pytest
from helpers import (
    SAMPLE_CLAUSE_TEXT,
    ai_reply,
    create_contract,
    login,
    make_blank_pdf,
    make_docx_with_text,
    make_text_pdf,
    upload_docx,
    upload_pdf,
)
from sqlalchemy import select

from app.ai.errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIModelUnavailableError,
    AIProviderError,
    AIRateLimitError,
    AIRequestTooLargeError,
    AITimeoutError,
)
from app.api.documents import get_storage_root
from app.api.reviews import get_ai_provider_factory
from app.core.config import Settings, get_settings
from app.core.cookies import CSRF_HEADER_NAME
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.contract_document import ContractDocument
from app.models.enums import UserRole
from app.models.review_result import ReviewResult

FAKE_KEY = "gsk_test_FAKE_KEY_do_not_use"


class FakeProvider:
    """Stands in for Groq. Records prompts; returns text or raises."""

    name = "groq"
    model = "fake-model"

    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self.reply = reply if reply is not None else ai_reply()
        self.error = error
        self.calls: list[dict[str, str]] = []

    def complete_json(self, *, system_prompt, user_prompt, max_output_tokens=8000):
        self.calls.append(
            {
                "system": system_prompt,
                "user": user_prompt,
                "max_output_tokens": max_output_tokens,
            }
        )
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def storage_root(client, tmp_path):
    app.dependency_overrides[get_storage_root] = lambda: tmp_path
    return tmp_path


@pytest.fixture
def use_provider():
    """Install a fake provider and return it."""

    def install(provider: FakeProvider) -> FakeProvider:
        app.dependency_overrides[get_ai_provider_factory] = lambda: (lambda: provider)
        return provider

    return install


@pytest.fixture
def owner_contract(client, user_factory, storage_root):
    owner = user_factory()
    csrf = login(client, owner.email)
    return owner, csrf, create_contract(client, csrf)


def start_review(client, csrf, contract_id):
    return client.post(
        f"/api/contracts/{contract_id}/reviews",
        headers={CSRF_HEADER_NAME: csrf} if csrf else {},
    )


# --------------------------- successful reviews -----------------------------


def test_review_of_pdf_stores_structured_results_for_the_document_version(
    client, db_session, owner_contract, use_provider
):
    owner, csrf, contract_id = owner_contract
    document = upload_pdf(client, csrf, contract_id).json()
    provider = use_provider(FakeProvider())

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["document_id"] == document["id"]
    assert body["document_version"] == 1
    assert body["document_filename"] == "agreement.pdf"
    assert body["is_current_version"] is True
    assert (body["provider"], body["model"]) == ("groq", "fake-model")
    assert body["initiated_by_name"] == owner.full_name
    assert body["created_at"]
    assert "human legal reviewer" in body["disclaimer"]

    assert body["summary"]["overview"].startswith("A services agreement")
    assert body["summary"]["parties"] == ["Acme Supplies Pvt Ltd", "Northwind Traders"]
    assert body["metadata"]["governing_law"] == "India"
    assert body["metadata"]["contract_value"] == "500,000"
    # Missing values become null, including "not found" style answers.
    assert body["metadata"]["effective_date"] is None
    assert body["metadata"]["expiry_date"] is None
    assert body["clauses"][0]["category"] == "payment_terms"

    # Risk findings are sorted by severity and labelled as AI observations.
    assert [f["severity"] for f in body["risk_findings"]] == ["high", "medium"]
    assert {f["source"] for f in body["risk_findings"]} == {"ai_observation"}
    assert body["risk_counts"] == {"critical": 0, "high": 1, "medium": 1, "low": 0}
    assert body["finding_count"] == 2

    # Playbook results are separate from AI observations and cover every rule.
    assert body["playbook"]["version"] == "baseline-poc@1"
    assert "not an approved" in body["playbook"]["disclaimer"].lower()
    results = {r["rule_id"]: r for r in body["playbook"]["results"]}
    assert len(results) >= 8
    assert {r["source"] for r in results.values()} == {"playbook"}
    assert results["payment_terms"]["status"] == "met"
    assert results["data_protection"]["status"] == "not_met"
    assert results["renewal"]["status"] == "not_assessed"  # AI did not answer

    assert body["source_info"]["method"] == "pdf-text"
    assert body["source_info"]["truncated"] is False

    # Persisted as structured data, not raw text.
    row = db_session.get(ReviewResult, body["id"])
    assert str(row.document_id) == document["id"] and row.document_version == 1
    assert row.initiated_by == owner.id
    assert row.summary and row.summary_details["parties"]
    assert len(row.findings) == 2 and len(row.clauses) == 1
    assert row.playbook_version == "baseline-poc@1"

    # The model got the contract text, treated as data, and the playbook.
    assert len(provider.calls) == 1
    assert "thirty days of invoice" in " ".join(provider.calls[0]["user"].split())
    assert "untrusted data" in provider.calls[0]["system"]
    assert "payment_terms" in provider.calls[0]["user"]
    assert provider.calls[0]["max_output_tokens"] == get_settings().ai_max_output_tokens
    # The model is told which party is the counterparty (so which is "us").
    assert 'NOT the counterparty "Example Corp"' in provider.calls[0]["user"]


def test_review_of_docx_works(client, owner_contract, use_provider):
    _, csrf, contract_id = owner_contract
    upload_docx(client, csrf, contract_id)
    use_provider(FakeProvider())

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 201, response.text
    assert response.json()["source_info"]["method"] == "docx-xml"


def test_markdown_fenced_json_is_accepted(client, owner_contract, use_provider):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    use_provider(FakeProvider(reply=f"```json\n{ai_reply()}\n```"))

    assert start_review(client, csrf, contract_id).status_code == 201


def test_quotations_are_checked_against_the_document_text(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    reply = json.loads(ai_reply())
    reply["risk_findings"][0]["excerpt"] = "The Supplier shall pay unlimited damages."
    reply["clauses"][0]["excerpt"] = "shall pay the supplier a FEE of INR 500,000  within thirty days"
    use_provider(FakeProvider(reply=json.dumps(reply)))

    body = start_review(client, csrf, contract_id).json()

    findings = {f["title"]: f for f in body["risk_findings"]}
    fabricated = findings["Low liability cap"]
    assert fabricated["excerpt"] is None
    assert fabricated["excerpt_status"] == "not_verified"
    assert findings["No data protection clause"]["excerpt_status"] == "not_provided"
    # Case and whitespace differences still match the real text.
    assert body["clauses"][0]["excerpt_status"] == "verified"
    assert body["clauses"][0]["excerpt"]
    assert "unlimited damages" not in json.dumps(body)


def test_unknown_playbook_rules_are_ignored_and_values_normalised(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    reply = json.loads(ai_reply())
    reply["playbook_results"].append(
        {"rule_id": "invented_rule", "status": "met", "explanation": "x"}
    )
    reply["playbook_results"][0]["status"] = "Partially Met"
    reply["risk_findings"][0]["severity"] = "HIGH"
    reply["risk_findings"][0]["category"] = "Limitation of Liability"
    reply["clauses"][0]["category"] = "something unexpected"
    use_provider(FakeProvider(reply=json.dumps(reply)))

    body = start_review(client, csrf, contract_id).json()

    results = {r["rule_id"]: r for r in body["playbook"]["results"]}
    assert "invented_rule" not in results
    assert results["payment_terms"]["status"] == "partially_met"
    assert {f["severity"] for f in body["risk_findings"]} == {"high"}
    assert "limitation_of_liability" in {f["category"] for f in body["risk_findings"]}
    assert body["clauses"][0]["category"] == "other"


def test_long_documents_are_truncated_and_flagged(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    paragraphs = [f"Clause {i}: the parties agree on matter number {i}." for i in range(400)]
    upload_docx(client, csrf, contract_id, content=make_docx_with_text(*paragraphs))
    provider = use_provider(FakeProvider())
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost/db",
        ai_max_input_chars=1000,
    )

    body = start_review(client, csrf, contract_id).json()

    assert body["source_info"]["truncated"] is True
    assert body["source_info"]["characters_analyzed"] == 1000
    assert body["source_info"]["characters_extracted"] > 1000
    assert "cut off" in provider.calls[0]["user"]
    assert "Clause 399" not in provider.calls[0]["user"]


# ------------------------- history and versions -----------------------------


def test_multiple_reviews_build_a_history_tied_to_document_versions(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    use_provider(FakeProvider())

    upload_pdf(client, csrf, contract_id, name="v1.pdf")
    first = start_review(client, csrf, contract_id).json()
    upload_docx(client, csrf, contract_id, name="v2.docx")
    second = start_review(client, csrf, contract_id).json()
    third = start_review(client, csrf, contract_id).json()

    assert [first["document_version"], second["document_version"]] == [1, 2]
    assert second["document_filename"] == "v2.docx"
    assert first["id"] not in (second["id"], third["id"])

    history = client.get(f"/api/contracts/{contract_id}/reviews").json()
    assert history["total"] == 3
    assert [item["id"] for item in history["items"]] == [
        third["id"],
        second["id"],
        first["id"],
    ]
    assert [item["document_version"] for item in history["items"]] == [2, 2, 1]
    # Only reviews of the latest version are flagged as current.
    assert [item["is_current_version"] for item in history["items"]] == [True, True, False]
    assert history["items"][0]["risk_counts"]["high"] == 1

    detail = client.get(f"/api/reviews/{first['id']}").json()
    assert detail["document_version"] == 1
    assert detail["document_filename"] == "v1.pdf"
    assert detail["is_current_version"] is False
    assert detail["risk_findings"] and detail["playbook"]["results"]


def test_history_is_empty_before_any_review(client, owner_contract):
    _, _, contract_id = owner_contract

    assert client.get(f"/api/contracts/{contract_id}/reviews").json() == {
        "items": [],
        "total": 0,
    }


def test_review_audit_events_contain_no_contract_content(
    client, db_session, owner_contract, use_provider
):
    owner, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    use_provider(FakeProvider())
    review = start_review(client, csrf, contract_id).json()

    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.contract_id == UUID(contract_id),
            AuditEvent.action == "ai_review.completed",
        )
    ).all()

    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "review" and event.entity_id == review["id"]
    assert event.actor_user_id == owner.id
    assert event.details["document_version"] == 1
    assert event.details["finding_count"] == 2
    assert "thirty days" not in json.dumps(event.details)


def test_original_document_is_never_modified(
    client, db_session, owner_contract, use_provider, storage_root
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    row = db_session.scalars(select(ContractDocument).where(
        ContractDocument.contract_id == UUID(contract_id)
    )).one()
    path = storage_root / row.storage_path
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    use_provider(FakeProvider())

    start_review(client, csrf, contract_id)

    assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == before
    db_session.refresh(row)
    assert row.is_current is True and row.version_number == 1


def test_uploading_a_document_never_triggers_an_ai_call(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    provider = use_provider(FakeProvider())

    upload_pdf(client, csrf, contract_id)
    upload_docx(client, csrf, contract_id)

    assert provider.calls == []
    assert client.get(f"/api/contracts/{contract_id}/reviews").json()["total"] == 0


def test_contract_content_is_not_logged(
    client, owner_contract, use_provider, caplog
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    use_provider(FakeProvider())

    with caplog.at_level(logging.DEBUG):
        start_review(client, csrf, contract_id)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "thirty days" not in logged
    assert "Northwind" not in logged
    assert FAKE_KEY not in logged


# ----------------------------- failure handling -----------------------------


def test_no_document_returns_a_clear_message_and_calls_nothing(
    client, db_session, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    provider = use_provider(FakeProvider())

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 409
    assert "Upload a document" in response.json()["detail"]
    assert provider.calls == []
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []


def test_scanned_pdf_without_text_is_not_sent_to_the_provider(
    client, db_session, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id, content=make_blank_pdf(), name="scan.pdf")
    provider = use_provider(FakeProvider())

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 422
    assert "OCR is not supported" in response.json()["detail"]
    assert provider.calls == []
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []


def test_missing_stored_file_returns_a_safe_error(
    client, db_session, owner_contract, use_provider, storage_root
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    row = db_session.scalars(select(ContractDocument).where(
        ContractDocument.contract_id == UUID(contract_id)
    )).one()
    (storage_root / row.storage_path).unlink()
    provider = use_provider(FakeProvider())

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 404
    assert str(storage_root) not in response.text
    assert provider.calls == []


def test_missing_ai_configuration_is_reported_without_breaking_the_app(
    client, db_session, owner_contract
):
    # The autouse fixture leaves the provider "not configured".
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []
    # Everything else still works.
    assert client.get(f"/api/contracts/{contract_id}").status_code == 200
    assert client.get(f"/api/contracts/{contract_id}/documents").status_code == 200


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (AIRateLimitError(), 429, "rate_limited"),
        (AITimeoutError(), 504, "timeout"),
        (AIAuthenticationError(), 502, "provider_authentication"),
        (AIModelUnavailableError(), 502, "model_unavailable"),
        (AIRequestTooLargeError(), 413, "request_too_large"),
        (AIProviderError(), 502, "provider_error"),
    ],
)
def test_provider_failures_return_safe_messages_and_save_nothing(
    client, db_session, owner_contract, use_provider, error, expected_status, expected_code
):
    owner, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    use_provider(FakeProvider(error=error))

    response = start_review(client, csrf, contract_id)

    assert response.status_code == expected_status
    assert response.json()["detail"] == error.message
    assert FAKE_KEY not in response.text
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []

    failed = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.contract_id == UUID(contract_id),
            AuditEvent.action == "ai_review.failed",
        )
    ).all()
    assert len(failed) == 1
    assert failed[0].details["error_code"] == expected_code
    assert "thirty days" not in json.dumps(failed[0].details)


@pytest.mark.parametrize(
    "reply",
    [
        "I'm sorry, I cannot help with that.",
        "[]",
        "{}",
        json.dumps({"summary": {"overview": ""}}),
        json.dumps({"summary": "just a string"}),
        json.dumps({**json.loads(ai_reply()), "risk_findings": "none"}),
        json.dumps(
            {
                **json.loads(ai_reply()),
                "risk_findings": [
                    {
                        "title": "x",
                        "description": "y",
                        "severity": "catastrophic",
                        "concern": "c",
                        "suggested_action": "a",
                    }
                ],
            }
        ),
    ],
)
def test_malformed_ai_responses_are_rejected_not_stored(
    client, db_session, owner_contract, use_provider, reply
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    use_provider(FakeProvider(reply=reply))

    response = start_review(client, csrf, contract_id)

    assert response.status_code == 502
    assert "could not be understood" in response.json()["detail"]
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []
    failed = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.contract_id == UUID(contract_id),
            AuditEvent.action == "ai_review.failed",
        )
    ).one()
    assert failed.details["error_code"] == "malformed_response"


# ------------------------ security and permissions --------------------------


def test_review_endpoints_require_authentication(client, storage_root):
    contract_id, review_id = uuid4(), uuid4()

    assert start_review(client, None, contract_id).status_code == 401
    assert client.get(f"/api/contracts/{contract_id}/reviews").status_code == 401
    assert client.get(f"/api/reviews/{review_id}").status_code == 401
    assert client.get("/api/ai/status").status_code == 401


def test_starting_a_review_requires_csrf(
    client, db_session, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    provider = use_provider(FakeProvider())

    response = start_review(client, None, contract_id)

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"
    assert provider.calls == []
    assert db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all() == []


def test_unknown_contract_and_review_return_404(
    client, user_factory, storage_root, use_provider
):
    user = user_factory()
    csrf = login(client, user.email)
    provider = use_provider(FakeProvider())

    assert start_review(client, csrf, uuid4()).status_code == 404
    assert client.get(f"/api/contracts/{uuid4()}/reviews").status_code == 404
    assert client.get(f"/api/reviews/{uuid4()}").status_code == 404
    assert client.get("/api/reviews/not-a-uuid").status_code == 422
    assert provider.calls == []


def test_users_cannot_review_or_read_contracts_they_cannot_view(
    client, db_session, user_factory, owner_contract, use_provider
):
    _, owner_csrf, contract_id = owner_contract
    upload_pdf(client, owner_csrf, contract_id)
    provider = use_provider(FakeProvider())
    review = start_review(client, owner_csrf, contract_id).json()
    calls_before = len(provider.calls)

    stranger = user_factory()
    stranger_csrf = login(client, stranger.email)

    assert start_review(client, stranger_csrf, contract_id).status_code == 403
    assert client.get(f"/api/contracts/{contract_id}/reviews").status_code == 403
    assert client.get(f"/api/reviews/{review['id']}").status_code == 403
    # No contract text was sent to the provider for the unauthorised attempt.
    assert len(provider.calls) == calls_before
    assert len(db_session.scalars(select(ReviewResult).where(
        ReviewResult.contract_id == UUID(contract_id)
    )).all()) == 1


def test_users_who_can_view_a_contract_can_review_it(
    client, user_factory, owner_contract, use_provider
):
    _, owner_csrf, contract_id = owner_contract
    upload_pdf(client, owner_csrf, contract_id)
    use_provider(FakeProvider())
    first = start_review(client, owner_csrf, contract_id).json()

    reviewer = user_factory(role=UserRole.LEGAL_REVIEWER)
    reviewer_csrf = login(client, reviewer.email)

    assert client.get(f"/api/reviews/{first['id']}").status_code == 200
    second = start_review(client, reviewer_csrf, contract_id)
    assert second.status_code == 201
    assert second.json()["initiated_by_name"] == reviewer.full_name
    assert client.get(f"/api/contracts/{contract_id}/reviews").json()["total"] == 2


def test_a_review_never_changes_the_contract(
    client, owner_contract, use_provider
):
    _, csrf, contract_id = owner_contract
    upload_pdf(client, csrf, contract_id)
    before = client.get(f"/api/contracts/{contract_id}").json()
    use_provider(FakeProvider())

    start_review(client, csrf, contract_id)

    assert client.get(f"/api/contracts/{contract_id}").json() == before


# ------------------------------ AI status -----------------------------------


def settings_override(**values):
    base = {"database_url": "postgresql+psycopg://u:p@localhost/db"}
    return lambda: Settings(_env_file=None, **{**base, **values})


def test_ai_status_reports_configuration_without_secrets(client, user_factory):
    user = user_factory()
    login(client, user.email)

    app.dependency_overrides[get_settings] = settings_override()
    missing = client.get("/api/ai/status").json()
    assert missing["configured"] is False
    assert "not configured" in missing["message"]

    app.dependency_overrides[get_settings] = settings_override(
        ai_provider="groq", groq_api_key=FAKE_KEY, groq_model="some-model"
    )
    response = client.get("/api/ai/status")
    configured = response.json()

    assert configured["configured"] is True
    assert (configured["provider"], configured["model"]) == ("groq", "some-model")
    assert configured["max_input_chars"] == 30000
    assert FAKE_KEY not in response.text
    assert "key" not in " ".join(configured).lower()

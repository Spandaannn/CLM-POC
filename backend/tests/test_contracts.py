"""Contract API tests.

These tests use the real PostgreSQL database through the transaction-scoped
fixtures in conftest.py. Every contract, audit event, user, and session is
rolled back after each test.
"""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.cookies import CSRF_HEADER_NAME
from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.enums import UserRole

TEST_PASSWORD = "Pytest-Password-123!"


def valid_payload(**overrides):
    payload = {
        "title": "Vendor services agreement",
        "contract_type": "Vendor agreement",
        "counterparty_name": "Acme Supplies Pvt Ltd",
        "description": "Annual support contract.",
        "contract_value": "125000.00",
        "currency": "INR",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }
    payload.update(overrides)
    return payload


def login(client, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def create_contract(client, csrf: str, **overrides):
    return client.post(
        "/api/contracts",
        json=valid_payload(**overrides),
        headers={CSRF_HEADER_NAME: csrf},
    )


def update_contract(client, csrf: str, contract_id: str, **overrides):
    return client.patch(
        f"/api/contracts/{contract_id}",
        json=overrides,
        headers={CSRF_HEADER_NAME: csrf},
    )


def audit_events(db_session, contract_id: str) -> list[AuditEvent]:
    return list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.contract_id == UUID(contract_id)
            )
        )
    )


def test_create_contract_generates_server_fields_and_audit_event(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    response = create_contract(
        client,
        csrf,
        title="  Vendor services agreement  ",
        currency="inr",
    )

    assert response.status_code == 201
    body = response.json()
    assert re.fullmatch(r"CTR-\d{4}-[0-9A-F]{8}", body["contract_number"])
    assert body["contract_number"].startswith(
        f"CTR-{datetime.now(UTC).year}-"
    )
    assert body["title"] == "Vendor services agreement"
    assert body["currency"] == "INR"
    assert body["status"] == "draft"
    assert body["created_by"] == str(user.id)
    assert body["created_by_name"] == user.full_name
    assert body["contract_value"] == "125000.00"
    assert "created_at" in body and "updated_at" in body

    events = audit_events(db_session, body["id"])
    assert len(events) == 1
    event = events[0]
    assert event.action == "contract.created"
    assert event.entity_type == "contract"
    assert event.entity_id == body["id"]
    assert event.actor_user_id == user.id
    assert event.details["contract_number"] == body["contract_number"]
    assert event.details["title"] == "Vendor services agreement"
    assert event.details["status"] == "draft"


def test_contract_numbers_are_unique(client, user_factory) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    first = create_contract(client, csrf)
    second = create_contract(client, csrf, title="Second agreement")

    assert first.status_code == 201
    assert second.status_code == 201
    assert (
        first.json()["contract_number"] != second.json()["contract_number"]
    )


def test_create_rejects_client_supplied_system_fields(
    client, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    response = create_contract(
        client,
        csrf,
        created_by=str(uuid4()),
        contract_number="HACK-0001",
        id=str(uuid4()),
        created_at="2020-01-01T00:00:00Z",
        status="approved",
    )

    assert response.status_code == 422
    assert '"input"' not in response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "   "),
        ("contract_type", ""),
        ("counterparty_name", ""),
        ("currency", "RUPEE"),
        ("contract_value", "-1"),
        ("contract_value", "12.345"),
        ("start_date", "2026-12-31"),
        ("end_date", "not-a-date"),
    ],
)
def test_create_validates_input(
    client, user_factory, field: str, value: str
) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    overrides = {field: value}
    if field == "start_date":
        overrides["end_date"] = "2026-01-01"

    response = create_contract(client, csrf, **overrides)

    assert response.status_code == 422
    assert '"input"' not in response.text


def test_contract_endpoints_require_authentication(client) -> None:
    contract_id = uuid4()

    list_response = client.get("/api/contracts")
    detail_response = client.get(f"/api/contracts/{contract_id}")
    create_response = client.post(
        "/api/contracts", json=valid_payload()
    )
    update_response = client.patch(
        f"/api/contracts/{contract_id}", json={"title": "Updated"}
    )

    assert list_response.status_code == 401
    assert detail_response.status_code == 401
    assert create_response.status_code == 401
    assert update_response.status_code == 401
    assert list_response.json()["detail"] == "Not authenticated"


def test_create_and_update_require_csrf(client, user_factory) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    blocked_create = client.post(
        "/api/contracts", json=valid_payload()
    )
    assert blocked_create.status_code == 403
    assert blocked_create.json()["detail"] == "CSRF validation failed"

    created = create_contract(client, csrf)
    assert created.status_code == 201

    blocked_update = client.patch(
        f"/api/contracts/{created.json()['id']}",
        json={"title": "Changed without CSRF"},
    )
    assert blocked_update.status_code == 403
    assert blocked_update.json()["detail"] == "CSRF validation failed"


def test_list_supports_pagination_search_and_filters(
    client, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)

    alpha = create_contract(
        client,
        csrf,
        title="Alpha vendor agreement",
        counterparty_name="Northwind Traders",
        contract_type="Vendor agreement",
    ).json()
    beta = create_contract(
        client,
        csrf,
        title="Beta NDA",
        counterparty_name="Contoso Ltd",
        contract_type="NDA",
    ).json()
    gamma = create_contract(
        client,
        csrf,
        title="Gamma services",
        counterparty_name="Fabrikam",
        contract_type="Service agreement",
    ).json()

    pending = update_contract(
        client, csrf, gamma["id"], status="pending_review"
    )
    assert pending.status_code == 200

    first_page = client.get("/api/contracts?page=1&page_size=2").json()
    assert first_page["total"] == 3
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert first_page["pages"] == 2
    assert len(first_page["items"]) == 2

    second_page = client.get("/api/contracts?page=2&page_size=2").json()
    assert len(second_page["items"]) == 1

    by_counterparty = client.get("/api/contracts?q=Northwind").json()
    assert by_counterparty["total"] == 1
    assert by_counterparty["items"][0]["id"] == alpha["id"]

    by_title_case_insensitive = client.get(
        "/api/contracts?q=alpha"
    ).json()
    assert by_title_case_insensitive["total"] == 1

    by_number = client.get(
        f"/api/contracts?q={beta['contract_number']}"
    ).json()
    assert by_number["total"] == 1
    assert by_number["items"][0]["id"] == beta["id"]

    by_status = client.get(
        "/api/contracts?status=pending_review"
    ).json()
    assert by_status["total"] == 1
    assert by_status["items"][0]["id"] == gamma["id"]

    by_type = client.get("/api/contracts?contract_type=NDA").json()
    assert by_type["total"] == 1
    assert by_type["items"][0]["id"] == beta["id"]

    assert client.get("/api/contracts?status=not-a-status").status_code == 422
    assert client.get("/api/contracts?page=0").status_code == 422
    assert client.get("/api/contracts?page_size=101").status_code == 422


def test_access_is_limited_by_role_and_ownership(
    client, user_factory
) -> None:
    owner = user_factory()
    owner_csrf = login(client, owner.email)
    # Tests share the real database (changes are rolled back), so it may
    # already hold contracts created through the app. Reviewers and admins can
    # see every contract, so their list checks are scoped to this unique title
    # instead of assuming the table is otherwise empty.
    marker = f"Access test {uuid4().hex}"
    contract = create_contract(client, owner_csrf, title=marker).json()

    def visible_test_contract_ids() -> list[str]:
        body = client.get("/api/contracts", params={"q": marker}).json()
        return [item["id"] for item in body["items"]]

    other_business_user = user_factory()
    other_csrf = login(client, other_business_user.email)

    assert (
        client.get(f"/api/contracts/{contract['id']}").status_code == 403
    )
    assert (
        update_contract(
            client, other_csrf, contract["id"], title="Not allowed"
        ).status_code
        == 403
    )
    # Business users see only their own contracts; this user has none.
    other_list = client.get("/api/contracts").json()
    assert other_list["total"] == 0
    assert visible_test_contract_ids() == []

    # A reviewer can read every contract but cannot edit someone else's
    # metadata in this phase.
    reviewer = user_factory(role=UserRole.LEGAL_REVIEWER)
    reviewer_csrf = login(client, reviewer.email)

    assert (
        client.get(f"/api/contracts/{contract['id']}").status_code == 200
    )
    assert visible_test_contract_ids() == [contract["id"]]
    assert (
        update_contract(
            client, reviewer_csrf, contract["id"], title="Not allowed"
        ).status_code
        == 403
    )

    admin = user_factory(role=UserRole.ADMIN)
    admin_csrf = login(client, admin.email)

    assert visible_test_contract_ids() == [contract["id"]]
    admin_update = update_contract(
        client, admin_csrf, contract["id"], title="Admin correction"
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["title"] == "Admin correction"

    # The client's cookie belongs to whoever logged in last, so sign back in
    # as the owner to check the owner's (ownership-scoped) list.
    login(client, owner.email)
    owner_list = client.get("/api/contracts").json()
    assert owner_list["total"] == 1
    assert owner_list["items"][0]["id"] == contract["id"]


def test_get_contract_returns_detail_and_404_for_missing(
    client, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)
    created = create_contract(client, csrf).json()

    response = client.get(f"/api/contracts/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["contract_number"] == created["contract_number"]
    assert body["title"] == "Vendor services agreement"
    assert body["counterparty_name"] == "Acme Supplies Pvt Ltd"
    assert body["created_by"] == str(user.id)
    assert body["created_by_name"] == user.full_name
    assert body["status"] == "draft"

    missing = client.get(f"/api/contracts/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Contract not found"

    malformed = client.get("/api/contracts/not-a-uuid")
    assert malformed.status_code == 422


def test_update_records_changed_fields_in_audit_event(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)
    created = create_contract(client, csrf).json()

    response = update_contract(
        client,
        csrf,
        created["id"],
        title="Renewed vendor agreement",
        contract_value="2500.50",
        status="pending_review",
        end_date="2027-12-31",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Renewed vendor agreement"
    assert body["contract_value"] == "2500.50"
    assert body["status"] == "pending_review"
    assert body["end_date"] == "2027-12-31"
    assert body["contract_number"] == created["contract_number"]
    assert body["created_by"] == created["created_by"]

    events = audit_events(db_session, created["id"])
    actions = {event.action for event in events}
    assert actions == {"contract.created", "contract.updated"}

    updated = next(
        event for event in events if event.action == "contract.updated"
    )
    assert updated.actor_user_id == user.id
    changes = updated.details["changes"]
    assert changes["title"] == {
        "from": "Vendor services agreement",
        "to": "Renewed vendor agreement",
    }
    assert changes["contract_value"] == {
        "from": "125000.00",
        "to": "2500.50",
    }
    assert changes["status"] == {
        "from": "draft",
        "to": "pending_review",
    }
    assert changes["end_date"] == {
        "from": "2026-12-31",
        "to": "2027-12-31",
    }


def test_update_with_no_changes_does_not_add_audit_event(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)
    created = create_contract(client, csrf).json()

    assert len(audit_events(db_session, created["id"])) == 1

    response = update_contract(
        client, csrf, created["id"], title=created["title"]
    )

    assert response.status_code == 200
    assert response.json()["title"] == created["title"]
    assert len(audit_events(db_session, created["id"])) == 1


def test_update_rejects_invalid_input(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    csrf = login(client, user.email)
    created = create_contract(client, csrf).json()

    invalid_requests = [
        {},
        {"status": "not-a-status"},
        {"title": None},
        {"currency": None},
        {"start_date": "2027-01-01"},
        {"created_by": str(uuid4())},
        {"contract_number": "HACK-0002"},
        {"contract_value": "-5"},
    ]

    for payload in invalid_requests:
        response = client.patch(
            f"/api/contracts/{created['id']}",
            json=payload,
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 422, payload

    assert len(audit_events(db_session, created["id"])) == 1

    missing = update_contract(
        client, csrf, str(uuid4()), title="Missing"
    )
    assert missing.status_code == 404


def test_contract_audit_events_survive_contract_deletion(
    db_session, user_factory
) -> None:
    """The audit table uses ON DELETE SET NULL for its contract reference."""
    user = user_factory()
    contract = Contract(
        contract_number=f"CTR-2026-{uuid4().hex[:8].upper()}",
        title="Audit retention test",
        contract_type="NDA",
        counterparty_name="Example Corp",
        currency="INR",
        status="draft",
        created_by=user.id,
    )
    db_session.add(contract)
    db_session.flush()

    event = AuditEvent(
        contract_id=contract.id,
        actor_user_id=user.id,
        action="contract.created",
        entity_type="contract",
        entity_id=str(contract.id),
        details={"title": contract.title},
    )
    db_session.add(event)
    db_session.commit()

    contract_id = contract.id
    db_session.delete(contract)
    db_session.commit()

    stored = db_session.execute(
        select(AuditEvent).where(AuditEvent.entity_id == str(contract_id))
    ).scalar_one()
    db_session.refresh(stored)
    assert stored.contract_id is None
    assert stored.details["title"] == "Audit retention test"

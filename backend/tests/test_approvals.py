"""Approval workflow tests: submission, stages, permissions, history, audit.

Every database query is scoped to the test's own contract (the tests share the
real database, so manual data must not affect them).
"""

import json
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from helpers import ai_reply, create_contract, login, upload_pdf
from sqlalchemy import select, update

from app.api.documents import get_storage_root
from app.api.reviews import get_ai_provider_factory
from app.core.cookies import CSRF_HEADER_NAME
from app.main import app
from app.models.approval_cycle import ApprovalAction, ApprovalCycle
from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.enums import UserRole

LONG_COMMENT = "This needs more work before it can proceed."


# ------------------------------- fixtures -----------------------------------


@pytest.fixture
def storage_root(client, tmp_path):
    app.dependency_overrides[get_storage_root] = lambda: tmp_path
    return tmp_path


@pytest.fixture
def team(user_factory):
    return SimpleNamespace(
        creator=user_factory(),
        reviewer=user_factory(role=UserRole.LEGAL_REVIEWER),
        reviewer2=user_factory(role=UserRole.LEGAL_REVIEWER),
        approver=user_factory(role=UserRole.LEGAL_APPROVER),
        approver2=user_factory(role=UserRole.LEGAL_APPROVER),
        admin=user_factory(role=UserRole.ADMIN),
        stranger=user_factory(),
    )


@pytest.fixture
def draft(client, team, storage_root):
    """A draft contract with an uploaded document, owned by team.creator."""
    csrf = login(client, team.creator.email)
    contract_id = create_contract(client, csrf)
    assert upload_pdf(client, csrf, contract_id).status_code == 201
    return contract_id


# ------------------------------- helpers ------------------------------------


def post(client, csrf, path, body):
    return client.post(
        path, json=body, headers={CSRF_HEADER_NAME: csrf} if csrf else {}
    )


def submit(client, csrf, cid, reviewer, approver, comment=None, kind="submit"):
    return post(
        client,
        csrf,
        f"/api/contracts/{cid}/approval/{kind}",
        {
            "reviewer_id": str(reviewer.id),
            "approver_id": str(approver.id),
            "comment": comment,
        },
    )


def reviewer_act(client, csrf, cid, action, comment=None):
    return post(
        client,
        csrf,
        f"/api/contracts/{cid}/approval/reviewer-action",
        {"action": action, "comment": comment},
    )


def approver_act(client, csrf, cid, action, comment=None):
    return post(
        client,
        csrf,
        f"/api/contracts/{cid}/approval/approver-action",
        {"action": action, "comment": comment},
    )


def state(client, cid):
    response = client.get(f"/api/contracts/{cid}/approval")
    assert response.status_code == 200, response.text
    return response.json()


def submitted(client, team, cid):
    """Submit as the creator with the default reviewer/approver."""
    csrf = login(client, team.creator.email)
    response = submit(client, csrf, cid, team.reviewer, team.approver)
    assert response.status_code == 201, response.text
    return response.json()


def recommended(client, team, cid):
    submitted(client, team, cid)
    csrf = login(client, team.reviewer.email)
    response = reviewer_act(client, csrf, cid, "recommend")
    assert response.status_code == 200, response.text
    return response.json()


def comparable(value):
    """Parse timestamps so equal instants compare equal whatever their zone."""
    if isinstance(value, dict):
        return {
            k: (
                datetime.fromisoformat(v.replace("Z", "+00:00"))
                if k.endswith("_at") and isinstance(v, str)
                else comparable(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


def approval_audit(db_session, cid):
    return list(
        db_session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.contract_id == UUID(cid),
                AuditEvent.entity_type == "approval",
            )
            .order_by(AuditEvent.created_at)
        )
    )


def contract_status(db_session, cid):
    db_session.expire_all()
    return db_session.get(Contract, UUID(cid)).status


# ------------------------------ submission ----------------------------------


def test_successful_submission(client, db_session, team, draft):
    body = submitted(client, team, draft)

    assert body["contract_status"] == "pending_review"
    assert body["workflow_status"] == "pending_reviewer"
    assert body["content_locked"] is True
    cycle = body["current_cycle"]
    assert cycle["cycle_number"] == 1
    assert cycle["reviewer"]["id"] == str(team.reviewer.id)
    assert cycle["approver"]["id"] == str(team.approver.id)
    assert cycle["submitted_by"]["id"] == str(team.creator.id)
    assert cycle["document_version"] == 1
    assert cycle["completed_at"] is None
    assert [a["action_type"] for a in cycle["actions"]] == ["submitted"]
    assert cycle["actions"][0]["actor"]["id"] == str(team.creator.id)
    assert cycle["actions"][0]["created_at"]
    # The creator can do nothing more at this stage.
    assert body["available_actions"] == []
    assert contract_status(db_session, draft) == "pending_review"


def test_submission_with_a_comment_is_stored(client, team, draft):
    csrf = login(client, team.creator.email)

    body = submit(
        client, csrf, draft, team.reviewer, team.approver, "Please review soon."
    ).json()

    assert body["current_cycle"]["actions"][0]["comment"] == "Please review soon."


def test_only_creator_or_admin_can_submit(client, team, draft):
    for person in (team.stranger, team.reviewer, team.approver):
        csrf = login(client, person.email)
        response = submit(client, csrf, draft, team.reviewer2, team.approver2)
        assert response.status_code == 403, person.role

    csrf = login(client, team.admin.email)
    assert submit(client, csrf, draft, team.reviewer, team.approver).status_code == 201


def test_submission_requires_a_document(client, team, storage_root):
    csrf = login(client, team.creator.email)
    cid = create_contract(client, csrf)

    response = submit(client, csrf, cid, team.reviewer, team.approver)

    assert response.status_code == 409
    assert "Upload a document" in response.json()["detail"]
    assert state(client, cid)["workflow_status"] == "not_submitted"


def test_submission_validates_reviewer_and_approver(
    client, db_session, user_factory, team, draft
):
    csrf = login(client, team.creator.email)
    inactive_reviewer = user_factory(role=UserRole.LEGAL_REVIEWER, is_active=False)
    inactive_approver = user_factory(role=UserRole.LEGAL_APPROVER, is_active=False)
    ghost = SimpleNamespace(id=uuid4())

    cases = [
        (team.stranger, team.approver),  # reviewer is a business user
        (team.approver, team.approver2),  # approver used as reviewer
        (team.admin, team.approver),  # admin is not a Legal Reviewer
        (team.reviewer, team.reviewer2),  # reviewer used as approver
        (team.reviewer, team.admin),  # admin is not a Legal Approver
        (inactive_reviewer, team.approver),
        (team.reviewer, inactive_approver),
        (ghost, team.approver),
        (team.reviewer, ghost),
        (team.reviewer, team.reviewer),  # same person in both slots
    ]
    for reviewer, approver in cases:
        response = submit(client, csrf, draft, reviewer, approver)
        assert response.status_code == 422, (reviewer.id, approver.id, response.text)

    assert state(client, draft)["workflow_status"] == "not_submitted"
    assert contract_status(db_session, draft) == "draft"


def test_submission_rejects_malformed_input(client, team, draft):
    csrf = login(client, team.creator.email)
    path = f"/api/contracts/{draft}/approval/submit"

    assert post(client, csrf, path, {}).status_code == 422
    assert post(client, csrf, path, {"reviewer_id": "nope", "approver_id": "x"}).status_code == 422
    extra = {
        "reviewer_id": str(team.reviewer.id),
        "approver_id": str(team.approver.id),
        "status": "approved",
    }
    assert post(client, csrf, path, extra).status_code == 422


def test_creator_cannot_be_their_own_reviewer_or_approver(
    client, user_factory, storage_root
):
    reviewer_creator = user_factory(role=UserRole.LEGAL_REVIEWER)
    other_reviewer = user_factory(role=UserRole.LEGAL_REVIEWER)
    approver = user_factory(role=UserRole.LEGAL_APPROVER)
    csrf = login(client, reviewer_creator.email)
    cid = create_contract(client, csrf)
    upload_pdf(client, csrf, cid)

    response = submit(client, csrf, cid, reviewer_creator, approver)

    assert response.status_code == 422
    assert "creator" in response.json()["detail"]
    # Another reviewer is fine.
    assert submit(client, csrf, cid, other_reviewer, approver).status_code == 201


def test_submit_twice_and_non_draft_are_rejected(client, team, draft):
    submitted(client, team, draft)
    csrf = login(client, team.creator.email)

    again = submit(client, csrf, draft, team.reviewer, team.approver)

    assert again.status_code == 409
    assert "already been submitted" in again.json()["detail"]


# ------------------------- reviewer-stage authorization ---------------------


def test_only_the_assigned_reviewer_or_admin_can_take_reviewer_actions(
    client, db_session, team, draft
):
    submitted(client, team, draft)

    for person in (team.reviewer2, team.approver, team.stranger, team.creator):
        csrf = login(client, person.email)
        response = reviewer_act(client, csrf, draft, "recommend")
        assert response.status_code == 403, person.role

    assert state(client, draft)["workflow_status"] == "pending_reviewer"

    csrf = login(client, team.reviewer.email)
    assert reviewer_act(client, csrf, draft, "recommend").status_code == 200


def test_admin_can_take_reviewer_actions(client, team, draft):
    submitted(client, team, draft)
    csrf = login(client, team.admin.email)

    response = reviewer_act(client, csrf, draft, "recommend")

    assert response.status_code == 200
    action = response.json()["current_cycle"]["actions"][-1]
    assert action["actor"]["id"] == str(team.admin.id)


def test_reviewer_whose_role_changed_loses_their_assignment(
    client, db_session, team, draft
):
    submitted(client, team, draft)
    csrf = login(client, team.reviewer.email)
    team.reviewer.role = UserRole.BUSINESS_USER.value
    db_session.commit()

    response = reviewer_act(client, csrf, draft, "recommend")

    assert response.status_code == 403
    login(client, team.creator.email)
    assert state(client, draft)["workflow_status"] == "pending_reviewer"


def test_reviewer_actions_require_authentication_csrf_and_visibility(
    client, team, draft
):
    submitted(client, team, draft)

    client.cookies.clear()
    assert reviewer_act(client, None, draft, "recommend").status_code == 401
    assert client.get(f"/api/contracts/{draft}/approval").status_code == 401

    login(client, team.reviewer.email)
    assert reviewer_act(client, None, draft, "recommend").status_code == 403  # no CSRF

    csrf = login(client, team.stranger.email)
    assert client.get(f"/api/contracts/{draft}/approval").status_code == 403
    assert reviewer_act(client, csrf, draft, "recommend").status_code == 403
    assert approver_act(client, csrf, draft, "approve").status_code == 403


# ------------------------- approver-stage authorization ---------------------


def test_approver_cannot_act_before_the_reviewer_recommends(client, team, draft):
    submitted(client, team, draft)
    csrf = login(client, team.approver.email)

    response = approver_act(client, csrf, draft, "approve")

    assert response.status_code == 409
    assert "not awaiting final approval" in response.json()["detail"]


def test_only_the_assigned_approver_or_admin_can_take_approver_actions(
    client, team, draft
):
    recommended(client, team, draft)

    for person in (team.approver2, team.reviewer, team.stranger, team.creator):
        csrf = login(client, person.email)
        response = approver_act(client, csrf, draft, "approve")
        assert response.status_code == 403, person.role

    csrf = login(client, team.approver.email)
    assert approver_act(client, csrf, draft, "approve").status_code == 200


def test_admin_can_give_final_approval_but_not_after_recommending(
    client, team, draft
):
    recommended(client, team, draft)
    csrf = login(client, team.admin.email)
    assert approver_act(client, csrf, draft, "approve").status_code == 200


def test_the_same_person_cannot_recommend_and_finally_approve(client, team, draft):
    submitted(client, team, draft)
    csrf = login(client, team.admin.email)
    assert reviewer_act(client, csrf, draft, "recommend").status_code == 200

    response = approver_act(client, csrf, draft, "approve")

    assert response.status_code == 403
    body = state(client, draft)
    assert body["available_actions"] == []
    assert body["workflow_status"] == "pending_approver"


def test_creator_cannot_approve_their_own_contract_even_as_admin(
    client, user_factory, storage_root
):
    admin = user_factory(role=UserRole.ADMIN)
    reviewer = user_factory(role=UserRole.LEGAL_REVIEWER)
    approver = user_factory(role=UserRole.LEGAL_APPROVER)
    csrf = login(client, admin.email)
    cid = create_contract(client, csrf)
    upload_pdf(client, csrf, cid)
    assert submit(client, csrf, cid, reviewer, approver).status_code == 201

    # The admin-creator is offered no decision and is refused if they try.
    assert state(client, cid)["available_actions"] == []
    assert reviewer_act(client, csrf, cid, "recommend").status_code == 403
    assert reviewer_act(client, csrf, cid, "reject", LONG_COMMENT).status_code == 403

    reviewer_csrf = login(client, reviewer.email)
    assert reviewer_act(client, reviewer_csrf, cid, "recommend").status_code == 200

    csrf = login(client, admin.email)
    assert state(client, cid)["available_actions"] == []
    assert approver_act(client, csrf, cid, "approve").status_code == 403
    assert state(client, cid)["workflow_status"] == "pending_approver"


# ----------------------------- full workflows -------------------------------


def test_full_sequential_workflow_to_final_approval(client, db_session, team, draft):
    submitted(client, team, draft)

    csrf = login(client, team.reviewer.email)
    assert state(client, draft)["available_actions"] == [
        "recommend", "request_changes", "reject",
    ]
    body = reviewer_act(client, csrf, draft, "recommend", "Looks good.").json()
    assert body["workflow_status"] == "pending_approver"
    assert body["contract_status"] == "pending_review"
    assert body["available_actions"] == []  # reviewer has nothing left to do

    csrf = login(client, team.approver.email)
    assert state(client, draft)["available_actions"] == [
        "approve", "request_changes", "reject",
    ]
    body = approver_act(client, csrf, draft, "approve", "Approved for signature.").json()

    assert body["workflow_status"] == "approved"
    assert body["contract_status"] == "approved"
    assert body["available_actions"] == []
    cycle = body["current_cycle"]
    assert cycle["completed_at"] is not None
    assert [a["action_type"] for a in cycle["actions"]] == [
        "submitted", "recommended", "approved",
    ]
    assert [a["stage"] for a in cycle["actions"]] == ["creator", "reviewer", "approver"]
    assert [a["sequence"] for a in cycle["actions"]] == [1, 2, 3]
    assert cycle["actions"][1]["comment"] == "Looks good."
    assert cycle["actions"][2]["actor"]["id"] == str(team.approver.id)
    assert contract_status(db_session, draft) == "approved"


def test_approval_comment_is_optional(client, team, draft):
    recommended(client, team, draft)
    csrf = login(client, team.approver.email)

    body = approver_act(client, csrf, draft, "approve").json()

    assert body["workflow_status"] == "approved"
    assert body["current_cycle"]["actions"][-1]["comment"] is None


def test_reviewer_requests_changes_then_creator_resubmits(
    client, db_session, team, draft
):
    submitted(client, team, draft)
    csrf = login(client, team.reviewer.email)
    body = reviewer_act(client, csrf, draft, "request_changes", LONG_COMMENT).json()

    assert body["workflow_status"] == "changes_requested"
    assert body["contract_status"] == "draft"
    assert body["content_locked"] is False
    assert body["current_cycle"]["completed_at"] is not None
    assert body["available_actions"] == []  # reviewers cannot resubmit

    # The creator can edit again, and is offered "resubmit".
    csrf = login(client, team.creator.email)
    assert state(client, draft)["available_actions"] == ["resubmit"]
    edit = client.patch(
        f"/api/contracts/{draft}",
        json={"title": "Revised after review"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert edit.status_code == 200

    body = submit(
        client, csrf, draft, team.reviewer2, team.approver2, "Fixed.", kind="resubmit"
    ).json()
    assert body["workflow_status"] == "pending_reviewer"
    assert body["contract_status"] == "pending_review"
    assert body["current_cycle"]["cycle_number"] == 2
    assert body["current_cycle"]["reviewer"]["id"] == str(team.reviewer2.id)
    assert [a["action_type"] for a in body["current_cycle"]["actions"]] == ["resubmitted"]
    assert [c["cycle_number"] for c in body["cycles"]] == [2, 1]
    assert contract_status(db_session, draft) == "pending_review"


def test_approver_requests_changes(client, team, draft):
    recommended(client, team, draft)
    csrf = login(client, team.approver.email)

    body = approver_act(client, csrf, draft, "request_changes", LONG_COMMENT).json()

    assert body["workflow_status"] == "changes_requested"
    assert body["contract_status"] == "draft"
    last = body["current_cycle"]["actions"][-1]
    assert (last["action_type"], last["stage"]) == ("changes_requested", "approver")


@pytest.mark.parametrize("stage", ["reviewer", "approver"])
def test_rejection_is_final(client, db_session, team, draft, stage):
    if stage == "reviewer":
        submitted(client, team, draft)
        csrf = login(client, team.reviewer.email)
        body = reviewer_act(client, csrf, draft, "reject", LONG_COMMENT).json()
    else:
        recommended(client, team, draft)
        csrf = login(client, team.approver.email)
        body = approver_act(client, csrf, draft, "reject", LONG_COMMENT).json()

    assert body["workflow_status"] == "rejected"
    assert body["contract_status"] == "rejected"
    assert body["current_cycle"]["actions"][-1]["action_type"] == "rejected"
    assert body["current_cycle"]["actions"][-1]["comment"] == LONG_COMMENT

    # Nothing more can happen to a rejected contract.
    assert reviewer_act(client, login(client, team.reviewer.email), draft, "recommend").status_code == 409
    assert approver_act(client, login(client, team.approver.email), draft, "approve").status_code == 409
    creator_csrf = login(client, team.creator.email)
    assert submit(client, creator_csrf, draft, team.reviewer, team.approver, kind="resubmit").status_code == 409
    assert submit(client, creator_csrf, draft, team.reviewer, team.approver).status_code == 409
    assert state(client, draft)["available_actions"] == []
    assert contract_status(db_session, draft) == "rejected"


# ---------------------------- mandatory comments ----------------------------


@pytest.mark.parametrize("comment", [None, "", "   ", "too short", "123456789"])
@pytest.mark.parametrize("action", ["request_changes", "reject"])
def test_changes_and_rejection_require_a_meaningful_comment(
    client, db_session, team, draft, action, comment
):
    submitted(client, team, draft)
    csrf = login(client, team.reviewer.email)

    response = reviewer_act(client, csrf, draft, action, comment)

    assert response.status_code == 422
    assert "comment" in response.json()["detail"]
    assert state(client, draft)["workflow_status"] == "pending_reviewer"
    assert contract_status(db_session, draft) == "pending_review"


def test_approver_stage_comments_are_also_mandatory(client, team, draft):
    recommended(client, team, draft)
    csrf = login(client, team.approver.email)

    assert approver_act(client, csrf, draft, "reject", "no").status_code == 422
    assert approver_act(client, csrf, draft, "request_changes", None).status_code == 422
    assert approver_act(client, csrf, draft, "approve", None).status_code == 200


def test_unknown_actions_and_overlong_comments_are_rejected(client, team, draft):
    submitted(client, team, draft)
    csrf = login(client, team.reviewer.email)

    assert reviewer_act(client, csrf, draft, "approve").status_code == 422
    assert reviewer_act(client, csrf, draft, "delete").status_code == 422
    assert reviewer_act(client, csrf, draft, "recommend", "x" * 2001).status_code == 422


# ------------------------ duplicate / invalid transitions -------------------


def test_duplicate_and_out_of_order_actions_are_rejected(client, team, draft):
    recommended(client, team, draft)
    reviewer_csrf = login(client, team.reviewer.email)

    # The reviewer already recommended: acting again is invalid.
    assert reviewer_act(client, reviewer_csrf, draft, "recommend").status_code == 409
    assert reviewer_act(client, reviewer_csrf, draft, "reject", LONG_COMMENT).status_code == 409

    approver_csrf = login(client, team.approver.email)
    assert approver_act(client, approver_csrf, draft, "approve").status_code == 200
    # Final approval cannot be repeated or reversed.
    assert approver_act(client, approver_csrf, draft, "approve").status_code == 409
    assert approver_act(client, approver_csrf, draft, "reject", LONG_COMMENT).status_code == 409
    creator_csrf = login(client, team.creator.email)
    assert submit(client, creator_csrf, draft, team.reviewer, team.approver, kind="resubmit").status_code == 409

    cycle = state(client, draft)["current_cycle"]
    assert [a["action_type"] for a in cycle["actions"]] == [
        "submitted", "recommended", "approved",
    ]


def test_resubmit_is_only_valid_after_changes_were_requested(client, team, draft):
    csrf = login(client, team.creator.email)
    # Never submitted.
    assert submit(client, csrf, draft, team.reviewer, team.approver, kind="resubmit").status_code == 409
    submitted(client, team, draft)
    csrf = login(client, team.creator.email)
    # Under review.
    assert submit(client, csrf, draft, team.reviewer, team.approver, kind="resubmit").status_code == 409


def test_cannot_use_submit_when_changes_were_requested(client, team, draft):
    submitted(client, team, draft)
    reviewer_act(client, login(client, team.reviewer.email), draft, "request_changes", LONG_COMMENT)
    csrf = login(client, team.creator.email)

    response = submit(client, csrf, draft, team.reviewer, team.approver)

    assert response.status_code == 409
    assert "resubmit" in response.json()["detail"]


def test_only_one_open_cycle_is_possible(client, db_session, team, draft):
    submitted(client, team, draft)

    open_cycles = db_session.scalars(
        select(ApprovalCycle).where(
            ApprovalCycle.contract_id == UUID(draft),
            ApprovalCycle.status.in_(["pending_reviewer", "pending_approver"]),
        )
    ).all()
    assert len(open_cycles) == 1


# ------------------------- history across several cycles --------------------


def test_history_is_kept_across_multiple_cycles(client, db_session, team, draft):
    creator_csrf = login(client, team.creator.email)

    # Cycle 1: reviewer asks for changes.
    submitted(client, team, draft)
    reviewer_act(client, login(client, team.reviewer.email), draft, "request_changes", "Cycle one feedback here.")
    cycle1_before = state(client, draft)["cycles"][0]

    # Cycle 2: different people; approver asks for changes.
    creator_csrf = login(client, team.creator.email)
    submit(client, creator_csrf, draft, team.reviewer2, team.approver2, "Second try", kind="resubmit")
    reviewer_act(client, login(client, team.reviewer2.email), draft, "recommend", "Fine by me.")
    approver_act(client, login(client, team.approver2.email), draft, "request_changes", "Cycle two feedback here.")

    # Cycle 3: approved.
    creator_csrf = login(client, team.creator.email)
    submit(client, creator_csrf, draft, team.reviewer, team.approver, "Third try", kind="resubmit")
    reviewer_act(client, login(client, team.reviewer.email), draft, "recommend")
    final = approver_act(client, login(client, team.approver.email), draft, "approve", "Done.").json()

    assert final["workflow_status"] == "approved"
    assert [c["cycle_number"] for c in final["cycles"]] == [3, 2, 1]
    assert [c["status"] for c in final["cycles"]] == ["approved", "changes_requested", "changes_requested"]
    by_number = {c["cycle_number"]: c for c in final["cycles"]}
    assert [a["action_type"] for a in by_number[2]["actions"]] == ["resubmitted", "recommended", "changes_requested"]
    assert by_number[2]["reviewer"]["id"] == str(team.reviewer2.id)
    assert by_number[2]["actions"][-1]["comment"] == "Cycle two feedback here."
    assert by_number[3]["actions"][0]["comment"] == "Third try"

    # Cycle 1 is byte-for-byte what it was before later cycles existed.
    assert comparable(by_number[1]) == comparable(cycle1_before)
    assert by_number[1]["actions"][-1]["comment"] == "Cycle one feedback here."

    rows = db_session.scalars(
        select(ApprovalCycle).where(ApprovalCycle.contract_id == UUID(draft))
    ).all()
    assert sorted(r.cycle_number for r in rows) == [1, 2, 3]
    total_actions = db_session.scalars(
        select(ApprovalAction).where(ApprovalAction.cycle_id.in_([r.id for r in rows]))
    ).all()
    assert len(total_actions) == 2 + 3 + 3  # cycle 1, 2, 3


# ------------------------------- audit events -------------------------------


def test_every_workflow_step_creates_an_audit_event(client, db_session, team, draft):
    creator_csrf = login(client, team.creator.email)
    submit(client, creator_csrf, draft, team.reviewer, team.approver, "SECRET-COMMENT-TEXT")
    reviewer_act(client, login(client, team.reviewer.email), draft, "request_changes", LONG_COMMENT)
    creator_csrf = login(client, team.creator.email)
    submit(client, creator_csrf, draft, team.reviewer, team.approver, kind="resubmit")
    reviewer_act(client, login(client, team.reviewer.email), draft, "recommend")
    approver_act(client, login(client, team.approver.email), draft, "approve")

    events = approval_audit(db_session, draft)

    assert [e.action for e in events] == [
        "approval.submitted",
        "approval.changes_requested",
        "approval.resubmitted",
        "approval.recommended",
        "approval.approved",
    ]
    assert [e.actor_user_id for e in events] == [
        team.creator.id, team.reviewer.id, team.creator.id, team.reviewer.id, team.approver.id,
    ]
    first, _, _, _, last = events
    assert first.details["cycle_number"] == 1 and last.details["cycle_number"] == 2
    assert first.details["contract_status"] == {"from": "draft", "to": "pending_review"}
    assert last.details["contract_status"] == {"from": "pending_review", "to": "approved"}
    assert first.details["reviewer_id"] == str(team.reviewer.id)
    assert first.details["has_comment"] is True
    # Comments live in the action log, not in the audit details.
    assert "SECRET-COMMENT-TEXT" not in json.dumps([e.details for e in events])


def test_failed_actions_create_no_audit_event_or_history(client, db_session, team, draft):
    submitted(client, team, draft)
    before = len(approval_audit(db_session, draft))

    reviewer_act(client, login(client, team.stranger.email), draft, "recommend")
    reviewer_act(client, login(client, team.reviewer.email), draft, "reject", "short")
    approver_act(client, login(client, team.approver.email), draft, "approve")

    assert len(approval_audit(db_session, draft)) == before
    assert len(state(client, draft)["current_cycle"]["actions"]) == 1


# ---------------- locking: edits, uploads, and status bypass ----------------


def test_contract_cannot_be_edited_or_given_new_documents_while_under_approval(
    client, db_session, team, draft
):
    submitted(client, team, draft)
    csrf = login(client, team.creator.email)

    edit = client.patch(
        f"/api/contracts/{draft}", json={"title": "Sneaky change"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    upload = upload_pdf(client, csrf, draft, name="sneaky.pdf")

    assert edit.status_code == 409
    assert "under approval" in edit.json()["detail"]
    assert upload.status_code == 409
    assert "under approval" in upload.json()["detail"]
    # Same for an admin; nothing changed.
    admin_csrf = login(client, team.admin.email)
    assert client.patch(
        f"/api/contracts/{draft}", json={"title": "Admin change"},
        headers={CSRF_HEADER_NAME: admin_csrf},
    ).status_code == 409
    docs = client.get(f"/api/contracts/{draft}/documents").json()
    assert docs["total"] == 1 and docs["current"]["version_number"] == 1
    assert client.get(f"/api/contracts/{draft}").json()["title"] == "AI review test contract"


def test_awaiting_final_approval_is_also_locked(client, team, draft):
    recommended(client, team, draft)
    csrf = login(client, team.creator.email)

    assert client.patch(
        f"/api/contracts/{draft}", json={"description": "late edit"},
        headers={CSRF_HEADER_NAME: csrf},
    ).status_code == 409
    assert upload_pdf(client, csrf, draft).status_code == 409


def test_rejected_and_approved_contracts_cannot_be_edited(client, team, storage_root):
    for outcome in ("reject", "approve"):
        csrf = login(client, team.creator.email)
        cid = create_contract(client, csrf)
        upload_pdf(client, csrf, cid)
        submit(client, csrf, cid, team.reviewer, team.approver)
        reviewer_act(client, login(client, team.reviewer.email), cid, "recommend")
        approver = login(client, team.approver.email)
        if outcome == "reject":
            approver_act(client, approver, cid, "reject", LONG_COMMENT)
        else:
            approver_act(client, approver, cid, "approve")

        csrf = login(client, team.creator.email)
        response = client.patch(
            f"/api/contracts/{cid}", json={"title": "After the decision"},
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 409, outcome
        assert upload_pdf(client, csrf, cid).status_code == 409, outcome


def test_status_cannot_be_set_by_a_plain_edit(client, db_session, team, draft):
    csrf = login(client, team.creator.email)

    for target in ("approved", "pending_review", "rejected", "active"):
        response = client.patch(
            f"/api/contracts/{draft}", json={"status": target},
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 409, target
    assert contract_status(db_session, draft) == "draft"
    # An admin cannot bypass the workflow this way either.
    admin_csrf = login(client, team.admin.email)
    assert client.patch(
        f"/api/contracts/{draft}", json={"status": "approved"},
        headers={CSRF_HEADER_NAME: admin_csrf},
    ).status_code == 409


def test_lifecycle_status_changes_are_allowed_only_after_approval(
    client, db_session, team, draft
):
    recommended(client, team, draft)
    approver_act(client, login(client, team.approver.email), draft, "approve")
    csrf = login(client, team.creator.email)

    activate = client.patch(
        f"/api/contracts/{draft}", json={"status": "active"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert activate.status_code == 200
    assert activate.json()["status"] == "active"
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.contract_id == UUID(draft),
            AuditEvent.action == "contract.updated",
        )
    ).all()
    assert events[-1].details["changes"]["status"] == {"from": "approved", "to": "active"}
    # Content is still fixed, and workflow statuses are still off limits.
    assert client.patch(
        f"/api/contracts/{draft}", json={"title": "Changed"},
        headers={CSRF_HEADER_NAME: csrf},
    ).status_code == 409
    assert client.patch(
        f"/api/contracts/{draft}", json={"status": "draft"},
        headers={CSRF_HEADER_NAME: csrf},
    ).status_code == 409


def test_resending_unchanged_fields_with_a_status_change_is_allowed(
    client, team, draft
):
    """The edit form always sends every field; unchanged ones must not block."""
    recommended(client, team, draft)
    approver_act(client, login(client, team.approver.email), draft, "approve")
    csrf = login(client, team.creator.email)
    current = client.get(f"/api/contracts/{draft}").json()

    response = client.patch(
        f"/api/contracts/{draft}",
        json={
            "title": current["title"],
            "contract_type": current["contract_type"],
            "counterparty_name": current["counterparty_name"],
            "status": "terminated",
        },
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "terminated"


def test_document_versioning_still_works_for_drafts_and_after_changes_requested(
    client, team, draft
):
    csrf = login(client, team.creator.email)
    assert upload_pdf(client, csrf, draft, name="v2.pdf").json()["version_number"] == 2

    submit(client, csrf, draft, team.reviewer, team.approver)
    assert state(client, draft)["current_cycle"]["document_version"] == 2
    reviewer_act(client, login(client, team.reviewer.email), draft, "request_changes", LONG_COMMENT)

    csrf = login(client, team.creator.email)
    assert upload_pdf(client, csrf, draft, name="v3.pdf").json()["version_number"] == 3
    body = submit(client, csrf, draft, team.reviewer, team.approver, kind="resubmit").json()
    assert body["current_cycle"]["document_version"] == 3
    # The first cycle still records the version that was originally submitted.
    assert body["cycles"][1]["document_version"] == 2


# --------------------- AI review is advisory only ---------------------------


class _FakeProvider:
    name = "groq"
    model = "fake-model"

    def complete_json(self, *, system_prompt, user_prompt, max_output_tokens=8000):
        return ai_reply()


def test_ai_review_never_changes_the_approval_state(client, team, draft):
    submitted(client, team, draft)
    before = state(client, draft)
    provider = _FakeProvider()
    app.dependency_overrides[get_ai_provider_factory] = lambda: (lambda: provider)

    csrf = login(client, team.reviewer.email)
    response = client.post(
        f"/api/contracts/{draft}/reviews", headers={CSRF_HEADER_NAME: csrf}
    )

    assert response.status_code == 201, response.text
    after = state(client, draft)
    assert after["workflow_status"] == before["workflow_status"] == "pending_reviewer"
    assert after["contract_status"] == "pending_review"
    assert comparable(after["current_cycle"]) == comparable(before["current_cycle"])
    assert "advisory" in after["advisory_note"]


# ------------------------- assignees and dashboard --------------------------


def test_assignees_list_only_active_reviewers_and_approvers(
    client, user_factory, team
):
    inactive = user_factory(role=UserRole.LEGAL_REVIEWER, is_active=False)
    login(client, team.creator.email)

    body = client.get("/api/approvals/assignees").json()

    reviewer_ids = {r["id"] for r in body["reviewers"]}
    approver_ids = {a["id"] for a in body["approvers"]}
    assert str(team.reviewer.id) in reviewer_ids
    assert str(team.approver.id) in approver_ids
    assert str(inactive.id) not in reviewer_ids
    assert str(team.admin.id) not in reviewer_ids | approver_ids
    assert str(team.creator.id) not in reviewer_ids | approver_ids
    assert {r["role"] for r in body["reviewers"]} == {"legal_reviewer"}
    assert {a["role"] for a in body["approvers"]} == {"legal_approver"}
    assert "password" not in json.dumps(body).lower()

    client.cookies.clear()
    assert client.get("/api/approvals/assignees").status_code == 401


def test_dashboard_summary_shows_what_awaits_each_person(client, team, draft):
    submitted(client, team, draft)

    reviewer_view = None
    login(client, team.reviewer.email)
    reviewer_view = client.get("/api/approvals/summary").json()
    mine = [i for i in reviewer_view["awaiting_my_action"] if i["contract_id"] == draft]
    assert len(mine) == 1
    assert (mine[0]["cycle_number"], mine[0]["status"]) == (1, "pending_reviewer")
    assert reviewer_view["awaiting_my_action_count"] >= 1

    login(client, team.approver.email)  # nothing awaits the approver yet
    approver_view = client.get("/api/approvals/summary").json()
    assert all(i["contract_id"] != draft for i in approver_view["awaiting_my_action"])

    login(client, team.creator.email)
    creator_view = client.get("/api/approvals/summary").json()
    ours = [i for i in creator_view["my_contracts"] if i["contract_id"] == draft]
    assert len(ours) == 1 and ours[0]["status"] == "pending_reviewer"
    assert creator_view["under_approval_count"] >= 1
    assert all(i["contract_id"] != draft for i in creator_view["awaiting_my_action"])

    reviewer_act(client, login(client, team.reviewer.email), draft, "recommend")
    login(client, team.approver.email)
    approver_view = client.get("/api/approvals/summary").json()
    assert any(i["contract_id"] == draft for i in approver_view["awaiting_my_action"])

    approver_act(client, login(client, team.approver.email), draft, "request_changes", LONG_COMMENT)
    login(client, team.creator.email)
    creator_view = client.get("/api/approvals/summary").json()
    ours = [i for i in creator_view["my_contracts"] if i["contract_id"] == draft]
    assert ours and ours[0]["status"] == "changes_requested"
    assert creator_view["changes_requested_count"] >= 1


def test_summary_requires_authentication(client):
    assert client.get("/api/approvals/summary").status_code == 401

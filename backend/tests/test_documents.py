"""Document upload, versioning, listing, and download tests.

Files are written to a per-test temporary directory (never the real storage
path) and database changes are rolled back after each test.
"""

import io
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.api.documents import get_storage_root
from app.core.cookies import CSRF_HEADER_NAME
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.contract_document import ContractDocument
from app.models.enums import UserRole
from app.services.documents import (
    DOCX_MIME,
    MAX_UPLOAD_BYTES,
    PDF_MIME,
)

TEST_PASSWORD = "Pytest-Password-123!"


def make_pdf(extra: int = 0) -> bytes:
    body = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    return body + b"\0" * extra


def make_docx(text: str = "Hello") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats'
            '.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "word/document.xml", f"<w:document>{text}</w:document>"
        )
    return buffer.getvalue()


@pytest.fixture
def storage_root(client, tmp_path):
    """Point document storage at a temporary directory for this test."""
    app.dependency_overrides[get_storage_root] = lambda: tmp_path
    return tmp_path


def login(client, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def create_contract(client, csrf: str) -> str:
    response = client.post(
        "/api/contracts",
        json={
            "title": "Document test contract",
            "contract_type": "NDA",
            "counterparty_name": "Example Corp",
        },
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(
    client,
    csrf,
    contract_id,
    *,
    name="agreement.pdf",
    content=None,
    mime=PDF_MIME,
):
    return client.post(
        f"/api/contracts/{contract_id}/documents",
        files={"file": (name, make_pdf() if content is None else content, mime)},
        headers={CSRF_HEADER_NAME: csrf} if csrf else {},
    )


@pytest.fixture
def owner_contract(client, user_factory, storage_root):
    owner = user_factory()
    csrf = login(client, owner.email)
    return owner, csrf, create_contract(client, csrf)


def stored_files(root):
    return [path for path in root.rglob("*") if path.is_file()]


def test_upload_valid_pdf(client, db_session, owner_contract, storage_root):
    owner, csrf, contract_id = owner_contract
    content = make_pdf()

    response = upload(client, csrf, contract_id, content=content)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "agreement.pdf"
    assert body["mime_type"] == PDF_MIME
    assert body["file_size"] == len(content)
    assert body["version_number"] == 1
    assert body["is_current"] is True
    assert body["uploaded_by"] == str(owner.id)
    assert body["uploaded_by_name"] == owner.full_name
    assert body["uploaded_at"]
    # Internal storage details must never reach the client.
    assert "storage_path" not in body and "stored_filename" not in body
    assert str(storage_root) not in response.text

    row = db_session.get(ContractDocument, body["id"])
    assert (storage_root / row.storage_path).read_bytes() == content
    assert row.stored_filename == f"{body['id']}.pdf"


def test_upload_valid_docx(client, owner_contract, storage_root):
    _, csrf, contract_id = owner_contract

    response = upload(
        client,
        csrf,
        contract_id,
        name="terms.docx",
        content=make_docx(),
        mime=DOCX_MIME,
    )

    assert response.status_code == 201, response.text
    assert response.json()["mime_type"] == DOCX_MIME
    assert len(stored_files(storage_root)) == 1


def test_docx_with_generic_browser_mime_is_accepted(
    client, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract

    response = upload(
        client,
        csrf,
        contract_id,
        name="terms.docx",
        content=make_docx(),
        mime="application/octet-stream",
    )

    assert response.status_code == 201
    assert response.json()["mime_type"] == DOCX_MIME


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        ("notes.txt", b"plain text", "text/plain"),
        ("program.exe", b"MZ\x90\x00", "application/octet-stream"),
        ("macro.docm", make_docx(), DOCX_MIME),
        ("noextension", make_pdf(), PDF_MIME),
        # Extension and content type disagree.
        ("agreement.pdf", make_pdf(), "text/plain"),
        ("agreement.pdf", make_pdf(), DOCX_MIME),
        # Content is not what the name claims.
        ("fake.pdf", b"This is not a PDF", PDF_MIME),
        ("fake.docx", b"This is not a zip", DOCX_MIME),
        ("renamed.pdf", make_docx(), PDF_MIME),
        ("renamed.docx", make_pdf(), DOCX_MIME),
    ],
)
def test_upload_rejects_invalid_files(
    client, db_session, owner_contract, storage_root, name, content, mime
):
    _, csrf, contract_id = owner_contract

    response = upload(
        client, csrf, contract_id, name=name, content=content, mime=mime
    )

    assert response.status_code == 415, response.text
    assert str(storage_root) not in response.text
    assert stored_files(storage_root) == []
    assert db_session.scalars(select(ContractDocument).where(
        ContractDocument.contract_id == UUID(contract_id)
    )).all() == []
    assert (
        db_session.scalars(
            select(AuditEvent).where(
            AuditEvent.contract_id == UUID(contract_id),
            AuditEvent.action == "document.uploaded",
        )
        ).all()
        == []
    )


def test_docx_without_word_content_is_rejected(
    client, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "just a zip")

    response = upload(
        client,
        csrf,
        contract_id,
        name="archive.docx",
        content=buffer.getvalue(),
        mime=DOCX_MIME,
    )

    assert response.status_code == 415
    assert stored_files(storage_root) == []


def test_empty_file_is_rejected(client, owner_contract, storage_root):
    _, csrf, contract_id = owner_contract

    response = upload(client, csrf, contract_id, content=b"")

    assert response.status_code == 422
    assert stored_files(storage_root) == []


def test_oversized_file_is_rejected_and_limit_is_inclusive(
    client, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract

    too_big = make_pdf(MAX_UPLOAD_BYTES - len(make_pdf()) + 1)
    assert len(too_big) == MAX_UPLOAD_BYTES + 1
    response = upload(client, csrf, contract_id, content=too_big)
    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]
    assert stored_files(storage_root) == []

    exactly_max = make_pdf(MAX_UPLOAD_BYTES - len(make_pdf()))
    assert len(exactly_max) == MAX_UPLOAD_BYTES
    assert upload(client, csrf, contract_id, content=exactly_max).status_code == 201


def test_upload_to_nonexistent_contract_returns_404(
    client, user_factory, storage_root
):
    user = user_factory()
    csrf = login(client, user.email)

    response = upload(client, csrf, uuid4())

    assert response.status_code == 404
    assert stored_files(storage_root) == []


def test_upload_requires_csrf(client, owner_contract, storage_root):
    _, csrf, contract_id = owner_contract

    response = upload(client, None, contract_id)

    assert response.status_code == 403
    assert stored_files(storage_root) == []


def test_document_endpoints_require_authentication(client, storage_root):
    contract_id, document_id = uuid4(), uuid4()

    assert upload(client, None, contract_id).status_code == 401
    assert (
        client.get(f"/api/contracts/{contract_id}/documents").status_code == 401
    )
    assert client.get(f"/api/documents/{document_id}").status_code == 401
    assert (
        client.get(f"/api/documents/{document_id}/download").status_code == 401
    )


def test_new_upload_creates_next_version_and_keeps_old_files(
    client, db_session, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    first_content = make_pdf()
    second_content = make_docx("second")

    first = upload(client, csrf, contract_id, content=first_content).json()
    second = upload(
        client,
        csrf,
        contract_id,
        name="agreement-v2.docx",
        content=second_content,
        mime=DOCX_MIME,
    ).json()

    assert (first["version_number"], second["version_number"]) == (1, 2)
    assert second["is_current"] is True
    assert first["id"] != second["id"]

    listing = client.get(f"/api/contracts/{contract_id}/documents").json()
    assert listing["total"] == 2
    assert [item["version_number"] for item in listing["items"]] == [2, 1]
    assert [item["is_current"] for item in listing["items"]] == [True, False]
    assert listing["current"]["id"] == second["id"]

    # Both physical files survive and neither overwrote the other.
    rows = {
        row.version_number: row
        for row in db_session.scalars(select(ContractDocument).where(
        ContractDocument.contract_id == UUID(contract_id)
    ))
    }
    assert (storage_root / rows[1].storage_path).read_bytes() == first_content
    assert (storage_root / rows[2].storage_path).read_bytes() == second_content
    assert rows[1].storage_path != rows[2].storage_path

    # Metadata of the old version reports the whole history.
    detail = client.get(f"/api/documents/{first['id']}").json()
    assert detail["version_number"] == 1
    assert detail["is_current"] is False
    assert detail["latest_version_number"] == 2
    assert [v["version_number"] for v in detail["versions"]] == [2, 1]


def test_versions_are_per_contract(client, user_factory, storage_root):
    owner = user_factory()
    csrf = login(client, owner.email)
    first_contract = create_contract(client, csrf)
    second_contract = create_contract(client, csrf)

    upload(client, csrf, first_contract)
    upload(client, csrf, first_contract)
    other = upload(client, csrf, second_contract).json()

    assert other["version_number"] == 1
    assert other["is_current"] is True


def test_upload_creates_audit_event(
    client, db_session, owner_contract, storage_root
):
    owner, csrf, contract_id = owner_contract
    document = upload(client, csrf, contract_id, name="Master.pdf").json()

    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.contract_id == UUID(contract_id),
            AuditEvent.action == "document.uploaded",
        )
    ).all()

    assert len(events) == 1
    event = events[0]
    assert str(event.contract_id) == contract_id
    assert event.actor_user_id == owner.id
    assert event.entity_type == "document"
    assert event.entity_id == document["id"]
    assert event.details["filename"] == "Master.pdf"
    assert event.details["version"] == 1
    assert event.details["size"] == document["file_size"]
    assert "storage_path" not in event.details


def test_download_returns_file_with_safe_headers(
    client, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    content = make_docx("download me")
    document = upload(
        client,
        csrf,
        contract_id,
        name="Final Terms.docx",
        content=content,
        mime=DOCX_MIME,
    ).json()

    response = client.get(f"/api/documents/{document['id']}/download")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith(DOCX_MIME)
    assert response.headers["content-disposition"].startswith("attachment")
    # Non-ASCII-safe RFC 5987 form: the space is percent-encoded.
    assert "Final%20Terms.docx" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_old_versions_remain_downloadable(client, owner_contract, storage_root):
    _, csrf, contract_id = owner_contract
    first_content = make_pdf()
    first = upload(client, csrf, contract_id, content=first_content).json()
    upload(client, csrf, contract_id, content=make_pdf(10))

    response = client.get(f"/api/documents/{first['id']}/download")

    assert response.status_code == 200
    assert response.content == first_content


def test_client_filename_cannot_choose_storage_location(
    client, db_session, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract

    response = upload(
        client, csrf, contract_id, name="../../../etc/evil.pdf"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "evil.pdf"
    row = db_session.get(ContractDocument, body["id"])
    assert row.storage_path == f"contracts/{contract_id}/{body['id']}.pdf"
    files = stored_files(storage_root)
    assert len(files) == 1
    assert files[0].resolve().is_relative_to(storage_root.resolve())


def test_download_refuses_a_stored_path_outside_the_storage_root(
    client, db_session, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    document = upload(client, csrf, contract_id).json()
    outside = storage_root.parent / "outside-secret.txt"
    outside.write_text("secret")

    row = db_session.get(ContractDocument, document["id"])
    row.storage_path = "../outside-secret.txt"
    db_session.commit()

    response = client.get(f"/api/documents/{document['id']}/download")

    assert response.status_code == 404
    assert "secret" not in response.text
    assert "outside" not in response.text


def test_missing_stored_file_returns_safe_404(
    client, db_session, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    document = upload(client, csrf, contract_id).json()
    row = db_session.get(ContractDocument, document["id"])
    (storage_root / row.storage_path).unlink()

    response = client.get(f"/api/documents/{document['id']}/download")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "The stored file for this document is unavailable."
    )
    assert str(storage_root) not in response.text
    assert row.storage_path not in response.text


def test_unknown_or_malformed_document_ids(client, user_factory, storage_root):
    user = user_factory()
    login(client, user.email)

    assert client.get(f"/api/documents/{uuid4()}").status_code == 404
    assert client.get(f"/api/documents/{uuid4()}/download").status_code == 404
    assert client.get("/api/documents/not-a-uuid").status_code == 422


def test_access_control_for_documents(
    client, user_factory, owner_contract, storage_root
):
    _, owner_csrf, contract_id = owner_contract
    document = upload(client, owner_csrf, contract_id).json()
    document_id = document["id"]

    # An unrelated business user can do nothing with this contract's files.
    stranger = user_factory()
    stranger_csrf = login(client, stranger.email)
    assert client.get(f"/api/contracts/{contract_id}/documents").status_code == 403
    assert client.get(f"/api/documents/{document_id}").status_code == 403
    assert client.get(f"/api/documents/{document_id}/download").status_code == 403
    assert upload(client, stranger_csrf, contract_id).status_code == 403

    # A reviewer may read and download, but not upload.
    reviewer = user_factory(role=UserRole.LEGAL_REVIEWER)
    reviewer_csrf = login(client, reviewer.email)
    assert client.get(f"/api/contracts/{contract_id}/documents").status_code == 200
    assert client.get(f"/api/documents/{document_id}").status_code == 200
    assert client.get(f"/api/documents/{document_id}/download").status_code == 200
    assert upload(client, reviewer_csrf, contract_id).status_code == 403

    # An administrator may upload a new version.
    admin = user_factory(role=UserRole.ADMIN)
    admin_csrf = login(client, admin.email)
    admin_upload = upload(client, admin_csrf, contract_id)
    assert admin_upload.status_code == 201
    assert admin_upload.json()["version_number"] == 2

    assert len(stored_files(storage_root)) == 2


def test_rejected_upload_does_not_change_the_version_history(
    client, owner_contract, storage_root
):
    _, csrf, contract_id = owner_contract
    upload(client, csrf, contract_id)
    upload(client, csrf, contract_id, name="bad.pdf", content=b"not a pdf")

    listing = client.get(f"/api/contracts/{contract_id}/documents").json()

    assert listing["total"] == 1
    assert listing["current"]["version_number"] == 1


def test_list_is_empty_for_contract_without_documents(
    client, owner_contract, storage_root
):
    _, _, contract_id = owner_contract

    body = client.get(f"/api/contracts/{contract_id}/documents").json()

    assert body == {"items": [], "total": 0, "current": None}

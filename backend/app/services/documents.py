"""Contract document storage, validation, versioning, and audit events.

Versioning model
----------------
The existing ``contract_documents`` table has a unique ``(contract_id,
version_number)`` pair and a partial unique index allowing one ``is_current``
row per contract. So each contract has one logical document whose versions are
its rows: an upload adds version N+1, marks it current, and keeps every older
row and file. Files are never overwritten.

Storage layout
--------------
``<DOCUMENT_STORAGE_PATH>/contracts/<contract_id>/<document_id>.<ext>``. Every
component is server generated (UUIDs and a fixed extension); a client-supplied
filename is stored only as display metadata and never used as a path.
``storage_path`` in the database is relative to the storage root.
"""

import io
import logging
import re
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.contract_document import ContractDocument
from app.models.user import User
from app.schemas.document import DocumentDetail, DocumentRead
from app.services import contracts as contract_service

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
READ_CHUNK_BYTES = 64 * 1024

PDF_MIME = "application/pdf"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
# A generic type is accepted because some browsers and operating systems do
# not know .docx; the file content is still checked below.
GENERIC_MIME = "application/octet-stream"

ALLOWED_TYPES: dict[str, str] = {".pdf": PDF_MIME, ".docx": DOCX_MIME}

# A .docx is a zip archive. These limits stop a small upload from expanding
# into something huge ("zip bomb") if it is ever unpacked or scanned.
MAX_DOCX_ENTRIES = 5_000
MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

AUDIT_ENTITY_TYPE = "document"


def _unsupported(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail
    )


def safe_display_filename(raw_name: str | None) -> str:
    """Return a harmless display name from a client-supplied filename.

    Directory parts, control characters, and quotes are removed. The result is
    used only for display and the download header, never as a filesystem path.
    """
    name = (raw_name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f\"]", "", name).strip().strip(".")
    return name[:255]


def _extension(display_name: str) -> str:
    return Path(display_name).suffix.lower()


def _is_valid_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


def _is_valid_docx(content: bytes) -> bool:
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                return False
            if sum(e.file_size for e in entries) > MAX_DOCX_UNCOMPRESSED_BYTES:
                return False
            names = {e.filename for e in entries}
    except (zipfile.BadZipFile, ValueError, OSError):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def read_limited(upload: UploadFile) -> bytes:
    """Read the upload, stopping as soon as it exceeds the size limit."""
    buffer = bytearray()
    while chunk := upload.file.read(READ_CHUNK_BYTES):
        buffer.extend(chunk)
        if len(buffer) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="The file is larger than the 10 MB limit.",
            )
    return bytes(buffer)


def validate_upload(
    display_name: str, declared_mime: str | None, content: bytes
) -> tuple[str, str]:
    """Validate extension, declared MIME type, and real content.

    Returns ``(extension, canonical_mime_type)`` or raises an HTTP error.
    """
    if not display_name:
        raise _unsupported("The file must have a name.")

    extension = _extension(display_name)
    expected_mime = ALLOWED_TYPES.get(extension)
    if expected_mime is None:
        raise _unsupported("Only PDF (.pdf) and Word (.docx) files are allowed.")

    declared = (declared_mime or "").split(";")[0].strip().lower()
    if declared and declared not in (expected_mime, GENERIC_MIME):
        raise _unsupported(
            "The file type does not match its extension. "
            "Only PDF and Word (.docx) files are allowed."
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The file is empty.",
        )

    valid = (
        _is_valid_pdf(content)
        if extension == ".pdf"
        else _is_valid_docx(content)
    )
    if not valid:
        raise _unsupported(
            "The file content is not a valid "
            + ("PDF." if extension == ".pdf" else "Word (.docx) document.")
        )

    return extension, expected_mime


def _resolve_inside_root(storage_root: Path, relative_path: str) -> Path:
    """Resolve a stored relative path and refuse anything outside the root."""
    root = storage_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Path escapes the storage root")
    return candidate


def to_read(document: ContractDocument) -> DocumentRead:
    uploader = document.uploaded_by_user
    return DocumentRead(
        id=document.id,
        contract_id=document.contract_id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        version_number=document.version_number,
        is_current=document.is_current,
        uploaded_by=document.uploaded_by,
        uploaded_by_name=uploader.full_name if uploader is not None else None,
        uploaded_at=document.uploaded_at,
    )


def list_versions(db: Session, contract_id: UUID) -> list[ContractDocument]:
    """Return every version of the contract's document, newest first."""
    return list(
        db.execute(
            select(ContractDocument)
            .options(selectinload(ContractDocument.uploaded_by_user))
            .where(ContractDocument.contract_id == contract_id)
            .order_by(ContractDocument.version_number.desc())
        )
        .scalars()
        .all()
    )


def get_document_for_read(
    db: Session, document_id: UUID, user: User
) -> ContractDocument:
    """Load a document the user may read (via its contract), or 404/403."""
    document = db.execute(
        select(ContractDocument)
        .options(selectinload(ContractDocument.uploaded_by_user))
        .where(ContractDocument.id == document_id)
    ).scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Reuses the contract rules: 403 unless the user may view the contract.
    contract_service.get_contract_for_read(db, document.contract_id, user)
    return document


def to_detail(db: Session, document: ContractDocument) -> DocumentDetail:
    versions = list_versions(db, document.contract_id)
    return DocumentDetail(
        **to_read(document).model_dump(),
        latest_version_number=versions[0].version_number,
        versions=[to_read(version) for version in versions],
    )


def create_document_version(
    db: Session,
    *,
    contract: Contract,
    user: User,
    storage_root: Path,
    display_name: str,
    mime_type: str,
    extension: str,
    content: bytes,
) -> ContractDocument:
    """Write the file, add the next version, and record an audit event.

    The contract row is locked so two simultaneous uploads cannot pick the
    same version number. If the database step fails, the new file is removed.
    """
    db.execute(
        select(Contract.id).where(Contract.id == contract.id).with_for_update()
    )

    latest = db.execute(
        select(func.max(ContractDocument.version_number)).where(
            ContractDocument.contract_id == contract.id
        )
    ).scalar_one()
    version_number = (latest or 0) + 1

    document_id = uuid4()
    stored_filename = f"{document_id}{extension}"
    relative_path = f"contracts/{contract.id}/{stored_filename}"
    destination = _resolve_inside_root(storage_root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        # "xb" fails if the file exists, so nothing is ever overwritten.
        with open(destination, "xb") as handle:
            handle.write(content)

        # Clear the current flag first; the partial unique index allows only
        # one current row per contract.
        db.execute(
            update(ContractDocument)
            .where(
                ContractDocument.contract_id == contract.id,
                ContractDocument.is_current.is_(True),
            )
            .values(is_current=False)
        )

        document = ContractDocument(
            id=document_id,
            contract_id=contract.id,
            original_filename=display_name,
            stored_filename=stored_filename,
            storage_path=relative_path,
            mime_type=mime_type,
            file_size=len(content),
            version_number=version_number,
            uploaded_by=user.id,
            is_current=True,
        )
        db.add(document)
        db.flush()

        db.add(
            AuditEvent(
                contract_id=contract.id,
                actor_user_id=user.id,
                action="document.uploaded",
                entity_type=AUDIT_ENTITY_TYPE,
                entity_id=str(document.id),
                details={
                    "contract_number": contract.contract_number,
                    "filename": display_name,
                    "version": version_number,
                    "size": len(content),
                    "mime_type": mime_type,
                },
            )
        )
        db.commit()
    except BaseException:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise

    db.refresh(document)
    return document


def open_stored_file(storage_root: Path, document: ContractDocument) -> Path:
    """Return the path of the stored file, or raise a safe 404.

    Internal paths and filesystem errors are logged, never returned.
    """
    unavailable = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The stored file for this document is unavailable.",
    )

    try:
        path = _resolve_inside_root(storage_root, document.storage_path)
    except ValueError:
        logger.error("Document %s has an unsafe storage path", document.id)
        raise unavailable from None

    if not path.is_file():
        logger.error("Stored file missing for document %s", document.id)
        raise unavailable

    return path

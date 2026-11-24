"""Contract document endpoints (upload, list, metadata, download).

Access follows the contract rules: anyone who may view a contract may list and
download its documents; only someone who may edit the contract (its creator or
an administrator) may upload a new version. Upload requires the CSRF header.
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.document import (
    DocumentDetail,
    DocumentListResponse,
    DocumentRead,
)
from app.services import contracts as contract_service
from app.services import documents as document_service

router = APIRouter(prefix="/api", tags=["documents"])

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
}


def get_storage_root() -> Path:
    """Storage directory dependency (tests override it with a temp folder)."""
    return get_settings().document_storage_root


@router.post(
    "/contracts/{contract_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF or DOCX as the next version of the contract document",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
        413: {"model": ErrorResponse, "description": "File over 10 MB"},
        415: {"model": ErrorResponse, "description": "Unsupported file"},
    },
)
def upload_document(
    contract_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_root: Path = Depends(get_storage_root),
    _: None = Depends(verify_csrf),
) -> DocumentRead:
    # Authorisation and existence are checked before the body is read.
    contract = contract_service.get_contract_for_update(
        db, contract_id, current_user
    )

    display_name = document_service.safe_display_filename(file.filename)
    content = document_service.read_limited(file)
    extension, mime_type = document_service.validate_upload(
        display_name, file.content_type, content
    )

    document = document_service.create_document_version(
        db,
        contract=contract,
        user=current_user,
        storage_root=storage_root,
        display_name=display_name,
        mime_type=mime_type,
        extension=extension,
        content=content,
    )
    return document_service.to_read(document)


@router.get(
    "/contracts/{contract_id}/documents",
    response_model=DocumentListResponse,
    summary="List every version of the contract's document",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
)
def list_documents(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    contract_service.get_contract_for_read(db, contract_id, current_user)
    versions = [
        document_service.to_read(item)
        for item in document_service.list_versions(db, contract_id)
    ]
    return DocumentListResponse(
        items=versions,
        total=len(versions),
        current=next((v for v in versions if v.is_current), None),
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    summary="Document metadata and version history",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Document not found"},
    },
)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    document = document_service.get_document_for_read(
        db, document_id, current_user
    )
    return document_service.to_detail(db, document)


@router.get(
    "/documents/{document_id}/download",
    summary="Download a stored document version",
    response_class=FileResponse,
    responses={
        **AUTH_RESPONSES,
        404: {
            "model": ErrorResponse,
            "description": "Document or stored file not found",
        },
    },
)
def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_root: Path = Depends(get_storage_root),
) -> FileResponse:
    document = document_service.get_document_for_read(
        db, document_id, current_user
    )
    path = document_service.open_stored_file(storage_root, document)

    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.original_filename,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )

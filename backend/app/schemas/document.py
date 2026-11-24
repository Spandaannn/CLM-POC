"""Response schemas for contract documents.

The storage path and stored filename are internal and are deliberately not
part of any response, so server paths are never exposed to clients.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentRead(BaseModel):
    """One stored version of a contract's document."""

    id: UUID
    contract_id: UUID
    original_filename: str
    mime_type: str
    file_size: int = Field(description="Size in bytes.")
    version_number: int
    is_current: bool = Field(
        description="True for the latest version of the contract's document."
    )
    uploaded_by: UUID
    uploaded_by_name: str | None = None
    uploaded_at: datetime


class DocumentDetail(DocumentRead):
    """A version plus the full version history of the same document."""

    latest_version_number: int
    versions: list[DocumentRead] = Field(
        description="Every version, newest first."
    )


class DocumentListResponse(BaseModel):
    """All versions of a contract's document, newest first."""

    items: list[DocumentRead]
    total: int
    current: DocumentRead | None = Field(
        default=None, description="The latest version, if any."
    )

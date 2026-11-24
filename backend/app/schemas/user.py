"""Public user response schema; never includes password or session data."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str = Field(description="Display name.")
    email: str = Field(description="Normalized email address.")
    role: str = Field(description="Application role.")
    is_active: bool = Field(description="Whether the account may authenticate.")
    created_at: datetime

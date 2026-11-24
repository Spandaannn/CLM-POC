"""Authentication request and response schemas."""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserPublic


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    user: UserPublic
    csrf_token: str = Field(
        description="Send this value in the X-CSRF-Token header on logout."
    )


class CsrfTokenResponse(BaseModel):
    csrf_token: str = Field(
        description="Send this value in the X-CSRF-Token header."
    )

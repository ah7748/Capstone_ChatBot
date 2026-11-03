import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    tenant_id: uuid.UUID | None
    lang: str


class TokenPair(BaseModel):
    access_token: str
    expires_in: int
    refresh_token: str
    user: UserOut | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str
    all_sessions: bool = False


class MeOut(UserOut):
    tenant_name: str | None = None
    theme: str = "light"
    permissions: list[str] = []


class InviteAcceptIn(BaseModel):
    invitation_token: str
    password: str = Field(min_length=10)
    name: str | None = Field(default=None, min_length=2, max_length=80)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetConfirmIn(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=10)

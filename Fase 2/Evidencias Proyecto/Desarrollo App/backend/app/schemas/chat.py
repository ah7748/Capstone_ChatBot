from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class PublicUserIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None


class SessionCreateIn(BaseModel):
    lang: Literal["es", "en", "pt"] | None = None
    user: PublicUserIn | None = None
    page_url: str | None = Field(default=None, max_length=500)


class PublicMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class EscalateIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class RatingIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)


class AgentMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    suggestion_id: str | None = None


class ReleaseIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ResolveIn(BaseModel):
    resolution_note: str | None = Field(default=None, max_length=1000)


class TicketPatchIn(BaseModel):
    status: Literal["open", "pending", "resolved"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    assign_to_me: bool | None = None


class PresenceIn(BaseModel):
    presence: Literal["available", "busy", "offline"]

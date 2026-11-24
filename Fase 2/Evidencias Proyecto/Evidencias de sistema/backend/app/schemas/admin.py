import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ChatType = Literal["technical", "commercial"]
DocChatType = Literal["technical", "commercial", "both"]


class ChannelsIn(BaseModel):
    web: bool = True
    whatsapp: bool = False


class TenantCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")
    legal_name: str
    tax_id: str
    country: str = Field(min_length=2, max_length=2)
    language: Literal["es", "en", "pt"]
    admin_email: EmailStr
    deepseek_api_key: str
    channels: ChannelsIn = ChannelsIn()
    token_limit_month: int | None = Field(default=None, gt=0)


class TenantPatchIn(BaseModel):
    name: str | None = None
    slug: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")
    legal_name: str | None = None
    tax_id: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: Literal["es", "en", "pt"] | None = None
    token_limit_month: int | None = Field(default=None, gt=0)
    status: Literal["active", "disabled"] | None = None


class PlatformSettingsIn(BaseModel):
    default_model: Literal["deepseek-chat", "deepseek-reasoner"] | None = None
    escalation_threshold: int | None = Field(default=None, ge=1, le=5)
    default_token_limit_month: int | None = Field(default=None, gt=0)
    alert_pct: int | None = Field(default=None, ge=1, le=100)


class CompanySettingsIn(BaseModel):
    bot_name: str | None = Field(default=None, min_length=2, max_length=60)
    welcome_message: str | None = Field(default=None, max_length=500)
    languages: list[Literal["es", "en", "pt"]] | None = None
    widget_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class DeepseekKeyIn(BaseModel):
    api_key: str = Field(min_length=8)


class BotAgentPatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=60)
    topics: str | None = Field(default=None, max_length=300)
    system_prompt: str | None = Field(default=None, max_length=4000)
    knowledge_scope: Literal["own_type", "own_type_plus_web"] | None = None
    escalation_target: Literal["live_or_ticket", "ticket_only"] | None = None
    enabled: bool | None = None


class BotAgentPreviewIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=10)


class HumanAgentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    escalation_type: Literal["technical", "commercial", "both"]
    channel: Literal["web"]


class HumanAgentPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    email: EmailStr | None = None
    escalation_type: Literal["technical", "commercial", "both"] | None = None
    channel: Literal["web"] | None = None


class ChannelsWebIn(BaseModel):
    published: bool | None = None
    allowed_domains: list[str] | None = Field(default=None, max_length=20)


class EscalationIn(BaseModel):
    when: Literal["after_2_failures_or_request", "on_request_only", "never"] | None = None
    fallback: Literal["create_ticket", "show_hours"] | None = None
    business_hours: dict | None = None
    timezone: str | None = None


class WhatsappConnectIn(BaseModel):
    phone_number_id: str
    waba_id: str
    access_token: str


class WebsiteIn(BaseModel):
    url: str = Field(pattern=r"^https://.+")
    auto_rescan_days: int = Field(default=7, ge=1, le=30)

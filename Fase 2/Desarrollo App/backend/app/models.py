"""Modelos SQLAlchemy 2.0 — esquema multi-tenant del Chatbot de Soporte Genérico."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.types import EmbeddingVector


def now() -> datetime:
    return datetime.now(timezone.utc)


def pk() -> uuid.UUID:
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(2))
    language: Mapped[str] = mapped_column(String(2), default="es")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|active|disabled
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # bot / canales
    bot_name: Mapped[str] = mapped_column(String(60), default="Asistente")
    welcome_message: Mapped[str] = mapped_column(String(500), default="¡Hola! ¿En qué puedo ayudarte?")
    languages: Mapped[list] = mapped_column(JSON, default=lambda: ["es"])
    widget_color: Mapped[str] = mapped_column(String(7), default="#00a79d")
    web_published: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_domains: Mapped[list] = mapped_column(JSON, default=list)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(60))
    whatsapp_waba_id: Mapped[str | None] = mapped_column(String(60))
    whatsapp_phone_masked: Mapped[str | None] = mapped_column(String(30))
    # derivación
    escalation_when: Mapped[str] = mapped_column(String(40), default="after_2_failures_or_request")
    escalation_fallback: Mapped[str] = mapped_column(String(20), default="create_ticket")
    business_hours: Mapped[dict | None] = mapped_column(JSON)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/London")
    # sitio web
    website_url: Mapped[str | None] = mapped_column(String(500))
    auto_rescan_days: Mapped[int] = mapped_column(Integer, default=7)
    # límites / API key
    token_limit_month: Mapped[int | None] = mapped_column(Integer)
    deepseek_key_status: Mapped[str] = mapped_column(String(20), default="missing")  # missing|unvalidated|valid|rejected
    deepseek_key_masked: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # platform_admin|company_admin|human_agent
    lang: Mapped[str] = mapped_column(String(2), default="es")
    theme: Mapped[str] = mapped_column(String(10), default="light")
    status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|active|disabled
    invitation_token: Mapped[str | None] = mapped_column(String(100), index=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reset_token: Mapped[str | None] = mapped_column(String(100), index=True)
    reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # agentes humanos
    escalation_type: Mapped[str | None] = mapped_column(String(10))  # technical|commercial|both
    channel: Mapped[str | None] = mapped_column(String(10))  # web
    presence: Mapped[str] = mapped_column(String(10), default="offline")  # available|busy|offline
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    tenant: Mapped[Tenant | None] = relationship(back_populates="users")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    family: Mapped[str] = mapped_column(String(40), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    rotated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    chat_type: Mapped[str] = mapped_column(String(10))  # technical|commercial|both
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    blob_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(15), default="queued")  # queued|processing|indexed|error
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)
    extracted_content: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "content_hash", name="uq_doc_tenant_hash"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_kind: Mapped[str] = mapped_column(String(10))  # document|faq|web
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    source_name: Mapped[str] = mapped_column(String(300))
    chat_type: Mapped[str] = mapped_column(String(10), index=True)  # technical|commercial|both
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(EmbeddingVector)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Faq(Base):
    __tablename__ = "faqs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(String(10))  # technical|commercial
    source: Mapped[str] = mapped_column(String(12), default="manual")  # manual|import|suggestion
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class FaqSuggestion(Base):
    __tablename__ = "faq_suggestions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    question: Mapped[str] = mapped_column(String(300))
    suggested_answer: Mapped[str] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(String(10))
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    target_document: Mapped[str] = mapped_column(String(200), default="")
    sample_conversations: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|accepted
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FaqImprovement(Base):
    __tablename__ = "faq_improvements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # rewrite|merge|gap
    target_faq_ids: Mapped[list] = mapped_column(JSON, default=list)
    proposal: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|applied
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebsiteScan(Base):
    __tablename__ = "website_scans"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running|done|failed
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    pages_indexed: Mapped[int] = mapped_column(Integer, default=0)
    pages_excluded: Mapped[int] = mapped_column(Integer, default=0)
    new_pages: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BotAgent(Base):
    __tablename__ = "bot_agents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    agent_type: Mapped[str] = mapped_column(String(10))  # technical|commercial
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_name: Mapped[str] = mapped_column(String(60))
    topics: Mapped[str] = mapped_column(String(300), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    knowledge_scope: Mapped[str] = mapped_column(String(30), default="own_type_plus_web")
    escalation_target: Mapped[str] = mapped_column(String(20), default="live_or_ticket")
    __table_args__ = (UniqueConstraint("tenant_id", "agent_type", name="uq_bot_agent"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10), default="web")  # web|whatsapp
    chat_type: Mapped[str] = mapped_column(String(10), default="technical")
    status: Mapped[str] = mapped_column(String(12), default="bot", index=True)
    # bot|queued|live|ticket|resolved|abandoned
    priority: Mapped[str] = mapped_column(String(6), default="medium")  # low|medium|high
    lang: Mapped[str] = mapped_column(String(2), default="es")
    user_name: Mapped[str | None] = mapped_column(String(120))
    user_email: Mapped[str | None] = mapped_column(String(200))
    user_plan: Mapped[str | None] = mapped_column(String(60))
    wa_from: Mapped[str | None] = mapped_column(String(30), index=True)
    page_url: Mapped[str | None] = mapped_column(String(500))
    bot_failures: Mapped[int] = mapped_column(Integer, default=0)
    escalation_reason: Mapped[str | None] = mapped_column(String(300))
    topic: Mapped[str | None] = mapped_column(String(200))
    sentiment: Mapped[str | None] = mapped_column(String(30))
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rating: Mapped[str | None] = mapped_column(String(4))  # up|down
    rating_comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(8))  # user|bot|agent|system
    content: Mapped[str] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(String(80))
    agent_type: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open|pending|resolved
    priority: Mapped[str] = mapped_column(String(6), default="medium")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_ticket_number"),)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    bot_type: Mapped[str] = mapped_column(String(10))
    channel: Mapped[str] = mapped_column(String(10))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_model: Mapped[str] = mapped_column(String(40), default="deepseek-chat")
    escalation_threshold: Mapped[int] = mapped_column(Integer, default=2)
    default_token_limit_month: Mapped[int] = mapped_column(Integer, default=1_000_000)
    alert_pct: Mapped[int] = mapped_column(Integer, default=80)


class RagSuggestion(Base):
    """Sugerencias RAG mostradas al agente humano (para trazar cuáles usa)."""
    __tablename__ = "rag_suggestions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=pk)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_document: Mapped[str] = mapped_column(String(300), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

"""Sección 15 — Chat público del usuario final (session tokens efímeros)."""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_public_session
from app.core.errors import conflict, err, forbidden, not_found
from app.core.security import create_session_token
from app.db.session import get_db
from app.models import Conversation, Message, PlatformSettings, Tenant
from app.schemas.chat import EscalateIn, PublicMessageIn, RatingIn, SessionCreateIn
from app.services import rag
from app.services.deepseek import DeepSeekError
from app.services.escalation import escalate
from app.services.ratelimit import allow
from app.services.realtime import publish_agent_event, publish_session_event
from app.services.usage import quota_exceeded

router = APIRouter(prefix="/public/chat", tags=["public-chat"])

WELCOME = {"es": "¡Hola! 👋 ¿En qué puedo ayudarte?",
           "en": "Hi! 👋 How can I help you?",
           "pt": "Olá! 👋 Como posso ajudar?"}


def _origin_allowed(tenant: Tenant, origin: str | None) -> bool:
    if not origin or not tenant.allowed_domains:
        return True
    host = origin.split("://")[-1].split("/")[0].split(":")[0].lower()
    for d in tenant.allowed_domains:
        if d.startswith("*."):
            if host.endswith(d[1:]) or host == d[2:]:
                return True
        elif host == d:
            return True
    return False


async def _tenant_by_slug(db: AsyncSession, slug: str) -> Tenant:
    t = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if t is None:
        raise not_found("No existe una empresa con ese slug.", "TENANT_NOT_FOUND")
    return t


def _detect_lang(tenant: Tenant, requested: str | None, header: str | None) -> str:
    if requested and requested in tenant.languages:
        return requested
    if header:
        for part in header.split(","):
            code = part.split(";")[0].strip()[:2].lower()
            if code in tenant.languages:
                return code
    return tenant.language if tenant.language in tenant.languages else tenant.languages[0]


@router.get("/{tenant_slug}/config")
async def public_config(tenant_slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    t = await _tenant_by_slug(db, tenant_slug)
    if not _origin_allowed(t, request.headers.get("origin")):
        raise forbidden("ORIGIN_NOT_ALLOWED", "El dominio que embebe el widget no está autorizado.")
    if t.status != "active" or not t.web_published:
        raise forbidden("TENANT_INACTIVE", "El chat no está publicado.")
    return {"tenant_slug": t.slug, "published": True, "bot_name": t.bot_name,
            "widget_color": t.widget_color, "position": "bottom-right",
            "languages": t.languages,
            "welcome_messages": {l: (t.welcome_message if l == t.language else WELCOME.get(l))
                                 for l in t.languages},
            "ws_base_url": settings.API_BASE_URL.replace("http", "ws", 1)}


@router.post("/{tenant_slug}/sessions", status_code=201)
async def create_session(tenant_slug: str, body: SessionCreateIn, request: Request,
                         db: AsyncSession = Depends(get_db)):
    t = await _tenant_by_slug(db, tenant_slug)
    if t.status != "active" or not t.web_published:
        raise forbidden("TENANT_INACTIVE", "La empresa está desactivada o su chat no está publicado.")
    if not _origin_allowed(t, request.headers.get("origin")):
        raise forbidden("ORIGIN_NOT_ALLOWED", "El dominio que embebe el widget no está autorizado.")
    ip = request.client.host if request.client else "?"
    if not await allow(f"session:{ip}", 20, 3600):
        raise err(429, "SESSION_RATE_LIMIT", "Demasiadas sesiones desde la misma IP.")
    lang = _detect_lang(t, body.lang, request.headers.get("accept-language"))
    convo = Conversation(tenant_id=t.id, channel="web", lang=lang,
                         user_name=body.user.name if body.user else None,
                         user_email=body.user.email if body.user else None,
                         page_url=body.page_url)
    db.add(convo)
    await db.flush()
    welcome = t.welcome_message if lang == t.language else WELCOME.get(lang, t.welcome_message)
    db.add(Message(conversation_id=convo.id, role="bot", content=welcome))
    await db.commit()
    return {"session_id": str(convo.id),
            "session_token": create_session_token(convo.id, t.id),
            "config": {"bot_name": t.bot_name, "widget_color": t.widget_color,
                       "welcome_message": welcome, "languages": t.languages},
            "ws_url": f"{settings.API_BASE_URL.replace('http', 'ws', 1)}/ws/chat/{convo.id}"}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: uuid.UUID, body: PublicMessageIn,
                       convo: Conversation = Depends(get_public_session),
                       db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, convo.tenant_id)
    if not await allow(f"msg:{convo.id}", settings.PUBLIC_MSG_PER_MINUTE, 60):
        raise err(429, "MESSAGE_RATE_LIMIT",
                  f"Máximo {settings.PUBLIC_MSG_PER_MINUTE} mensajes por minuto por sesión.")
    user_msg = Message(conversation_id=convo.id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()

    # conversación atendida por humano → entregar al agente, sin respuesta del bot
    if convo.status in ("live", "queued"):
        await db.commit()
        await publish_agent_event(convo.tenant_id, {
            "event": "message.user",
            "data": {"conversation_id": str(convo.id), "content": body.content}})
        return {"message_id": str(user_msg.id), "bot_reply": None, "escalation": None}

    if await quota_exceeded(db, tenant):
        await db.commit()
        raise err(503, "TENANT_QUOTA_EXCEEDED",
                  "La empresa alcanzó su límite de tokens; el bot ofrece dejar un ticket.")

    history = [{"role": "assistant" if m.role == "bot" else "user", "content": m.content}
               for m in (await db.execute(
                   select(Message).where(Message.conversation_id == convo.id,
                                         Message.role.in_(["user", "bot"]))
                   .order_by(Message.created_at))).scalars().all()][:-1]
    escalation = None
    try:
        result = await rag.answer(db, tenant, convo, body.content, history)
        convo.chat_type = result["agent_type"]
        if convo.topic is None:
            convo.topic = body.content[:120]
        bot_msg = Message(conversation_id=convo.id, role="bot", content=result["content"],
                          agent_type=result["agent_type"])
        db.add(bot_msg)
        low_conf = result["sources_used"] == 0
        if low_conf:
            convo.bot_failures += 1
        ps = await db.get(PlatformSettings, 1)
        threshold = ps.escalation_threshold if ps else 2
        if (tenant.escalation_when == "after_2_failures_or_request"
                and convo.bot_failures >= threshold):
            escalation = await escalate(db, tenant, convo, "Bot sin respuesta (intentos agotados)")
        await db.commit()
        await publish_session_event(convo.id, {
            "event": "message.bot",
            "data": {"content": result["content"], "agent_type": result["agent_type"]}})
        return {"message_id": str(user_msg.id),
                "bot_reply": {"message_id": str(bot_msg.id), "content": result["content"],
                              "agent_type": result["agent_type"],
                              "sources_used": result["sources_used"]},
                "escalation": escalation}
    except DeepSeekError as e:
        fallback = {"es": "Disculpa, tengo un problema técnico. ¿Quieres que te contacte una persona?",
                    "en": "Sorry, I'm having a technical issue. Would you like to talk to a person?",
                    "pt": "Desculpe, estou com um problema técnico. Quer falar com uma pessoa?"}[convo.lang]
        db.add(Message(conversation_id=convo.id, role="bot", content=fallback))
        await db.commit()
        if e.code == "DEEPSEEK_UNREACHABLE":
            raise err(502, e.code, e.message)
        raise err(400, e.code, e.message)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: uuid.UUID, after: str | None = Query(None),
                       convo: Conversation = Depends(get_public_session),
                       db: AsyncSession = Depends(get_db)):
    stmt = select(Message).where(Message.conversation_id == convo.id).order_by(Message.created_at)
    msgs = (await db.execute(stmt)).scalars().all()
    if after:
        seen = [i for i, m in enumerate(msgs) if str(m.id) == after]
        msgs = msgs[seen[0] + 1:] if seen else msgs
    return {"messages": [{"message_id": str(m.id), "role": m.role, "content": m.content,
                          "agent_name": m.agent_name, "created_at": m.created_at.isoformat()}
                         for m in msgs]}


@router.post("/sessions/{session_id}/escalate")
async def escalate_session(session_id: uuid.UUID, body: EscalateIn,
                           convo: Conversation = Depends(get_public_session),
                           db: AsyncSession = Depends(get_db)):
    if convo.status in ("queued", "live", "ticket"):
        raise conflict("ALREADY_ESCALATED", "La sesión ya está derivada o atendida.")
    tenant = await db.get(Tenant, convo.tenant_id)
    if tenant.escalation_when == "never" and tenant.escalation_fallback != "create_ticket":
        raise conflict("ESCALATION_DISABLED", "La empresa no tiene habilitada la derivación.")
    result = await escalate(db, tenant, convo, body.reason or "Solicitud explícita del usuario")
    await db.commit()
    await publish_session_event(convo.id, {"event": "escalation.update", "data": result})
    return result


@router.post("/sessions/{session_id}/rating", status_code=201)
async def rate_session(session_id: uuid.UUID, body: RatingIn,
                       convo: Conversation = Depends(get_public_session),
                       db: AsyncSession = Depends(get_db)):
    if convo.rating is not None:
        raise conflict("ALREADY_RATED", "La sesión ya fue valorada.")
    if convo.status not in ("resolved", "abandoned"):
        raise conflict("SESSION_STILL_OPEN", "La conversación sigue activa; valore al cierre.")
    convo.rating = body.rating
    convo.rating_comment = body.comment
    await db.commit()
    return {"saved": True}

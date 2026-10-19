"""Enrutador de derivación: chat en vivo si hay agente humano disponible del tipo, ticket si no."""
import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, Tenant, Ticket, User, now
from app.services.realtime import publish_agent_event


async def _available_agent(db: AsyncSession, tenant_id, chat_type: str) -> User | None:
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.role == "human_agent",
        User.status == "active",
        User.presence == "available",
        User.channel == "web",
        User.escalation_type.in_([chat_type, "both"]),
    )
    return (await db.execute(stmt)).scalars().first()


async def _next_ticket_number(db: AsyncSession, tenant_id) -> int:
    n = (await db.execute(select(func.max(Ticket.number)).where(Ticket.tenant_id == tenant_id))).scalar()
    return (n or 1000) + 1


async def escalate(db: AsyncSession, tenant: Tenant, convo: Conversation, reason: str) -> dict:
    convo.escalation_reason = reason
    convo.escalated_at = now()
    agent = await _available_agent(db, tenant.id, convo.chat_type)
    if agent is not None and convo.channel == "web":
        convo.status = "queued"
        db.add(Message(conversation_id=convo.id, role="system",
                       content=f"El bot derivó la conversación · Motivo: {reason}"))
        await db.flush()
        waiting = (await db.execute(select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == tenant.id, Conversation.status == "queued"))).scalar()
        await publish_agent_event(tenant.id, {"event": "queue.updated",
                                              "data": {"conversation_id": str(convo.id)}})
        return {"mode": "live", "queue_position": int(waiting or 1)}
    # sin agentes (o canal whatsapp en v1) → ticket
    convo.status = "ticket"
    number = await _next_ticket_number(db, tenant.id)
    ticket = Ticket(tenant_id=tenant.id, number=number, conversation_id=convo.id,
                    priority=convo.priority)
    db.add(ticket)
    db.add(Message(conversation_id=convo.id, role="system",
                   content=f"Ticket #T-{number} creado · {reason}"))
    await db.flush()
    await publish_agent_event(tenant.id, {"event": "queue.updated",
                                          "data": {"ticket_number": number}})
    return {"mode": "ticket", "ticket_number": f"T-{number}"}


# --- detección de "quiero hablar con una persona" (es / en / pt) -------------------------------
_HUMAN_WORDS = (r"agente|persona|humano|asesor|ejecutivo|representante|operador|alguien|"
                r"human|person|agent|representative|operator|someone|"
                r"humana|atendente|pessoa|alguem")
_WANT = (r"(quiero|quisiera|necesito|puedo|prefiero|pasame|comunicame|conectame|derivame|transfiereme|"
         r"i want|i need|i would like|can i|let me|connect me|transfer me|"
         r"quero|preciso|gostaria|posso|falar)")
_HUMAN_RE = re.compile(
    rf"\b{_WANT}\b.{{0,40}}\b(hablar|habla|conversar|contactar|comunicar|comunicarme|chatear|talk|speak|chat|"
    rf"contact|falar|conversar|atencion|atendimento|atendido)\b.{{0,40}}\b({_HUMAN_WORDS})\b"
    rf"|\b(hablar|talk to|speak to|speak with|falar com)\b.{{0,15}}\b(con|with|com)?\s*(un|una|an|a|uma|el|la|the)?\s*"
    rf"({_HUMAN_WORDS})\b"
    rf"|\b({_HUMAN_WORDS})\b.{{0,20}}\b(humano|humana|real|de verdad|en vivo|live)\b"
    rf"|\b(agente|asesor|ejecutivo)\s+(humano|real|en vivo)\b"
    rf"|\b(comunic\w*|pas\w*|conect\w*|deriv\w*|transfi\w*|pon\w*)\s+(me\s+)?(con|a)\s+(un|una|el|la)?\s*({_HUMAN_WORDS}|"
    rf"asesora|ejecutiva|supervisor\w*)\b"
    rf"|\bquiero\s+(un|una)\s+({_HUMAN_WORDS})\b"
    rf"|\b(necesito|quiero)\s+(ayuda|atencion)\s+(humana|de una persona|personalizada)\b"
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def wants_human(text: str) -> bool:
    """True si el usuario pide explícitamente hablar con una persona/agente."""
    t = _normalize(text)
    if len(t) > 160:        # un mensaje largo es una consulta, no una petición de derivación
        return False
    return bool(_HUMAN_RE.search(t))

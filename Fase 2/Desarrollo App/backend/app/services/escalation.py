"""Enrutador de derivación: chat en vivo si hay agente humano disponible del tipo, ticket si no."""
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

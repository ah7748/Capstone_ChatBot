"""Sección 17 — Consola de agente humano."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import Page, get_current_user, human_agent, require_role
from app.core.errors import conflict, forbidden, not_found, unprocessable
from app.db.session import get_db
from app.models import Conversation, Message, RagSuggestion, Tenant, Ticket, User, now
from app.schemas.chat import AgentMessageIn, PresenceIn, ReleaseIn, ResolveIn, TicketPatchIn
from app.services import rag
from app.services.realtime import publish_agent_event, publish_session_event
from app.services.whatsapp import MetaApiError, send_text

router = APIRouter(prefix="/agent", tags=["agent-console"])


def _visible_types(agent: User) -> list[str]:
    if agent.escalation_type == "both" or not agent.escalation_type:
        return ["technical", "commercial"]
    return [agent.escalation_type]


async def _convo_visible(db: AsyncSession, agent: User, conversation_id: uuid.UUID) -> Conversation:
    convo = (await db.execute(select(Conversation).options(selectinload(Conversation.messages))
                              .where(Conversation.id == conversation_id))).scalar_one_or_none()
    if convo is None or convo.tenant_id != agent.tenant_id:
        raise not_found("No existe o no es visible para este agente.", "CONVERSATION_NOT_FOUND")
    return convo


@router.get("/queue")
async def queue(type: str = Query(...), page: Page = Depends(),
                agent: User = Depends(human_agent), db: AsyncSession = Depends(get_db)):
    if type not in ("live", "tickets"):
        raise unprocessable("QUEUE_TYPE_INVALID", "type debe ser live o tickets.")
    types = _visible_types(agent)
    live_count = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == agent.tenant_id, Conversation.status.in_(["queued", "live"]),
        Conversation.chat_type.in_(types)))).scalar() or 0
    ticket_count = (await db.execute(select(func.count()).select_from(Ticket)
                                     .join(Conversation, Ticket.conversation_id == Conversation.id)
                                     .where(Ticket.tenant_id == agent.tenant_id,
                                            Ticket.status != "resolved",
                                            Conversation.chat_type.in_(types)))).scalar() or 0
    items = []
    if type == "live":
        stmt = (select(Conversation).where(
            Conversation.tenant_id == agent.tenant_id,
            Conversation.status.in_(["queued", "live"]),
            Conversation.chat_type.in_(types)).order_by(Conversation.escalated_at))
        convos = (await db.execute(stmt.offset(page.offset).limit(page.page_size))).scalars().all()
        for c in convos:
            last = (await db.execute(select(Message).where(Message.conversation_id == c.id)
                                     .order_by(Message.created_at.desc()).limit(1))).scalar_one_or_none()
            claimed = (await db.get(User, c.claimed_by)).name if c.claimed_by else None
            items.append({"conversation_id": str(c.id), "user_name": c.user_name or "Usuario",
                          "channel": c.channel, "chat_type": c.chat_type, "priority": c.priority,
                          "waiting_since": (c.escalated_at or c.created_at).isoformat(),
                          "preview": (last.content[:120] if last else ""),
                          "status": c.status, "assigned_to": claimed})
    else:
        stmt = (select(Ticket, Conversation).join(Conversation, Ticket.conversation_id == Conversation.id)
                .where(Ticket.tenant_id == agent.tenant_id, Ticket.status != "resolved",
                       Conversation.chat_type.in_(types)).order_by(Ticket.created_at))
        for tk, c in (await db.execute(stmt.offset(page.offset).limit(page.page_size))).all():
            assignee = (await db.get(User, tk.assignee_id)).name if tk.assignee_id else None
            items.append({"ticket_id": str(tk.id), "number": f"T-{tk.number}",
                          "conversation_id": str(c.id), "user_name": c.user_name or "Usuario",
                          "channel": c.channel, "chat_type": c.chat_type,
                          "priority": tk.priority, "status": tk.status,
                          "waiting_since": tk.created_at.isoformat(), "assigned_to": assignee,
                          "preview": c.topic or ""})
    return {**page.wrap(items, live_count if type == "live" else ticket_count),
            "counts": {"live": live_count, "tickets": ticket_count}}


@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: uuid.UUID, agent: User = Depends(human_agent),
                              db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    claimed = (await db.get(User, c.claimed_by)).name if c.claimed_by else None
    prev = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == c.tenant_id, Conversation.user_email == c.user_email,
        Conversation.id != c.id))).scalar() or 0 if c.user_email else 0
    return {"conversation": {"conversation_id": str(c.id), "status": c.status,
                             "channel": c.channel, "chat_type": c.chat_type,
                             "priority": c.priority, "created_at": c.created_at.isoformat()},
            "messages": [{"message_id": str(m.id), "role": m.role, "content": m.content,
                          "agent_name": m.agent_name, "created_at": m.created_at.isoformat()}
                         for m in c.messages],
            "context": {"escalation_reason": c.escalation_reason, "topic": c.topic,
                        "sentiment": c.sentiment, "bot_agent_type": c.chat_type},
            "user": {"name": c.user_name, "email": c.user_email, "plan": c.user_plan,
                     "previous_conversations": prev},
            "claimed_by": claimed}


@router.post("/conversations/{conversation_id}/claim")
async def claim(conversation_id: uuid.UUID, agent: User = Depends(human_agent),
                db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    if c.chat_type not in _visible_types(agent):
        raise forbidden("AGENT_TYPE_MISMATCH", "La conversación es de un tipo que este agente no atiende.")
    if c.status in ("resolved", "abandoned"):
        raise conflict("CONVERSATION_CLOSED", "La conversación ya fue resuelta o abandonada.")
    # bloqueo atómico: solo si nadie la reclamó
    result = await db.execute(update(Conversation).where(
        Conversation.id == c.id, Conversation.claimed_by.is_(None)).values(
        claimed_by=agent.id, status="live" if c.status in ("queued", "bot", "live") else c.status))
    if result.rowcount == 0:
        other = (await db.get(User, (await db.get(Conversation, c.id)).claimed_by))
        raise conflict("CONVERSATION_ALREADY_CLAIMED", "Otro agente la tomó primero.",
                       {"agent": other.name if other else None})
    db.add(Message(conversation_id=c.id, role="system",
                   content=f"{agent.name} se unió a la conversación"))
    await db.commit()
    await publish_session_event(c.id, {"event": "agent.joined", "data": {"agent_name": agent.name}})
    await publish_agent_event(agent.tenant_id, {"event": "queue.updated",
                                                "data": {"conversation_id": str(c.id)}})
    return {"claimed": True, "conversation_id": str(c.id)}


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def agent_message(conversation_id: uuid.UUID, body: AgentMessageIn,
                        agent: User = Depends(human_agent), db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    if c.status in ("resolved", "abandoned"):
        raise conflict("CONVERSATION_CLOSED", "La conversación ya se cerró.")
    if c.claimed_by != agent.id:
        raise forbidden("NOT_CLAIM_OWNER", "La conversación está asignada a otro agente.")
    msg = Message(conversation_id=c.id, role="agent", content=body.content,
                  agent_name=agent.name)
    db.add(msg)
    if body.suggestion_id:
        try:
            sugg = await db.get(RagSuggestion, uuid.UUID(body.suggestion_id))
            if sugg and sugg.conversation_id == c.id:
                sugg.used = True
        except ValueError:
            pass
    delivered = True
    if c.channel == "whatsapp" and c.wa_from:
        tenant = await db.get(Tenant, c.tenant_id)
        try:
            await send_text(tenant.id, tenant.whatsapp_phone_number_id, c.wa_from, body.content)
        except MetaApiError:
            delivered = False
    await db.commit()
    await publish_session_event(c.id, {"event": "message.agent",
                                       "data": {"content": body.content, "agent_name": agent.name}})
    return {"message_id": str(msg.id), "delivered": delivered}


@router.get("/conversations/{conversation_id}/suggestions")
async def suggestions(conversation_id: uuid.UUID, agent: User = Depends(human_agent),
                      db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    tenant = await db.get(Tenant, c.tenant_id)
    items = await rag.suggest_replies(db, tenant, c)
    if not items:
        raise conflict("KB_EMPTY", "No hay conocimiento indexado del tipo de esta conversación.")
    out = []
    for s in items:
        row = RagSuggestion(conversation_id=c.id, content=s["content"],
                            source_document=s["source_document"], confidence=s["confidence"])
        db.add(row)
        await db.flush()
        out.append({"suggestion_id": str(row.id), **s})
    await db.commit()
    return {"suggestions": out}


@router.post("/conversations/{conversation_id}/release")
async def release(conversation_id: uuid.UUID, body: ReleaseIn,
                  agent: User = Depends(human_agent), db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    if c.claimed_by != agent.id:
        raise forbidden("NOT_CLAIM_OWNER", "Asignada a otro agente.")
    c.claimed_by = None
    c.status = "bot"
    c.bot_failures = 0
    db.add(Message(conversation_id=c.id, role="system",
                   content=f"{agent.name} devolvió la conversación al bot"
                           + (f" · {body.note}" if body.note else "")))
    await db.commit()
    await publish_session_event(c.id, {"event": "agent.left", "data": {"agent_name": agent.name}})
    return {"released": True}


@router.post("/conversations/{conversation_id}/resolve")
async def resolve(conversation_id: uuid.UUID, body: ResolveIn,
                  agent: User = Depends(human_agent), db: AsyncSession = Depends(get_db)):
    c = await _convo_visible(db, agent, conversation_id)
    if c.status in ("resolved", "abandoned"):
        raise conflict("CONVERSATION_CLOSED", "Ya estaba cerrada.")
    if c.claimed_by is not None and c.claimed_by != agent.id:
        raise forbidden("NOT_CLAIM_OWNER", "Asignada a otro agente.")
    c.status = "resolved"
    c.resolved_at = now()
    ticket = (await db.execute(select(Ticket).where(Ticket.conversation_id == c.id))).scalar_one_or_none()
    if ticket:
        ticket.status = "resolved"
    db.add(Message(conversation_id=c.id, role="system", content="Conversación resuelta"))
    await db.commit()
    await publish_session_event(c.id, {"event": "session.closed", "data": {}})
    return {"resolved": True}


@router.patch("/tickets/{ticket_id}")
async def patch_ticket(ticket_id: uuid.UUID, body: TicketPatchIn,
                       agent: User = Depends(human_agent), db: AsyncSession = Depends(get_db)):
    tk = await db.get(Ticket, ticket_id)
    if tk is None or tk.tenant_id != agent.tenant_id:
        raise not_found("No existe o no es visible.", "TICKET_NOT_FOUND")
    if tk.status == "resolved" and body.status != "open":
        raise conflict("TICKET_CLOSED", "Un ticket resuelto no admite cambios.")
    data = body.model_dump(exclude_unset=True)
    if data.get("assign_to_me"):
        if tk.assignee_id and tk.assignee_id != agent.id:
            other = await db.get(User, tk.assignee_id)
            raise conflict("TICKET_ALREADY_ASSIGNED", "Asignado a otro agente.",
                           {"agent": other.name if other else None})
        tk.assignee_id = agent.id
        convo = await db.get(Conversation, tk.conversation_id)
        convo.claimed_by = agent.id
    if data.get("status"):
        tk.status = data["status"]
        if data["status"] == "resolved":
            convo = await db.get(Conversation, tk.conversation_id)
            convo.status = "resolved"
            convo.resolved_at = now()
    if data.get("priority"):
        tk.priority = data["priority"]
    await db.commit()
    assignee = (await db.get(User, tk.assignee_id)).name if tk.assignee_id else None
    return {"ticket_id": str(tk.id), "number": f"T-{tk.number}", "status": tk.status,
            "priority": tk.priority, "assigned_to": assignee}


@router.patch("/presence")
async def patch_presence(body: PresenceIn, agent: User = Depends(human_agent),
                         db: AsyncSession = Depends(get_db)):
    agent.presence = body.presence
    if body.presence == "offline":
        await db.execute(update(Conversation).where(
            Conversation.claimed_by == agent.id, Conversation.status == "queued")
            .values(claimed_by=None))
    await db.commit()
    return {"presence": agent.presence}

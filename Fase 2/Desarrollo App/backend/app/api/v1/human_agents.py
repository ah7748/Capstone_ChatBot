"""Sección 13 — Agentes humanos (CRUD por empresa)."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Page, company_admin, get_tenant
from app.core.errors import conflict, not_found
from app.core.security import new_opaque_token
from app.db.session import get_db
from app.models import Conversation, Tenant, Ticket, User
from app.schemas.admin import HumanAgentIn, HumanAgentPatchIn

router = APIRouter(prefix="/company/human-agents", tags=["human-agents"],
                   dependencies=[Depends(company_admin)])


async def _agent_out(db: AsyncSession, u: User) -> dict:
    live = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.claimed_by == u.id, Conversation.status == "live"))).scalar() or 0
    tickets = (await db.execute(select(func.count()).select_from(Ticket).where(
        Ticket.assignee_id == u.id, Ticket.status != "resolved"))).scalar() or 0
    return {"agent_id": str(u.id), "name": u.name, "email": u.email,
            "escalation_type": u.escalation_type, "channel": u.channel,
            "presence": u.presence, "live_count": live, "open_tickets": tickets,
            "status": "active" if u.status == "active" else "invited"}


async def _agent_or_404(db: AsyncSession, tenant: Tenant, agent_id: uuid.UUID) -> User:
    u = await db.get(User, agent_id)
    if u is None or u.tenant_id != tenant.id or u.role != "human_agent":
        raise not_found("No existe en este tenant.", "HUMAN_AGENT_NOT_FOUND")
    return u


@router.get("")
async def list_human_agents(page: Page = Depends(), tenant: Tenant = Depends(get_tenant),
                            db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.tenant_id == tenant.id, User.role == "human_agent",
                              User.status != "disabled")
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    users = (await db.execute(stmt.order_by(User.name).offset(page.offset).limit(page.page_size))).scalars().all()
    return page.wrap([await _agent_out(db, u) for u in users], total)


@router.post("", status_code=201)
async def create_human_agent(body: HumanAgentIn, tenant: Tenant = Depends(get_tenant),
                             db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none():
        raise conflict("HUMAN_AGENT_EMAIL_EXISTS", "Ya existe una cuenta con ese email.")
    u = User(tenant_id=tenant.id, name=body.name, email=body.email.lower(), role="human_agent",
             lang=tenant.language, escalation_type=body.escalation_type, channel=body.channel,
             invitation_token=new_opaque_token(),
             invitation_expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db.add(u)
    await db.commit()
    return {"agent_id": str(u.id), "status": "invited"}


@router.patch("/{agent_id}")
async def patch_human_agent(agent_id: uuid.UUID, body: HumanAgentPatchIn,
                            tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    u = await _agent_or_404(db, tenant, agent_id)
    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"].lower() != u.email:
        if (await db.execute(select(User).where(User.email == data["email"].lower()))).scalar_one_or_none():
            raise conflict("HUMAN_AGENT_EMAIL_EXISTS", "El nuevo email ya está en uso.")
        u.email = data.pop("email").lower()
        u.status = "invited"
        u.invitation_token = new_opaque_token()
        u.invitation_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    for k, v in data.items():
        setattr(u, k, v)
    await db.commit()
    return await _agent_out(db, u)


@router.delete("/{agent_id}")
async def delete_human_agent(agent_id: uuid.UUID, confirm: bool = Query(False),
                             tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    u = await _agent_or_404(db, tenant, agent_id)
    # ¿último agente de su tipo?
    if u.escalation_type:
        types = ["both"] + ([u.escalation_type] if u.escalation_type != "both"
                            else ["technical", "commercial"])
        others = (await db.execute(select(func.count()).select_from(User).where(
            User.tenant_id == tenant.id, User.role == "human_agent",
            User.status != "disabled", User.id != u.id,
            User.escalation_type.in_(types)))).scalar() or 0
        if not others and not confirm:
            raise conflict("LAST_AGENT_OF_TYPE",
                           "Es el último agente de un tipo con derivación activa; "
                           "las derivaciones futuras irán solo a ticket. Repita con ?confirm=true.")
    # reasignar carga
    candidates = (await db.execute(select(User).where(
        User.tenant_id == tenant.id, User.role == "human_agent", User.status == "active",
        User.id != u.id))).scalars().all()
    fallback = candidates[0] if candidates else None
    live_stmt = update(Conversation).where(Conversation.claimed_by == u.id,
                                           Conversation.status == "live")
    tick_stmt = update(Ticket).where(Ticket.assignee_id == u.id, Ticket.status != "resolved")
    reassigned_live = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.claimed_by == u.id, Conversation.status == "live"))).scalar() or 0
    open_tickets = (await db.execute(select(func.count()).select_from(Ticket).where(
        Ticket.assignee_id == u.id, Ticket.status != "resolved"))).scalar() or 0
    if fallback:
        await db.execute(live_stmt.values(claimed_by=fallback.id))
        await db.execute(tick_stmt.values(assignee_id=fallback.id))
        unassigned = 0
    else:
        await db.execute(live_stmt.values(claimed_by=None, status="queued"))
        await db.execute(tick_stmt.values(assignee_id=None))
        unassigned = open_tickets
    u.status = "disabled"
    u.presence = "offline"
    await db.commit()
    return {"deleted": True,
            "reassigned": {"live": reassigned_live if fallback else 0,
                           "tickets": open_tickets if fallback else 0},
            "unassigned": {"tickets": unassigned}}

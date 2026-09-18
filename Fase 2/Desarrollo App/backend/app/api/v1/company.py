"""Sección 8 — Empresa: dashboard y configuración."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import Page, company_admin, get_tenant, validate_period
from app.core.errors import err, unprocessable
from app.db.session import get_db
from app.models import Conversation, Tenant, Ticket, User
from app.schemas.admin import CompanySettingsIn, DeepseekKeyIn
from app.services.deepseek import DeepSeekError, as_api_error, validate_key
from app.services.secrets import SecretStore, mask_key, secret_store
from app.services.usage import month_usage, period_range

router = APIRouter(prefix="/company", tags=["company"], dependencies=[Depends(company_admin)])

METRICS = {"conversations", "resolved", "pending_tickets", "escalations"}


@router.get("/dashboard")
async def dashboard(period: str = Query("7d"), tenant: Tenant = Depends(get_tenant),
                    db: AsyncSession = Depends(get_db)):
    validate_period(period)
    start, _ = period_range(period)
    conv = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == tenant.id, Conversation.created_at >= start))).scalar() or 0
    resolved_bot = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == tenant.id, Conversation.created_at >= start,
        Conversation.status == "resolved", Conversation.escalated_at.is_(None)))).scalar() or 0
    esc = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == tenant.id, Conversation.created_at >= start,
        Conversation.escalated_at.is_not(None)))).scalar() or 0
    pending = (await db.execute(select(func.count()).select_from(Ticket).where(
        Ticket.tenant_id == tenant.id, Ticket.status != "resolved"))).scalar() or 0
    unassigned = (await db.execute(select(func.count()).select_from(Ticket).where(
        Ticket.tenant_id == tenant.id, Ticket.status != "resolved",
        Ticket.assignee_id.is_(None)))).scalar() or 0
    tokens = await month_usage(db, tenant.id)
    limit = tenant.token_limit_month or settings.DEFAULT_TOKEN_LIMIT_MONTH
    # temas más frecuentes
    topic_rows = (await db.execute(
        select(Conversation.topic, func.count())
        .where(Conversation.tenant_id == tenant.id, Conversation.created_at >= start,
               Conversation.topic.is_not(None))
        .group_by(Conversation.topic).order_by(func.count().desc()).limit(5))).all()
    return {
        "kpis": {"conversations": conv,
                 "bot_resolved_pct": round(resolved_bot * 100 / conv) if conv else 0,
                 "pending_tickets": pending, "pending_unassigned": unassigned,
                 "escalations": esc, "tokens": tokens,
                 "token_limit_pct": round(tokens * 100 / limit) if limit else 0},
        "top_topics": [{"topic": t, "count": c} for t, c in topic_rows],
        "period": period,
    }


@router.get("/dashboard/detail")
async def dashboard_detail(metric: str, period: str = Query("7d"), page: Page = Depends(),
                           tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    if metric not in METRICS:
        raise unprocessable("METRIC_INVALID", "La métrica no es una de las cuatro admitidas.",
                            {"allowed": sorted(METRICS)})
    validate_period(period)
    start, _ = period_range(period)

    if metric == "pending_tickets":
        stmt = (select(Ticket, Conversation).join(Conversation, Ticket.conversation_id == Conversation.id)
                .where(Ticket.tenant_id == tenant.id, Ticket.status != "resolved")
                .order_by(Ticket.created_at))
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
        rows = (await db.execute(stmt.offset(page.offset).limit(page.page_size))).all()
        items = []
        for tk, c in rows:
            assignee = (await db.get(User, tk.assignee_id)).name if tk.assignee_id else None
            items.append({"ticket_id": str(tk.id), "number": f"T-{tk.number}",
                          "user_name": c.user_name, "topic": c.topic, "chat_type": c.chat_type,
                          "channel": c.channel, "assigned_to": assignee,
                          "waiting_since": tk.created_at.isoformat(),
                          "conversation_id": str(c.id)})
        return page.wrap(items, total)

    stmt = select(Conversation).where(Conversation.tenant_id == tenant.id,
                                      Conversation.created_at >= start)
    if metric == "resolved":
        stmt = stmt.where(Conversation.status == "resolved", Conversation.escalated_at.is_(None))
    elif metric == "escalations":
        stmt = stmt.where(Conversation.escalated_at.is_not(None))
    stmt = stmt.order_by(Conversation.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    convos = (await db.execute(stmt.offset(page.offset).limit(page.page_size))).scalars().all()
    items = []
    for c in convos:
        agent_name = (await db.get(User, c.claimed_by)).name if c.claimed_by else None
        items.append({"conversation_id": str(c.id), "user_name": c.user_name,
                      "channel": c.channel, "chat_type": c.chat_type,
                      "created_at": c.created_at.isoformat(), "status": c.status,
                      "topic": c.topic, "rating": c.rating,
                      "escalation_reason": c.escalation_reason, "human_agent": agent_name})
    return page.wrap(items, total)


@router.get("/settings")
async def get_settings_ep(tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    used = await month_usage(db, tenant.id)
    limit = tenant.token_limit_month or settings.DEFAULT_TOKEN_LIMIT_MONTH
    return {"bot_name": tenant.bot_name, "welcome_message": tenant.welcome_message,
            "languages": tenant.languages, "widget_color": tenant.widget_color,
            "deepseek_key_masked": tenant.deepseek_key_masked,
            "deepseek_key_status": tenant.deepseek_key_status,
            "token_usage": {"used": used, "limit": limit,
                            "pct": round(used * 100 / limit) if limit else 0}}


@router.patch("/settings")
async def patch_settings(body: CompanySettingsIn, tenant: Tenant = Depends(get_tenant),
                         db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "languages" in data and not data["languages"]:
        raise unprocessable("LANGUAGES_EMPTY", "Debe haber al menos un idioma habilitado.")
    for k, v in data.items():
        setattr(tenant, k, v)
    await db.commit()
    return await get_settings_ep(tenant, db)


@router.put("/settings/deepseek-key")
async def put_deepseek_key(body: DeepseekKeyIn, tenant: Tenant = Depends(get_tenant),
                           db: AsyncSession = Depends(get_db)):
    if not body.api_key.startswith("sk-"):
        raise unprocessable("DEEPSEEK_KEY_INVALID_FORMAT", "La clave no tiene el formato esperado.")
    secret_store.set(SecretStore.deepseek_key_name(tenant.id), body.api_key)
    tenant.deepseek_key_masked = mask_key(body.api_key)
    tenant.deepseek_key_status = "unvalidated"
    await db.commit()
    return {"deepseek_key_masked": tenant.deepseek_key_masked, "status": "unvalidated"}


@router.post("/settings/deepseek-key/validate")
async def validate_deepseek_key(tenant: Tenant = Depends(get_tenant),
                                db: AsyncSession = Depends(get_db)):
    key = secret_store.get(SecretStore.deepseek_key_name(tenant.id))
    try:
        result = await validate_key(key or "")
    except DeepSeekError as e:
        tenant.deepseek_key_status = "rejected" if e.code == "DEEPSEEK_KEY_REJECTED" else tenant.deepseek_key_status
        await db.commit()
        raise as_api_error(e)
    tenant.deepseek_key_status = "valid"
    await db.commit()
    return {"valid": True, "model": result["model"]}

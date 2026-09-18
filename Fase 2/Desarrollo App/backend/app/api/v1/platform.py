"""Sección 7 — Administración de plataforma."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Page, platform_admin, validate_period
from app.core.errors import conflict, not_found, unprocessable
from app.core.security import new_opaque_token
from app.db.session import get_db
from app.models import (
    BotAgent, Conversation, Document, Faq, PlatformSettings, Tenant, Ticket, User, UsageEvent, now,
)
from app.schemas.admin import PlatformSettingsIn, TenantCreateIn, TenantPatchIn
from app.services.secrets import SecretStore, mask_key, secret_store
from app.services.usage import period_range, usage_breakdown

router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(platform_admin)])


async def _tenant_or_404(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise not_found("La empresa no existe.", "TENANT_NOT_FOUND")
    return tenant


def _kb_summary(docs: int, faqs: int, website_ok: bool) -> dict:
    return {"documents": docs, "faqs": faqs, "website_ok": website_ok}


@router.get("/dashboard")
async def dashboard(period: str = Query("7d"), db: AsyncSession = Depends(get_db)):
    validate_period(period)
    start, end = period_range(period)
    tenants = (await db.execute(select(Tenant).where(Tenant.status != "disabled"))).scalars().all()
    rows, tot_conv, tot_res, tot_esc, tot_tok = [], 0, 0, 0, 0
    for t in tenants:
        conv = (await db.execute(select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == t.id, Conversation.created_at >= start))).scalar() or 0
        esc = (await db.execute(select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == t.id, Conversation.created_at >= start,
            Conversation.escalated_at.is_not(None)))).scalar() or 0
        res = (await db.execute(select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == t.id, Conversation.created_at >= start,
            Conversation.status == "resolved", Conversation.escalated_at.is_(None)))).scalar() or 0
        tok = (await db.execute(select(func.sum(UsageEvent.tokens)).where(
            UsageEvent.tenant_id == t.id, UsageEvent.created_at >= start))).scalar() or 0
        channels = ["web"] + (["whatsapp"] if t.whatsapp_phone_number_id else [])
        rows.append({"tenant_id": str(t.id), "name": t.name, "channels": channels,
                     "conversations": conv,
                     "bot_resolved_pct": round(res * 100 / conv) if conv else 0,
                     "escalations": esc, "tokens": int(tok), "status": t.status})
        tot_conv += conv; tot_res += res; tot_esc += esc; tot_tok += int(tok)
    return {"kpis": {"conversations": tot_conv,
                     "bot_resolved_pct": round(tot_res * 100 / tot_conv) if tot_conv else 0,
                     "escalations": tot_esc, "tokens": tot_tok},
            "tenants": rows, "period": period}


@router.get("/tenants")
async def list_tenants(search: str | None = None, status: str | None = None,
                       page: Page = Depends(), db: AsyncSession = Depends(get_db)):
    stmt = select(Tenant)
    if search:
        stmt = stmt.where(func.lower(Tenant.name).contains(search.lower()) |
                          func.lower(Tenant.slug).contains(search.lower()))
    if status:
        stmt = stmt.where(Tenant.status == status)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    tenants = (await db.execute(stmt.order_by(Tenant.name).offset(page.offset).limit(page.page_size))).scalars().all()
    items = []
    for t in tenants:
        docs = (await db.execute(select(func.count()).select_from(Document).where(Document.tenant_id == t.id))).scalar() or 0
        faqs = (await db.execute(select(func.count()).select_from(Faq).where(Faq.tenant_id == t.id))).scalar() or 0
        items.append({
            "tenant_id": str(t.id), "name": t.name, "slug": t.slug, "status": t.status,
            "deepseek_key_status": t.deepseek_key_status,
            "kb_summary": _kb_summary(docs, faqs, bool(t.website_url)),
            "chat_url": f"soporte.allox.ai/{t.slug}",
            "whatsapp_status": "connected" if t.whatsapp_phone_number_id else "not_configured",
        })
    return page.wrap(items, total)


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreateIn, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Tenant).where(Tenant.slug == body.slug))).scalar_one_or_none():
        raise conflict("TENANT_SLUG_TAKEN", "El slug ya está en uso por otra empresa.")
    if (await db.execute(select(User).where(User.email == body.admin_email.lower()))).scalar_one_or_none():
        raise conflict("TENANT_EMAIL_EXISTS", "El email de administrador ya pertenece a otra cuenta.")
    if not body.deepseek_api_key.startswith("sk-"):
        raise unprocessable("DEEPSEEK_KEY_INVALID_FORMAT", "La API key no tiene el formato esperado (sk-...).")

    tenant = Tenant(name=body.name, slug=body.slug, legal_name=body.legal_name,
                    tax_id=body.tax_id, country=body.country.upper(), language=body.language,
                    languages=[body.language], token_limit_month=body.token_limit_month,
                    status="active", bot_name=f"Asistente {body.name}",
                    deepseek_key_status="unvalidated",
                    deepseek_key_masked=mask_key(body.deepseek_api_key))
    db.add(tenant)
    await db.flush()
    secret_store.set(SecretStore.deepseek_key_name(tenant.id), body.deepseek_api_key)
    # agentes del bot por defecto
    db.add(BotAgent(tenant_id=tenant.id, agent_type="technical", enabled=True,
                    display_name=f"Asistente {body.name} · Soporte técnico",
                    system_prompt=f"Eres el agente de soporte técnico de {body.name}. "
                                  "Responde solo con base en la documentación."))
    db.add(BotAgent(tenant_id=tenant.id, agent_type="commercial", enabled=False,
                    display_name=f"Asistente {body.name} · Ventas y planes",
                    system_prompt=f"Eres el agente comercial de {body.name}."))
    # invitación del admin de empresa
    admin = User(tenant_id=tenant.id, name=body.admin_email.split("@")[0],
                 email=body.admin_email.lower(), role="company_admin", lang=body.language,
                 invitation_token=new_opaque_token(),
                 invitation_expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db.add(admin)
    await db.commit()
    return {"tenant_id": str(tenant.id), "chat_url": f"soporte.allox.ai/{tenant.slug}",
            "invitation_sent": True}


@router.get("/tenants/{tenant_id}")
async def tenant_detail(tenant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    t = await _tenant_or_404(db, tenant_id)
    agents = (await db.execute(select(BotAgent).where(BotAgent.tenant_id == t.id))).scalars().all()
    by_type = {a.agent_type: a.enabled for a in agents}
    channels = [{"channel": "web", "technical": "enabled" if by_type.get("technical") else "disabled",
                 "commercial": "enabled" if by_type.get("commercial") else "disabled"}]
    if t.whatsapp_phone_number_id:
        channels.append({"channel": "whatsapp",
                         "technical": "enabled" if by_type.get("technical") else "disabled",
                         "commercial": "enabled" if by_type.get("commercial") else "disabled"})
    docs = (await db.execute(select(func.count()).select_from(Document).where(Document.tenant_id == t.id))).scalar() or 0
    faqs = (await db.execute(select(func.count()).select_from(Faq).where(Faq.tenant_id == t.id))).scalar() or 0
    return {"tenant": {"tenant_id": str(t.id), "name": t.name, "slug": t.slug,
                       "legal_name": t.legal_name, "tax_id": t.tax_id, "country": t.country,
                       "language": t.language, "deepseek_key_status": t.deepseek_key_status,
                       "deepseek_key_masked": t.deepseek_key_masked},
            "bots_by_channel": channels,
            "kb_summary": _kb_summary(docs, faqs, bool(t.website_url)),
            "status": t.status}


@router.patch("/tenants/{tenant_id}")
async def patch_tenant(tenant_id: uuid.UUID, body: TenantPatchIn, db: AsyncSession = Depends(get_db)):
    t = await _tenant_or_404(db, tenant_id)
    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"] != t.slug:
        if (await db.execute(select(Tenant).where(Tenant.slug == data["slug"]))).scalar_one_or_none():
            raise conflict("TENANT_SLUG_TAKEN", "Slug en uso.")
    for k, v in data.items():
        setattr(t, k, v.upper() if k == "country" else v)
    await db.commit()
    return await tenant_detail(tenant_id, db)


@router.delete("/tenants/{tenant_id}", status_code=202)
async def disable_tenant(tenant_id: uuid.UUID, force: bool = Query(False),
                         db: AsyncSession = Depends(get_db)):
    t = await _tenant_or_404(db, tenant_id)
    live = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == t.id, Conversation.status.in_(["queued", "live"])))).scalar() or 0
    if live and not force:
        raise conflict("TENANT_HAS_LIVE_CONVERSATIONS",
                       "Hay conversaciones en vivo; repita con ?force=true para cerrarlas.",
                       {"live": live})
    t.status = "disabled"
    t.purge_at = datetime.now(timezone.utc) + timedelta(days=90)
    await db.commit()
    return {"status": "disabled", "purge_at": t.purge_at.isoformat()}


@router.get("/tenants/{tenant_id}/usage")
async def tenant_usage(tenant_id: uuid.UUID, period: str = Query("7d"),
                       db: AsyncSession = Depends(get_db)):
    validate_period(period)
    t = await _tenant_or_404(db, tenant_id)
    return await usage_breakdown(db, t, period)


@router.get("/human-agents")
async def all_human_agents(tenant_id: uuid.UUID | None = None, page: Page = Depends(),
                           db: AsyncSession = Depends(get_db)):
    stmt = select(User, Tenant.name).join(Tenant, User.tenant_id == Tenant.id).where(
        User.role == "human_agent")
    if tenant_id:
        stmt = stmt.where(User.tenant_id == tenant_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.order_by(Tenant.name).offset(page.offset).limit(page.page_size))).all()
    items = []
    for u, tenant_name in rows:
        live = (await db.execute(select(func.count()).select_from(Conversation).where(
            Conversation.claimed_by == u.id, Conversation.status == "live"))).scalar() or 0
        tickets = (await db.execute(select(func.count()).select_from(Ticket).where(
            Ticket.assignee_id == u.id, Ticket.status != "resolved"))).scalar() or 0
        items.append({"agent_id": str(u.id), "name": u.name, "email": u.email,
                      "tenant_name": tenant_name, "escalation_type": u.escalation_type,
                      "channel": u.channel, "presence": u.presence,
                      "live_count": live, "open_tickets": tickets})
    return page.wrap(items, total)


async def _settings_row(db: AsyncSession) -> PlatformSettings:
    ps = await db.get(PlatformSettings, 1)
    if ps is None:
        ps = PlatformSettings(id=1)
        db.add(ps)
        await db.flush()
    return ps


@router.get("/settings")
async def get_platform_settings(db: AsyncSession = Depends(get_db)):
    ps = await _settings_row(db)
    await db.commit()
    return {"default_model": ps.default_model, "escalation_threshold": ps.escalation_threshold,
            "default_token_limit_month": ps.default_token_limit_month, "alert_pct": ps.alert_pct}


@router.patch("/settings")
async def patch_platform_settings(body: PlatformSettingsIn, db: AsyncSession = Depends(get_db)):
    ps = await _settings_row(db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ps, k, v)
    await db.commit()
    return {"default_model": ps.default_model, "escalation_threshold": ps.escalation_threshold,
            "default_token_limit_month": ps.default_token_limit_month, "alert_pct": ps.alert_pct}

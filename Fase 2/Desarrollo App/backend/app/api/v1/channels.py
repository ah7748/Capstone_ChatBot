"""Sección 14 — Canales del chat (web, WhatsApp, reglas de derivación)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import company_admin, get_tenant
from app.core.errors import conflict, err, not_found, unprocessable
from app.db.session import get_db
from app.models import Tenant
from app.schemas.admin import ChannelsWebIn, EscalationIn, WhatsappConnectIn
from app.services.secrets import SecretStore, secret_store
from app.services.whatsapp import MetaApiError, verify_connection

router = APIRouter(prefix="/company/channels", tags=["channels"],
                   dependencies=[Depends(company_admin)])

DOMAIN_RE = r"^(\*\.)?([a-z0-9-]+\.)+[a-z]{2,}$"


def _channels_out(t: Tenant) -> dict:
    snippet = (f'<script src="{settings.PUBLIC_CHAT_BASE_URL}/widget.js" '
               f'data-tenant="{t.slug}" async></script>')
    return {
        "web": {"chat_url": f"{settings.PUBLIC_CHAT_BASE_URL}/{t.slug}",
                "widget_snippet": snippet, "published": t.web_published,
                "allowed_domains": t.allowed_domains},
        "whatsapp": {"connected": bool(t.whatsapp_phone_number_id),
                     "phone_masked": t.whatsapp_phone_masked},
        "escalation": {"when": t.escalation_when, "fallback": t.escalation_fallback,
                       "business_hours": t.business_hours, "timezone": t.timezone},
    }


@router.get("")
async def get_channels(tenant: Tenant = Depends(get_tenant)):
    return _channels_out(tenant)


@router.patch("/web")
async def patch_web(body: ChannelsWebIn, tenant: Tenant = Depends(get_tenant),
                    db: AsyncSession = Depends(get_db)):
    import re
    data = body.model_dump(exclude_unset=True)
    if "allowed_domains" in data:
        for d in data["allowed_domains"]:
            if not re.match(DOMAIN_RE, d.lower()):
                raise unprocessable("DOMAIN_INVALID", "Algún dominio no es válido.", {"domain": d})
        tenant.allowed_domains = [d.lower() for d in data["allowed_domains"]]
    if "published" in data and data["published"] is not None:
        tenant.web_published = data["published"]
    await db.commit()
    return _channels_out(tenant)["web"]


@router.patch("/escalation")
async def patch_escalation(body: EscalationIn, tenant: Tenant = Depends(get_tenant),
                           db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "business_hours" in data and data["business_hours"] is not None:
        bh = data["business_hours"]
        if not isinstance(bh, dict) or not {"from", "to"}.issubset(bh):
            raise unprocessable("HOURS_INVALID", "El rango horario es inválido.")
    mapping = {"when": "escalation_when", "fallback": "escalation_fallback",
               "business_hours": "business_hours", "timezone": "timezone"}
    for k, v in data.items():
        setattr(tenant, mapping[k], v)
    await db.commit()
    return _channels_out(tenant)["escalation"]


@router.post("/whatsapp", status_code=201)
async def connect_whatsapp(body: WhatsappConnectIn, tenant: Tenant = Depends(get_tenant),
                           db: AsyncSession = Depends(get_db)):
    if tenant.whatsapp_phone_number_id:
        raise conflict("WHATSAPP_ALREADY_CONNECTED", "Ya hay un número conectado; desconecte primero.")
    try:
        info = await verify_connection(body.phone_number_id, body.access_token)
    except MetaApiError as e:
        raise err(502, "META_API_ERROR", "Meta rechazó las credenciales o el webhook.",
                  {"meta": e.detail})
    secret_store.set(SecretStore.whatsapp_token_name(tenant.id), body.access_token)
    tenant.whatsapp_phone_number_id = body.phone_number_id
    tenant.whatsapp_waba_id = body.waba_id
    phone = info.get("display_phone_number", "")
    tenant.whatsapp_phone_masked = f"•••{phone[-4:]}" if phone else "conectado"
    await db.commit()
    return {"connected": True, "phone_masked": tenant.whatsapp_phone_masked}


@router.delete("/whatsapp", status_code=204)
async def disconnect_whatsapp(tenant: Tenant = Depends(get_tenant),
                              db: AsyncSession = Depends(get_db)):
    if not tenant.whatsapp_phone_number_id:
        raise not_found("No hay número conectado.", "WHATSAPP_NOT_CONNECTED")
    tenant.whatsapp_phone_number_id = None
    tenant.whatsapp_waba_id = None
    tenant.whatsapp_phone_masked = None
    await db.commit()

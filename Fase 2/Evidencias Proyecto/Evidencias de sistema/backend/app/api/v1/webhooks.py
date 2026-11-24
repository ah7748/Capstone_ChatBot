"""Sección 18 — Webhooks de WhatsApp (Meta Cloud API)."""
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import forbidden, unauthorized
from app.db.session import get_db
from app.models import Conversation, Message, Tenant
from app.services import rag
from app.services.deepseek import DeepSeekError
from app.services.escalation import escalate
from app.services.usage import quota_exceeded
from app.services.whatsapp import MetaApiError, send_text, valid_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
async def verify(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") != settings.WHATSAPP_VERIFY_TOKEN:
        raise forbidden("WEBHOOK_VERIFY_FAILED", "El verify_token no coincide.")
    return Response(content=params.get("hub.challenge", ""), media_type="text/plain")


@router.post("/whatsapp")
async def receive(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    if not valid_signature(body, request.headers.get("x-hub-signature-256")):
        raise unauthorized("SIGNATURE_INVALID", "La firma no valida contra el app secret.")
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_id = value.get("metadata", {}).get("phone_number_id")
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                await _handle_incoming(db, phone_id, msg["from"], msg["text"]["body"])
    return {"received": True}


async def _handle_incoming(db: AsyncSession, phone_id: str, wa_from: str, text: str) -> None:
    tenant = (await db.execute(select(Tenant).where(
        Tenant.whatsapp_phone_number_id == phone_id))).scalar_one_or_none()
    if tenant is None:
        return  # PHONE_NOT_MAPPED: se registra y descarta
    convo = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == tenant.id, Conversation.wa_from == wa_from,
        Conversation.status.in_(["bot", "queued", "live", "ticket"]))
        .order_by(Conversation.created_at.desc()).limit(1))).scalar_one_or_none()
    if convo is None:
        convo = Conversation(tenant_id=tenant.id, channel="whatsapp", wa_from=wa_from,
                             lang=tenant.language, user_name=wa_from)
        db.add(convo)
        await db.flush()
    db.add(Message(conversation_id=convo.id, role="user", content=text))
    await db.flush()
    if convo.status in ("queued", "live", "ticket"):
        await db.commit()
        return  # lo atiende un humano vía consola
    if await quota_exceeded(db, tenant):
        await db.commit()
        return
    try:
        result = await rag.answer(db, tenant, convo, text)
        convo.chat_type = result["agent_type"]
        db.add(Message(conversation_id=convo.id, role="bot", content=result["content"],
                       agent_type=result["agent_type"]))
        if result["sources_used"] == 0:
            convo.bot_failures += 1
            if convo.bot_failures >= 2 and tenant.escalation_when != "never":
                await escalate(db, tenant, convo, "Bot sin respuesta (WhatsApp)")
        await db.commit()
        try:
            await send_text(tenant.id, phone_id, wa_from, result["content"])
        except MetaApiError:
            pass
    except DeepSeekError:
        await db.commit()

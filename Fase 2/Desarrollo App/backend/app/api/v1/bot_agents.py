"""Sección 12 — Agentes del bot (técnico y comercial)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import company_admin, get_tenant
from app.core.errors import conflict, unprocessable
from app.db.session import get_db
from app.models import BotAgent, Chunk, Conversation, Tenant, UsageEvent
from app.schemas.admin import BotAgentPatchIn, BotAgentPreviewIn
from app.services import rag, vectorstore
from app.services.deepseek import DeepSeekError, as_api_error, chat_completion
from app.services.secrets import SecretStore, secret_store

router = APIRouter(prefix="/company/bot-agents", tags=["bot-agents"],
                   dependencies=[Depends(company_admin)])


def _validate_type(agent_type: str) -> None:
    if agent_type not in ("technical", "commercial"):
        raise unprocessable("AGENT_TYPE_INVALID", "agent_type debe ser technical o commercial.")


async def _agent_out(db: AsyncSession, a: BotAgent) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    conv = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == a.tenant_id, Conversation.chat_type == a.agent_type,
        Conversation.created_at >= since))).scalar() or 0
    res = (await db.execute(select(func.count()).select_from(Conversation).where(
        Conversation.tenant_id == a.tenant_id, Conversation.chat_type == a.agent_type,
        Conversation.created_at >= since, Conversation.status == "resolved",
        Conversation.escalated_at.is_(None)))).scalar() or 0
    return {"agent_type": a.agent_type, "enabled": a.enabled, "display_name": a.display_name,
            "topics": a.topics, "system_prompt": a.system_prompt,
            "knowledge_scope": a.knowledge_scope, "escalation_target": a.escalation_target,
            "metrics_7d": {"conversations": conv,
                           "resolved_pct": round(res * 100 / conv) if conv else 0}}


@router.get("")
async def list_bot_agents(tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    agents = (await db.execute(select(BotAgent).where(BotAgent.tenant_id == tenant.id)
                               .order_by(BotAgent.agent_type.desc()))).scalars().all()
    return {"agents": [await _agent_out(db, a) for a in agents]}


@router.patch("/{agent_type}")
async def patch_bot_agent(agent_type: str, body: BotAgentPatchIn,
                          tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    _validate_type(agent_type)
    agent = await rag.get_agent(db, tenant.id, agent_type)
    data = body.model_dump(exclude_unset=True)
    if agent_type == "technical" and data.get("enabled") is False:
        raise conflict("CANNOT_DISABLE_TECHNICAL", "El agente técnico no puede desactivarse.")
    for k, v in data.items():
        setattr(agent, k, v)
    await db.commit()
    return await _agent_out(db, agent)


@router.post("/{agent_type}/preview")
async def preview_bot_agent(agent_type: str, body: BotAgentPreviewIn,
                            tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    _validate_type(agent_type)
    agent = await rag.get_agent(db, tenant.id, agent_type)
    n_chunks = (await db.execute(select(func.count()).select_from(Chunk).where(
        Chunk.tenant_id == tenant.id, Chunk.chat_type.in_([agent_type, "both"])))).scalar() or 0
    if not n_chunks:
        raise conflict("KB_EMPTY", "No hay conocimiento indexado para este agente.")
    passages = await vectorstore.search(db, tenant.id, agent_type, body.message,
                                        include_web=agent.knowledge_scope != "own_type")
    api_key = secret_store.get(SecretStore.deepseek_key_name(tenant.id)) or ""
    msgs = [{"role": "system",
             "content": rag._system_prompt(tenant, agent, tenant.language, passages)}]
    msgs += [{"role": h.get("role", "user"), "content": h.get("content", "")} for h in body.history]
    msgs.append({"role": "user", "content": body.message})
    import time
    t0 = time.monotonic()
    try:
        text, tokens = await chat_completion(api_key, msgs)
    except DeepSeekError as e:
        raise as_api_error(e)
    db.add(UsageEvent(tenant_id=tenant.id, bot_type=agent_type, channel="preview", tokens=tokens))
    await db.commit()
    return {"answer": text,
            "sources": [{"document": p["chunk"].source_name,
                         "chunk": p["chunk"].content[:200],
                         "score": round(p["score"], 3)} for p in passages],
            "tokens_used": tokens, "latency_ms": int((time.monotonic() - t0) * 1000)}

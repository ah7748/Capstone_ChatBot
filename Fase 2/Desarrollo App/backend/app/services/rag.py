"""Motor conversacional: clasificador de intención + agentes RAG (técnico/comercial) + DeepSeek."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotAgent, Conversation, Message, Tenant, UsageEvent
from app.services import vectorstore
from app.services.deepseek import chat_completion
from app.services.secrets import SecretStore, secret_store

COMMERCIAL_HINTS = (
    "precio", "precios", "plan", "planes", "contratar", "contratación", "upgrade", "factur",
    "renovación", "renovar", "descuento", "cotiza", "comprar", "pricing", "price", "subscription",
    "billing", "preço", "assinatura", "cobrança",
)

LANG_NAMES = {"es": "español", "en": "inglés", "pt": "portugués"}


async def classify_intent(db: AsyncSession, tenant: Tenant, text: str) -> str:
    """Heurística rápida + agente comercial habilitado. (El prompt del LLM refina en respuesta.)"""
    commercial = (await db.execute(select(BotAgent).where(
        BotAgent.tenant_id == tenant.id, BotAgent.agent_type == "commercial"))).scalar_one_or_none()
    if not commercial or not commercial.enabled:
        return "technical"
    lowered = text.lower()
    return "commercial" if any(h in lowered for h in COMMERCIAL_HINTS) else "technical"


async def get_agent(db: AsyncSession, tenant_id, agent_type: str) -> BotAgent | None:
    return (await db.execute(select(BotAgent).where(
        BotAgent.tenant_id == tenant_id, BotAgent.agent_type == agent_type))).scalar_one_or_none()


def _system_prompt(tenant: Tenant, agent: BotAgent, lang: str, passages: list[dict]) -> str:
    ctx = "\n\n".join(
        f"[Fuente: {p['chunk'].source_name}]\n{p['chunk'].content}" for p in passages
    ) or "(sin pasajes recuperados)"
    base = agent.system_prompt or f"Eres el asistente de soporte de {tenant.name}."
    return (
        f"{base}\n\n"
        f"Responde SIEMPRE en {LANG_NAMES.get(lang, 'español')}. "
        "Responde únicamente con base en los pasajes de contexto siguientes. "
        "Si la información no está en el contexto, dilo con transparencia y ofrece derivar a una persona. "
        "No inventes datos, enlaces ni precios.\n\n"
        f"=== CONTEXTO ===\n{ctx}"
    )


async def answer(db: AsyncSession, tenant: Tenant, conversation: Conversation,
                 user_text: str, history: list[dict] | None = None) -> dict:
    """Pipeline completo para un mensaje de usuario. Devuelve dict con content/agent_type/etc."""
    agent_type = await classify_intent(db, tenant, user_text)
    agent = await get_agent(db, tenant.id, agent_type)
    if agent is None:
        agent_type = "technical"
        agent = await get_agent(db, tenant.id, "technical")

    passages = await vectorstore.search(
        db, tenant.id, agent_type, user_text,
        include_web=(agent.knowledge_scope != "own_type" if agent else True),
    )
    api_key = secret_store.get(SecretStore.deepseek_key_name(tenant.id)) or ""

    msgs = [{"role": "system", "content": _system_prompt(tenant, agent, conversation.lang, passages)}]
    for h in (history or [])[-8:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": user_text})

    text, tokens = await chat_completion(api_key, msgs)
    db.add(UsageEvent(tenant_id=tenant.id, bot_type=agent_type,
                      channel=conversation.channel, tokens=tokens))
    return {
        "content": text,
        "agent_type": agent_type,
        "sources_used": len(passages),
        "sources": [
            {"document": p["chunk"].source_name, "chunk": p["chunk"].content[:200], "score": round(p["score"], 3)}
            for p in passages
        ],
        "tokens": tokens,
    }


async def suggest_replies(db: AsyncSession, tenant: Tenant, conversation: Conversation) -> list[dict]:
    """Respuestas sugeridas para el agente humano, basadas en el último mensaje del usuario."""
    last_user = next((m for m in reversed(conversation.messages) if m.role == "user"), None)
    if last_user is None:
        return []
    passages = await vectorstore.search(db, tenant.id, conversation.chat_type, last_user.content, top_k=2)
    api_key = secret_store.get(SecretStore.deepseek_key_name(tenant.id)) or ""
    out = []
    for p in passages:
        prompt = [
            {"role": "system", "content":
             "Redacta una respuesta breve y cordial de un agente de soporte humano, en el idioma del usuario, "
             f"basada exclusivamente en este pasaje:\n{p['chunk'].content}"},
            {"role": "user", "content": last_user.content},
        ]
        try:
            text, tokens = await chat_completion(api_key, prompt)
            db.add(UsageEvent(tenant_id=tenant.id, bot_type=conversation.chat_type,
                              channel=conversation.channel, tokens=tokens))
        except Exception:
            text = p["chunk"].content[:300]
        out.append({"content": text, "source_document": p["chunk"].source_name,
                    "confidence": round(p["score"], 3)})
    return out

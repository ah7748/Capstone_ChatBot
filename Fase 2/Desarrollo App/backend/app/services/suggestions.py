"""Sugerencias de FAQ por IA: preguntas frecuentes de usuarios sin cobertura en el documento de FAQ."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Faq, FaqSuggestion, Message, Tenant
from app.services.deepseek import DeepSeekError, chat_completion
from app.services.embeddings import cosine, embed_texts
from app.services.secrets import SecretStore, secret_store

SIMILARITY_COVERED = 0.86


async def generate_suggestions(db: AsyncSession, tenant: Tenant, window_days: int = 30) -> int:
    """Analiza las preguntas de usuarios del período, agrupa por similitud, descarta las ya
    cubiertas por FAQ y genera respuesta sugerida con DeepSeek (RAG). Reemplaza las pendientes."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = (select(Message.content, Message.conversation_id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant.id, Message.role == "user",
                   Message.created_at >= since))
    rows = (await db.execute(stmt)).all()
    questions = [(c.strip(), cid) for c, cid in rows if len(c.strip()) > 12]
    if not questions:
        return 0

    faqs = (await db.execute(select(Faq).where(Faq.tenant_id == tenant.id))).scalars().all()
    faq_vecs = await embed_texts([f.question for f in faqs]) if faqs else []
    q_vecs = await embed_texts([q for q, _ in questions])

    # agrupar preguntas similares y contar frecuencia
    clusters: list[dict] = []
    for (text, cid), vec in zip(questions, q_vecs):
        if faq_vecs and max(cosine(vec, fv) for fv in faq_vecs) >= SIMILARITY_COVERED:
            continue  # ya cubierta por una FAQ
        for cl in clusters:
            if cosine(vec, cl["vec"]) >= 0.80:
                cl["freq"] += 1
                cl["convos"].append(str(cid))
                break
        else:
            clusters.append({"text": text, "vec": vec, "freq": 1, "convos": [str(cid)]})

    clusters = sorted((c for c in clusters if c["freq"] >= 1),
                      key=lambda c: c["freq"], reverse=True)[:10]

    await db.execute(delete(FaqSuggestion).where(FaqSuggestion.tenant_id == tenant.id,
                                                 FaqSuggestion.status == "pending"))
    api_key = secret_store.get(SecretStore.deepseek_key_name(tenant.id)) or ""
    from app.services import rag, vectorstore
    created = 0
    for cl in clusters:
        chat_type = "commercial" if any(h in cl["text"].lower() for h in rag.COMMERCIAL_HINTS) else "technical"
        passages = await vectorstore.search(db, tenant.id, chat_type, cl["text"], top_k=3)
        ctx = "\n".join(p["chunk"].content for p in passages)
        try:
            answer, _ = await chat_completion(api_key, [
                {"role": "system", "content":
                 "Eres redactor de FAQ. Escribe una respuesta breve, precisa y autocontenida "
                 f"basada solo en este contexto:\n{ctx}"},
                {"role": "user", "content": cl["text"]},
            ])
        except DeepSeekError:
            answer = (passages[0]["chunk"].content[:400] if passages
                      else "Respuesta pendiente de redacción.")
        db.add(FaqSuggestion(
            tenant_id=tenant.id, question=cl["text"][:300], suggested_answer=answer,
            chat_type=chat_type, frequency=cl["freq"], window_days=window_days,
            target_document=f"FAQ_{'soporte_tecnico' if chat_type == 'technical' else 'comerciales'}_{tenant.slug}.docx",
            sample_conversations=cl["convos"][:5],
        ))
        created += 1
    await db.flush()
    return created

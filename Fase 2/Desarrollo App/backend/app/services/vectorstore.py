"""Búsqueda semántica sobre la tabla chunks: pgvector en PostgreSQL, coseno en Python en otros motores."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.services.embeddings import cosine, embed_texts


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        cut = text.rfind(". ", start, end)
        if cut == -1 or cut <= start + max_chars // 2:
            cut = end
        else:
            cut += 1
        chunks.append(text[start:cut].strip())
        start = max(cut - overlap, start + 1) if cut < len(text) else len(text)
    return [c for c in chunks if c]


async def index_chunks(db: AsyncSession, tenant_id, source_kind: str, source_id,
                       source_name: str, chat_type: str, texts: list[str]) -> int:
    if not texts:
        return 0
    vectors = await embed_texts(texts)
    for content, emb in zip(texts, vectors):
        db.add(Chunk(tenant_id=tenant_id, source_kind=source_kind, source_id=source_id,
                     source_name=source_name, chat_type=chat_type, content=content, embedding=emb))
    await db.flush()
    return len(texts)


async def delete_source(db: AsyncSession, tenant_id, source_kind: str, source_id=None) -> None:
    stmt = delete(Chunk).where(Chunk.tenant_id == tenant_id, Chunk.source_kind == source_kind)
    if source_id is not None:
        stmt = stmt.where(Chunk.source_id == source_id)
    await db.execute(stmt)


async def search(db: AsyncSession, tenant_id, chat_type: str, query: str,
                 top_k: int = 5, include_web: bool = True) -> list[dict]:
    """Recupera los pasajes más relevantes del tipo indicado (+ both, + web si aplica)."""
    [qvec] = await embed_texts([query])
    types = [chat_type, "both"]
    kinds = ["document", "faq"] + (["web"] if include_web else [])
    if db.bind.dialect.name == "postgresql":
        dist = Chunk.embedding.cosine_distance(qvec)
        stmt = (select(Chunk, dist.label("dist"))
                .where(Chunk.tenant_id == tenant_id,
                       Chunk.chat_type.in_(types),
                       Chunk.source_kind.in_(kinds))
                .order_by(dist).limit(top_k))
        rows = (await db.execute(stmt)).all()
        return [{"chunk": c, "score": 1 - d} for c, d in rows]
    # fallback (SQLite en tests): coseno en Python
    stmt = select(Chunk).where(Chunk.tenant_id == tenant_id,
                               Chunk.chat_type.in_(types),
                               Chunk.source_kind.in_(kinds))
    chunks = (await db.execute(stmt)).scalars().all()
    scored = sorted(((cosine(qvec, c.embedding or []), c) for c in chunks),
                    key=lambda x: x[0], reverse=True)
    return [{"chunk": c, "score": s} for s, c in scored[:top_k]]

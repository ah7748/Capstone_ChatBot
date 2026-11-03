"""Tareas asíncronas (arq sobre Redis). Con WORKERS_INLINE=true se ejecutan en el proceso de la API."""
import uuid

from arq.connections import RedisSettings

from app.core.config import settings
from app.db.session import SessionLocal


async def task_ingest_document(ctx, document_id: str):
    from app.models import Document
    from app.services.ingestion import ingest_document
    from app.services.storage import storage
    from pathlib import Path
    async with SessionLocal() as db:
        doc = await db.get(Document, uuid.UUID(document_id))
        if doc is None:
            return
        data = None
        if doc.extracted_content is None and doc.blob_path and settings.STORAGE_BACKEND == "local":
            p = Path(settings.LOCAL_STORAGE_DIR) / doc.blob_path
            if p.exists():
                data = p.read_bytes()
        await ingest_document(db, doc, data)
        await db.commit()


async def task_scan_website(ctx, scan_id: str, base_url: str):
    from app.models import WebsiteScan
    from app.services.crawler import run_scan
    async with SessionLocal() as db:
        scan = await db.get(WebsiteScan, uuid.UUID(scan_id))
        if scan is None:
            return
        await run_scan(db, scan, base_url)
        await db.commit()


async def task_generate_suggestions(ctx, tenant_id: str, window_days: int):
    from app.models import Tenant
    from app.services.suggestions import generate_suggestions
    async with SessionLocal() as db:
        tenant = await db.get(Tenant, uuid.UUID(tenant_id))
        if tenant is not None:
            await generate_suggestions(db, tenant, window_days)
            await db.commit()


async def task_reindex_all(ctx, tenant_id: str):
    from sqlalchemy import select
    from app.models import Document, Faq, Tenant
    from app.services import vectorstore
    from app.services.ingestion import ingest_document
    async with SessionLocal() as db:
        tid = uuid.UUID(tenant_id)
        docs = (await db.execute(select(Document).where(Document.tenant_id == tid))).scalars().all()
        for doc in docs:
            await ingest_document(db, doc)
        faqs = (await db.execute(select(Faq).where(Faq.tenant_id == tid))).scalars().all()
        await vectorstore.delete_source(db, tid, "faq")
        for f in faqs:
            await vectorstore.index_chunks(db, tid, "faq", f.id, "FAQ", f.chat_type,
                                           [f"P: {f.question}\nR: {f.answer}"])
        await db.commit()


TASKS = {
    "task_ingest_document": task_ingest_document,
    "task_scan_website": task_scan_website,
    "task_generate_suggestions": task_generate_suggestions,
    "task_reindex_all": task_reindex_all,
}


async def enqueue(name: str, *args) -> None:
    """Encola en arq, o ejecuta inline en dev/test."""
    if settings.WORKERS_INLINE:
        await TASKS[name](None, *args)
        return
    from arq import create_pool
    pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        await pool.enqueue_job(name, *args)
    finally:
        await pool.close()


class WorkerSettings:
    functions = list(TASKS.values())
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

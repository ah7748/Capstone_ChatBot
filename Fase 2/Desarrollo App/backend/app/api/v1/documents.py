"""Sección 9 — Documentos del cliente."""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import Page, company_admin, get_tenant
from app.core.errors import conflict, err, not_found
from app.db.session import get_db
from app.models import Document, Tenant
from app.schemas.knowledge import DocumentContentIn, DocumentPatchIn
from app.services import vectorstore
from app.services.ingestion import ALLOWED_EXTENSIONS
from app.services.storage import storage
from app.workers.tasks import enqueue

router = APIRouter(prefix="/company", tags=["documents"], dependencies=[Depends(company_admin)])


def _doc_out(d: Document) -> dict:
    return {"document_id": str(d.id), "filename": d.filename, "chat_type": d.chat_type,
            "size_bytes": d.size_bytes, "status": d.status, "progress_pct": d.progress_pct,
            "chunks": d.chunks, "uploaded_at": d.uploaded_at.isoformat(),
            "indexed_at": d.indexed_at.isoformat() if d.indexed_at else None,
            "error_detail": d.error_detail, "version": d.version}


async def _doc_or_404(db: AsyncSession, tenant: Tenant, document_id: uuid.UUID) -> Document:
    d = await db.get(Document, document_id)
    if d is None or d.tenant_id != tenant.id:
        raise not_found("El documento no existe en este tenant.", "DOCUMENT_NOT_FOUND")
    return d


@router.get("/documents")
async def list_documents(chat_type: str = Query("all"), status: str | None = None,
                         search: str | None = None, page: Page = Depends(),
                         tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    stmt = select(Document).where(Document.tenant_id == tenant.id)
    if chat_type != "all":
        stmt = stmt.where(Document.chat_type == chat_type)
    if status:
        stmt = stmt.where(Document.status == status)
    if search:
        stmt = stmt.where(func.lower(Document.filename).contains(search.lower()))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    docs = (await db.execute(stmt.order_by(Document.uploaded_at.desc())
                             .offset(page.offset).limit(page.page_size))).scalars().all()
    return page.wrap([_doc_out(d) for d in docs], total)


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), chat_type: str = Form(...),
                          tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    if chat_type not in ("technical", "commercial", "both"):
        raise err(422, "VALIDATION_ERROR", "chat_type debe ser technical, commercial o both.")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise err(415, "FILE_TYPE_UNSUPPORTED", "Solo se admiten PDF, DOCX, TXT y MD.")
    data = await file.read()
    if len(data) > settings.MAX_DOCUMENT_MB * 1024 * 1024:
        raise err(413, "FILE_TOO_LARGE", f"El archivo supera los {settings.MAX_DOCUMENT_MB} MB.")
    content_hash = hashlib.sha256(data).hexdigest()
    existing = (await db.execute(select(Document).where(
        Document.tenant_id == tenant.id, Document.content_hash == content_hash))).scalar_one_or_none()
    if existing:
        raise conflict("DOCUMENT_DUPLICATE", "Ya existe un documento idéntico.",
                       {"document_id": str(existing.id)})
    blob_path = await storage.save(tenant.id, file.filename, data)
    doc = Document(tenant_id=tenant.id, filename=file.filename, chat_type=chat_type,
                   size_bytes=len(data), content_hash=content_hash, blob_path=blob_path)
    db.add(doc)
    await db.flush()
    doc_id = str(doc.id)
    if settings.WORKERS_INLINE:
        from app.services.ingestion import ingest_document
        await ingest_document(db, doc, data)
        await db.commit()
    else:
        await db.commit()
        await enqueue("task_ingest_document", doc_id)
    return {"document_id": doc_id, "filename": file.filename, "chat_type": chat_type,
            "status": "queued"}


@router.get("/documents/{document_id}")
async def get_document(document_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                       db: AsyncSession = Depends(get_db)):
    return _doc_out(await _doc_or_404(db, tenant, document_id))


@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: uuid.UUID, original: bool = Query(False),
                               tenant: Tenant = Depends(get_tenant),
                               db: AsyncSession = Depends(get_db)):
    d = await _doc_or_404(db, tenant, document_id)
    if original:
        url = await storage.download_url(d.blob_path)
        return {"download_url": url, "expires_in": 300}
    if d.status in ("queued", "processing"):
        raise conflict("DOCUMENT_NOT_READY", "La ingesta aún no termina; no hay contenido extraído.")
    return {"content": d.extracted_content or "", "version": d.version,
            "updated_at": (d.indexed_at or d.uploaded_at).isoformat()}


@router.put("/documents/{document_id}/content")
async def put_document_content(document_id: uuid.UUID, body: DocumentContentIn,
                               tenant: Tenant = Depends(get_tenant),
                               db: AsyncSession = Depends(get_db)):
    d = await _doc_or_404(db, tenant, document_id)
    if d.status == "processing":
        raise conflict("INGEST_IN_PROGRESS", "Hay una ingesta en curso sobre este documento.")
    if body.version != d.version:
        raise conflict("DOCUMENT_VERSION_CONFLICT",
                       "Otro usuario guardó una versión más nueva; recargue.",
                       {"current_version": d.version})
    d.extracted_content = body.content
    d.version += 1
    d.status = "queued"
    await db.commit()
    await enqueue("task_ingest_document", str(d.id))
    return {"document_id": str(d.id), "version": d.version, "status": d.status}


@router.patch("/documents/{document_id}")
async def patch_document(document_id: uuid.UUID, body: DocumentPatchIn,
                         tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    d = await _doc_or_404(db, tenant, document_id)
    data = body.model_dump(exclude_unset=True)
    retype = "chat_type" in data and data["chat_type"] != d.chat_type
    for k, v in data.items():
        setattr(d, k, v)
    if retype:
        from sqlalchemy import update
        from app.models import Chunk
        await db.execute(update(Chunk).where(Chunk.source_id == d.id)
                         .values(chat_type=d.chat_type))
    await db.commit()
    return _doc_out(d)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                          db: AsyncSession = Depends(get_db)):
    d = await _doc_or_404(db, tenant, document_id)
    if d.status == "processing":
        raise conflict("INGEST_IN_PROGRESS", "Espere o cancele la ingesta antes de eliminar.")
    await vectorstore.delete_source(db, tenant.id, "document", d.id)
    if d.blob_path:
        await storage.delete(d.blob_path)
    await db.delete(d)
    await db.commit()


@router.post("/documents/{document_id}/reingest", status_code=202)
async def reingest_document(document_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                            db: AsyncSession = Depends(get_db)):
    d = await _doc_or_404(db, tenant, document_id)
    if d.status == "processing":
        raise conflict("INGEST_IN_PROGRESS", "Ya hay una ingesta en curso.")
    d.status = "queued"
    await db.commit()
    await enqueue("task_ingest_document", str(d.id))
    return {"status": "queued"}


@router.post("/knowledge/reindex", status_code=202)
async def reindex_all(tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    processing = (await db.execute(select(func.count()).select_from(Document).where(
        Document.tenant_id == tenant.id, Document.status == "processing"))).scalar() or 0
    if processing:
        raise conflict("REINDEX_IN_PROGRESS", "Ya hay una reindexación global en curso.")
    await enqueue("task_reindex_all", str(tenant.id))
    return {"job_id": str(uuid.uuid4()), "status": "queued"}

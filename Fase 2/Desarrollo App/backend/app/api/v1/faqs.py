"""Sección 10 — Preguntas frecuentes: CRUD, import, sugerencias IA, mejoras y export."""
import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import delete as sqldelete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Page, company_admin, get_tenant
from app.core.errors import conflict, err, not_found, unprocessable
from app.db.session import get_db
from app.models import Faq, FaqImprovement, FaqSuggestion, Tenant
from app.schemas.knowledge import FaqIn, FaqPatchIn, SuggestionAcceptIn, SuggestionsAcceptAllIn
from app.services import vectorstore
from app.services.embeddings import cosine, embed_texts
from app.services.exporter import EXPORters
from app.workers.tasks import enqueue

router = APIRouter(prefix="/company/faqs", tags=["faqs"], dependencies=[Depends(company_admin)])

DUPLICATE_THRESHOLD = 0.92


def _faq_out(f: Faq) -> dict:
    return {"faq_id": str(f.id), "question": f.question, "answer": f.answer,
            "chat_type": f.chat_type, "source": f.source, "updated_at": f.updated_at.isoformat()}


async def _index_faq(db: AsyncSession, tenant_id, f: Faq) -> None:
    await vectorstore.delete_source(db, tenant_id, "faq", f.id)
    await vectorstore.index_chunks(db, tenant_id, "faq", f.id, "FAQ", f.chat_type,
                                   [f"P: {f.question}\nR: {f.answer}"])


async def _is_duplicate(db: AsyncSession, tenant_id, question: str,
                        exclude_id=None) -> Faq | None:
    faqs = (await db.execute(select(Faq).where(Faq.tenant_id == tenant_id))).scalars().all()
    faqs = [f for f in faqs if f.id != exclude_id]
    if not faqs:
        return None
    [qv] = await embed_texts([question])
    vecs = await embed_texts([f.question for f in faqs])
    best_i, best_s = max(enumerate(cosine(qv, v) for v in vecs), key=lambda x: x[1], default=(0, 0))
    return faqs[best_i] if best_s >= DUPLICATE_THRESHOLD else None


@router.get("")
async def list_faqs(chat_type: str = Query("all"), search: str | None = None,
                    page: Page = Depends(), tenant: Tenant = Depends(get_tenant),
                    db: AsyncSession = Depends(get_db)):
    stmt = select(Faq).where(Faq.tenant_id == tenant.id)
    if chat_type != "all":
        stmt = stmt.where(Faq.chat_type == chat_type)
    if search:
        s = search.lower()
        stmt = stmt.where(func.lower(Faq.question).contains(s) | func.lower(Faq.answer).contains(s))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    faqs = (await db.execute(stmt.order_by(Faq.updated_at.desc())
                             .offset(page.offset).limit(page.page_size))).scalars().all()
    return page.wrap([_faq_out(f) for f in faqs], total)


@router.post("", status_code=201)
async def create_faq(body: FaqIn, tenant: Tenant = Depends(get_tenant),
                     db: AsyncSession = Depends(get_db)):
    dup = await _is_duplicate(db, tenant.id, body.question)
    if dup:
        raise conflict("FAQ_DUPLICATE_QUESTION", "Ya existe una pregunta casi idéntica.",
                       {"faq_id": str(dup.id), "question": dup.question})
    f = Faq(tenant_id=tenant.id, **body.model_dump())
    db.add(f)
    await db.flush()
    await _index_faq(db, tenant.id, f)
    await db.commit()
    return _faq_out(f)


@router.patch("/{faq_id}")
async def patch_faq(faq_id: uuid.UUID, body: FaqPatchIn, tenant: Tenant = Depends(get_tenant),
                    db: AsyncSession = Depends(get_db)):
    f = await db.get(Faq, faq_id)
    if f is None or f.tenant_id != tenant.id:
        raise not_found("No existe.", "FAQ_NOT_FOUND")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    await _index_faq(db, tenant.id, f)
    await db.commit()
    return _faq_out(f)


@router.delete("/{faq_id}", status_code=204)
async def delete_faq(faq_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                     db: AsyncSession = Depends(get_db)):
    f = await db.get(Faq, faq_id)
    if f is None or f.tenant_id != tenant.id:
        raise not_found("No existe.", "FAQ_NOT_FOUND")
    await vectorstore.delete_source(db, tenant.id, "faq", f.id)
    await db.delete(f)
    await db.commit()


@router.post("/import")
async def import_csv(file: UploadFile = File(...), tenant: Tenant = Depends(get_tenant),
                     db: AsyncSession = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise err(415, "FILE_TYPE_UNSUPPORTED", "El archivo no es CSV.")
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    required = {"question", "answer", "chat_type"}
    if not reader.fieldnames or not required.issubset({c.strip().lower() for c in reader.fieldnames}):
        raise unprocessable("CSV_FORMAT_INVALID", "Faltan columnas obligatorias.",
                            {"expected": sorted(required)})
    inserted, rejected = 0, []
    for i, row in enumerate(reader, start=2):
        q = (row.get("question") or "").strip()
        a = (row.get("answer") or "").strip()
        ct = (row.get("chat_type") or "").strip().lower()
        if len(q) < 5 or len(a) < 5 or ct not in ("technical", "commercial"):
            rejected.append({"row": i, "reason_code": "INVALID_ROW",
                             "message": "Campos inválidos o tipo desconocido."})
            continue
        if await _is_duplicate(db, tenant.id, q):
            rejected.append({"row": i, "reason_code": "DUPLICATE", "message": "Pregunta ya existente."})
            continue
        f = Faq(tenant_id=tenant.id, question=q[:300], answer=a[:4000], chat_type=ct, source="import")
        db.add(f)
        await db.flush()
        await _index_faq(db, tenant.id, f)
        inserted += 1
    await db.commit()
    return {"inserted": inserted, "rejected": rejected}


@router.get("/suggestions")
async def get_suggestions(window_days: int = Query(30, ge=7, le=90),
                          chat_type: str = Query("all"),
                          tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    pending = (await db.execute(select(FaqSuggestion).where(
        FaqSuggestion.tenant_id == tenant.id, FaqSuggestion.status == "pending"))).scalars().all()
    if not pending or pending[0].window_days != window_days:
        await enqueue("task_generate_suggestions", str(tenant.id), window_days)
        pending = (await db.execute(select(FaqSuggestion).where(
            FaqSuggestion.tenant_id == tenant.id, FaqSuggestion.status == "pending"))).scalars().all()
    items = [s for s in pending if chat_type == "all" or s.chat_type == chat_type]
    return {"generated_at": items[0].created_at.isoformat() if items else None,
            "suggestions": [{
                "suggestion_id": str(s.id), "question": s.question, "frequency": s.frequency,
                "chat_type": s.chat_type, "suggested_answer": s.suggested_answer,
                "target_document": s.target_document,
                "sample_conversations": s.sample_conversations} for s in
                sorted(items, key=lambda s: s.frequency, reverse=True)]}


@router.post("/suggestions/{suggestion_id}/accept", status_code=201)
async def accept_suggestion(suggestion_id: uuid.UUID, body: SuggestionAcceptIn,
                            tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    s = await db.get(FaqSuggestion, suggestion_id)
    if s is None or s.tenant_id != tenant.id:
        raise not_found("No existe o expiró.", "SUGGESTION_NOT_FOUND")
    if s.status == "accepted":
        raise conflict("SUGGESTION_ALREADY_ACCEPTED", "Ya fue añadida.")
    f = Faq(tenant_id=tenant.id, question=s.question,
            answer=body.answer_override or s.suggested_answer,
            chat_type=body.chat_type_override or s.chat_type, source="suggestion")
    db.add(f)
    await db.flush()
    await _index_faq(db, tenant.id, f)
    s.status = "accepted"
    total = (await db.execute(select(func.count()).select_from(Faq).where(
        Faq.tenant_id == tenant.id))).scalar() or 0
    await db.commit()
    return {"faq_id": str(f.id), "faq_count": total}


@router.post("/suggestions/accept-all")
async def accept_all_suggestions(body: SuggestionsAcceptAllIn,
                                 tenant: Tenant = Depends(get_tenant),
                                 db: AsyncSession = Depends(get_db)):
    pending = (await db.execute(select(FaqSuggestion).where(
        FaqSuggestion.tenant_id == tenant.id, FaqSuggestion.status == "pending"))).scalars().all()
    if not pending:
        raise conflict("NO_PENDING_SUGGESTIONS", "No hay sugerencias pendientes.")
    created = 0
    for s in pending:
        f = Faq(tenant_id=tenant.id, question=s.question, answer=s.suggested_answer,
                chat_type=s.chat_type, source="suggestion")
        db.add(f)
        await db.flush()
        await _index_faq(db, tenant.id, f)
        s.status = "accepted"
        created += 1
    total = (await db.execute(select(func.count()).select_from(Faq).where(
        Faq.tenant_id == tenant.id))).scalar() or 0
    await db.commit()
    return {"created": created, "faq_count": total}


@router.get("/improvements")
async def get_improvements(chat_type: str = Query("all"), tenant: Tenant = Depends(get_tenant),
                           db: AsyncSession = Depends(get_db)):
    # análisis simple de duplicados por similitud entre FAQ existentes
    faqs = (await db.execute(select(Faq).where(Faq.tenant_id == tenant.id))).scalars().all()
    if chat_type != "all":
        faqs = [f for f in faqs if f.chat_type == chat_type]
    await db.execute(sqldelete(FaqImprovement).where(FaqImprovement.tenant_id == tenant.id,
                                                     FaqImprovement.status == "pending"))
    improvements = []
    if len(faqs) >= 2:
        vecs = await embed_texts([f.question for f in faqs])
        for i in range(len(faqs)):
            for j in range(i + 1, len(faqs)):
                if cosine(vecs[i], vecs[j]) >= 0.88:
                    imp = FaqImprovement(
                        tenant_id=tenant.id, kind="merge",
                        target_faq_ids=[str(faqs[i].id), str(faqs[j].id)],
                        proposal=f'Fusionar "{faqs[i].question}" y "{faqs[j].question}" en una sola entrada.',
                        rationale="Se responden de forma casi idéntica.")
                    db.add(imp)
                    improvements.append(imp)
    for f in faqs:
        if len(f.answer) > 1200:
            imp = FaqImprovement(tenant_id=tenant.id, kind="rewrite", target_faq_ids=[str(f.id)],
                                 proposal=f'Acortar y estructurar la respuesta de "{f.question}".',
                                 rationale="Respuestas largas generan repreguntas.")
            db.add(imp)
            improvements.append(imp)
    await db.commit()
    return {"improvements": [{
        "improvement_id": str(i.id), "kind": i.kind, "target_faq_ids": i.target_faq_ids,
        "proposal": i.proposal, "rationale": i.rationale} for i in improvements]}


@router.post("/improvements/{improvement_id}/apply")
async def apply_improvement(improvement_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                            db: AsyncSession = Depends(get_db)):
    imp = await db.get(FaqImprovement, improvement_id)
    if imp is None or imp.tenant_id != tenant.id:
        raise not_found("No existe o expiró.", "IMPROVEMENT_NOT_FOUND")
    if imp.status == "applied":
        raise conflict("IMPROVEMENT_ALREADY_APPLIED", "Ya aplicada.")
    affected = []
    if imp.kind == "merge" and len(imp.target_faq_ids) == 2:
        keep = await db.get(Faq, uuid.UUID(imp.target_faq_ids[0]))
        drop = await db.get(Faq, uuid.UUID(imp.target_faq_ids[1]))
        if keep and drop:
            await vectorstore.delete_source(db, tenant.id, "faq", drop.id)
            await db.delete(drop)
            await _index_faq(db, tenant.id, keep)
            affected = imp.target_faq_ids
    imp.status = "applied"
    await db.commit()
    return {"applied": True, "affected_faq_ids": affected}


@router.get("/export")
async def export_faqs(format: str = Query(...), chat_type: str = Query("all"),
                      tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    if format not in EXPORters:
        raise unprocessable("FORMAT_INVALID", "Formato no admitido.", {"allowed": list(EXPORters)})
    stmt = select(Faq).where(Faq.tenant_id == tenant.id)
    if chat_type != "all":
        stmt = stmt.where(Faq.chat_type == chat_type)
    faqs = (await db.execute(stmt.order_by(Faq.chat_type, Faq.question))).scalars().all()
    if not faqs:
        raise conflict("FAQ_EMPTY", "No hay FAQ que exportar para ese filtro.")
    fn, media, ext = EXPORters[format]
    data = fn(tenant, faqs)
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="FAQ_{tenant.slug}.{ext}"'})

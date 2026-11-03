"""Ingesta de documentos: extracción de texto (PDF/DOCX/TXT/MD), troceo e indexación vectorial."""
import io

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, now
from app.services import vectorstore

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    return data.decode("utf-8", errors="replace")


async def ingest_document(db: AsyncSession, document: Document, data: bytes | None = None) -> None:
    """Extrae (si hay bytes), trocea e indexa. Actualiza estado/progreso del documento."""
    document.status = "processing"
    document.progress_pct = 10
    document.error_detail = None
    await db.flush()
    try:
        if data is not None:
            document.extracted_content = extract_text(document.filename, data)
        text = document.extracted_content or ""
        if not text.strip():
            raise ValueError("No se pudo extraer texto del documento.")
        document.progress_pct = 50
        await vectorstore.delete_source(db, document.tenant_id, "document", document.id)
        n = await vectorstore.index_chunks(
            db, document.tenant_id, "document", document.id,
            document.filename, document.chat_type, vectorstore.chunk_text(text),
        )
        document.chunks = n
        document.status = "indexed"
        document.progress_pct = 100
        document.indexed_at = now()
    except Exception as e:
        document.status = "error"
        document.error_detail = str(e)[:500]
    await db.flush()

"""classify_intent con el LLM simulado (RF-BE-01): heurística → LLM → tipo previo."""
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Conversation, Tenant
from app.services import rag

pytestmark = pytest.mark.asyncio

AMBIGUO = "¿Cuánto me sale tenerlo todo el año?"   # la heurística no decide


async def _contexto(db, chat_type="technical"):
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == "wellq"))).scalar_one()
    convo = Conversation(tenant_id=tenant.id, channel="web", lang="es", chat_type=chat_type)
    return tenant, convo


@pytest.fixture
def llm(monkeypatch):
    """Simula la API key y registra cuántas veces se llamó al LLM."""
    monkeypatch.setattr(rag.secret_store, "get", lambda name: "sk-test")
    estado = {"llamadas": 0, "respuesta": ('{"type": "commercial", "confidence": 0.9}', 50),
              "error": None}

    async def falso(api_key, messages, model=None, temperature=0.3):
        estado["llamadas"] += 1
        if estado["error"]:
            raise estado["error"]
        return estado["respuesta"]

    monkeypatch.setattr(rag, "chat_completion", falso)
    return estado


async def test_senal_clara_no_llama_al_llm(seed, llm):
    async with SessionLocal() as db:
        tenant, convo = await _contexto(db)
        assert await rag.classify_intent(db, tenant, convo, "¿Cuánto cuesta el plan anual?") == "commercial"
    assert llm["llamadas"] == 0


async def test_ambiguo_usa_el_llm(seed, llm):
    async with SessionLocal() as db:
        tenant, convo = await _contexto(db)
        assert await rag.classify_intent(db, tenant, convo, AMBIGUO) == "commercial"
    assert llm["llamadas"] == 1


async def test_confianza_baja_mantiene_tipo_previo(seed, llm):
    llm["respuesta"] = ('{"type": "commercial", "confidence": 0.3}', 50)
    async with SessionLocal() as db:
        tenant, convo = await _contexto(db, chat_type="technical")
        assert await rag.classify_intent(db, tenant, convo, AMBIGUO) == "technical"


async def test_fallo_del_llm_mantiene_tipo_previo(seed, llm):
    llm["error"] = RuntimeError("DeepSeek caído")
    async with SessionLocal() as db:
        tenant, convo = await _contexto(db, chat_type="commercial")
        assert await rag.classify_intent(db, tenant, convo, AMBIGUO) == "commercial"


async def test_etiqueta_invalida_se_ignora(seed, llm):
    llm["respuesta"] = ('{"type": "hacked", "confidence": 0.99}', 50)
    async with SessionLocal() as db:
        tenant, convo = await _contexto(db, chat_type="technical")
        assert await rag.classify_intent(db, tenant, convo, AMBIGUO) == "technical"
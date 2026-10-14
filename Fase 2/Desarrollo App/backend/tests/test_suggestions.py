#RF-BE-05: sugerencias de FAQ por IA (app/services/suggestions.py).

#Valida la agrupación de preguntas por similitud, la exclusión de las ya cubiertas por una FAQ
#y la generación de la respuesta sugerida. DeepSeek se simula; los embeddings son los deEMBEDDINGS_BACKEND=hash (determinista), así que no hay red."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import Chunk, Conversation, Faq, FaqSuggestion, Message, Tenant
from app.services import suggestions
from app.services.deepseek import DeepSeekError
from app.services.embeddings import embed_texts

pytestmark = pytest.mark.asyncio

# Con el embedding hash: A1~A2~A3 (coseno 0.90) forman un grupo; B1~B2 (0.83) otro;
# C1 no se parece a nada. Todos superan el umbral de agrupación (0.80) solo dentro de su grupo.
A1 = "No puedo subir mi examen de sangre a la plataforma"
A2 = "No puedo subir mi examen de orina a la plataforma"
A3 = "No puedo subir mi examen de sangre a la aplicacion"
B1 = "Como cambio la contraseña de mi cuenta personal"
B2 = "Como cambio la contraseña de mi cuenta de usuario"
C1 = "Cuanto cuesta el plan anual de la plataforma"      # contiene "plan" -> comercial


# ------------------------------------------------------------------ fixtures
@pytest_asyncio.fixture
async def make_tenant():
    """Empresas aisladas (no tocan los datos del resto de la suite); se borran al final."""
    ids = []

    async def _make():
        async with SessionLocal() as db:
            t = Tenant(name="zz-sugerencias", slug=f"sugg-{uuid.uuid4().hex[:8]}",
                       legal_name="Sugerencias Test SpA", tax_id="1-9", country="CL",
                       language="es", languages=["es"], status="active")
            db.add(t)
            await db.commit()
            ids.append(t.id)
            return t.id

    yield _make
    async with SessionLocal() as db:
        for tid in ids:
            convos = select(Conversation.id).where(Conversation.tenant_id == tid)
            await db.execute(delete(Message).where(Message.conversation_id.in_(convos)))
            for model in (Conversation, FaqSuggestion, Faq, Chunk):
                await db.execute(delete(model).where(model.tenant_id == tid))
            await db.execute(delete(Tenant).where(Tenant.id == tid))
        await db.commit()


@pytest_asyncio.fixture
async def tid(make_tenant):
    return await make_tenant()


@pytest.fixture
def llm(monkeypatch):
    """Simula la API key y DeepSeek; registra cada llamada (mensajes enviados)."""
    monkeypatch.setattr(suggestions.secret_store, "get", lambda name: "sk-test")
    estado = {"llamadas": [], "error": None}

    async def falso(api_key, messages, model=None, temperature=0.3):
        estado["llamadas"].append({"api_key": api_key, "messages": messages})
        if estado["error"]:
            raise estado["error"]
        return "RESPUESTA REDACTADA POR IA", 42

    monkeypatch.setattr(suggestions, "chat_completion", falso)
    return estado


async def add_questions(tid, textos, role="user", days_ago=0, tenant_override=None):
    """Una conversación por pregunta (como en el chat real). Devuelve los ids de conversación."""
    ids = []
    async with SessionLocal() as db:
        for texto in textos:
            c = Conversation(tenant_id=tenant_override or tid, channel="web", lang="es")
            db.add(c)
            await db.flush()
            db.add(Message(conversation_id=c.id, role=role, content=texto,
                           created_at=datetime.now(timezone.utc) - timedelta(days=days_ago)))
            ids.append(c.id)
        await db.commit()
    return ids


async def add_faq(tid, question):
    async with SessionLocal() as db:
        db.add(Faq(tenant_id=tid, question=question, answer="Respuesta existente",
                   chat_type="technical"))
        await db.commit()


async def add_knowledge(tid, content, chat_type="technical"):
    [vec] = await embed_texts([content])
    async with SessionLocal() as db:
        db.add(Chunk(tenant_id=tid, source_kind="document", source_name="manual.txt",
                     chat_type=chat_type, content=content, embedding=vec))
        await db.commit()


async def run(tid, **kw):
    async with SessionLocal() as db:
        tenant = await db.get(Tenant, tid)
        n = await suggestions.generate_suggestions(db, tenant, **kw)
        await db.commit()
        return n


async def pendientes(tid):
    async with SessionLocal() as db:
        rows = (await db.execute(select(FaqSuggestion).where(
            FaqSuggestion.tenant_id == tid))).scalars().all()
        return sorted(rows, key=lambda s: s.frequency, reverse=True)


# ------------------------------------------------- agrupación por similitud
async def test_agrupa_preguntas_similares_y_cuenta_la_frecuencia(tid, llm):
    convos = await add_questions(tid, [A1, A2, A3, B1, B2, C1])
    assert await run(tid) == 3
    a, b, c = await pendientes(tid)                       # ordenadas por frecuencia
    assert (a.frequency, b.frequency, c.frequency) == (3, 2, 1)
    assert a.question == A1                                # el grupo toma la 1.ª pregunta
    assert b.question == B1 and c.question == C1
    assert {str(x) for x in convos[:3]} == set(a.sample_conversations)  # conversaciones del grupo
    assert a.window_days == 30


async def test_preguntas_distintas_no_se_agrupan(tid, llm):
    await add_questions(tid, [A1, B1, C1])
    assert await run(tid) == 3
    assert [s.frequency for s in await pendientes(tid)] == [1, 1, 1]


async def test_devuelve_maximo_10_sugerencias_las_mas_frecuentes(tid, llm):
    palabras = [f"{p}{i}" for i in range(12) for p in ("aaa", "bbb", "ccc", "ddd", "eee", "fff")]
    # 12 preguntas con vocabulario propio (sin parecido entre sí)
    unicas = [" ".join(palabras[i::12]) for i in range(12)]
    repetida = unicas[0]
    await add_questions(tid, unicas + [repetida, repetida])   # la primera aparece 3 veces
    assert await run(tid) == 10
    sugerencias = await pendientes(tid)
    assert len(sugerencias) == 10
    assert sugerencias[0].frequency == 3 and sugerencias[0].question == repetida


async def test_guarda_a_lo_mas_5_conversaciones_de_ejemplo(tid, llm):
    await add_questions(tid, [A1] * 7)
    await run(tid)
    [s] = await pendientes(tid)
    assert s.frequency == 7 and len(s.sample_conversations) == 5


# ------------------------------------- exclusión de preguntas ya cubiertas
async def test_excluye_las_preguntas_cubiertas_por_una_faq(tid, llm):
    await add_faq(tid, A1)                                 # la FAQ cubre el grupo A
    await add_questions(tid, [A1, A2, A3, B1, B2])
    assert await run(tid) == 1
    [s] = await pendientes(tid)
    assert s.question == B1 and s.frequency == 2           # solo queda el grupo B


async def test_una_faq_distinta_no_cubre_las_preguntas(tid, llm):
    await add_faq(tid, "Donde descargo la factura mensual de mi servicio")
    await add_questions(tid, [A1, A2])
    assert await run(tid) == 1
    assert (await pendientes(tid))[0].frequency == 2


async def test_si_todo_esta_cubierto_no_crea_sugerencias(tid, llm):
    await add_faq(tid, A1)
    await add_questions(tid, [A1, A2, A3])
    assert await run(tid) == 0
    assert await pendientes(tid) == []
    assert llm["llamadas"] == []                           # no gasta tokens


async def test_las_faq_de_otra_empresa_no_cubren(tid, make_tenant, llm):
    otro = await make_tenant()
    await add_faq(otro, A1)
    await add_questions(tid, [A1])
    assert await run(tid) == 1


# ----------------------------------------------- qué preguntas se analizan
async def test_ignora_mensajes_cortos_de_bot_antiguos_y_de_otras_empresas(tid, make_tenant, llm):
    otro = await make_tenant()
    await add_questions(tid, ["Hola", "ok gracias"])                  # <= 12 caracteres
    await add_questions(tid, [B1], role="bot")                        # no es del usuario
    await add_questions(tid, [C1], days_ago=45)                       # fuera de la ventana de 30 días
    await add_questions(otro, [A1])                                   # otra empresa
    assert await run(tid) == 0
    assert await pendientes(tid) == []


async def test_respeta_la_ventana_de_dias(tid, llm):
    await add_questions(tid, [C1], days_ago=45)
    assert await run(tid, window_days=30) == 0
    assert await run(tid, window_days=90) == 1
    [s] = await pendientes(tid)
    assert s.window_days == 90


async def test_sin_preguntas_devuelve_cero_sin_llamar_al_llm(tid, llm):
    assert await run(tid) == 0
    assert llm["llamadas"] == []


# ------------------------------------------- respuesta sugerida (RAG + LLM)
async def test_la_respuesta_sugerida_viene_del_llm_con_contexto_de_la_base(tid, llm):
    await add_knowledge(tid, "Ve a Salud > Exámenes > Subir archivo y elige tu examen de sangre.")
    await add_questions(tid, [A1])
    await run(tid)
    [s] = await pendientes(tid)
    assert s.suggested_answer == "RESPUESTA REDACTADA POR IA"
    [llamada] = llm["llamadas"]
    assert llamada["api_key"] == "sk-test"
    sistema, usuario = llamada["messages"]
    assert sistema["role"] == "system" and usuario == {"role": "user", "content": A1}
    assert "Subir archivo" in sistema["content"]            # el contexto recuperado va en el prompt


async def test_clasifica_el_tipo_y_el_documento_destino(tid, llm):
    async with SessionLocal() as db:
        slug = (await db.get(Tenant, tid)).slug
    await add_questions(tid, [C1, A1])
    await run(tid)
    por_pregunta = {s.question: s for s in await pendientes(tid)}
    comercial, tecnica = por_pregunta[C1], por_pregunta[A1]
    assert comercial.chat_type == "commercial"
    assert comercial.target_document == f"FAQ_comerciales_{slug}.docx"
    assert tecnica.chat_type == "technical"
    assert tecnica.target_document == f"FAQ_soporte_tecnico_{slug}.docx"


async def test_si_deepseek_falla_usa_el_pasaje_recuperado(tid, llm):
    llm["error"] = DeepSeekError("DEEPSEEK_UNREACHABLE", "sin conexión")
    contenido = "Ve a Salud > Exámenes > Subir archivo. " + "x" * 600
    await add_knowledge(tid, contenido)
    await add_questions(tid, [A1])
    assert await run(tid) == 1
    [s] = await pendientes(tid)
    assert s.suggested_answer == contenido[:400]


async def test_si_deepseek_falla_y_no_hay_contexto_deja_respuesta_pendiente(tid, llm):
    llm["error"] = DeepSeekError("DEEPSEEK_KEY_REJECTED", "clave rechazada")
    await add_questions(tid, [A1])
    assert await run(tid) == 1
    assert (await pendientes(tid))[0].suggested_answer == "Respuesta pendiente de redacción."


# ------------------------------------------------- reemplazo de pendientes
async def test_reemplaza_las_pendientes_y_conserva_las_aceptadas(tid, llm):
    await add_questions(tid, [A1])
    await run(tid)
    async with SessionLocal() as db:                        # una pendiente vieja y una aceptada
        db.add(FaqSuggestion(tenant_id=tid, question="Vieja pendiente", suggested_answer="x",
                             chat_type="technical", status="pending"))
        db.add(FaqSuggestion(tenant_id=tid, question="Ya aceptada", suggested_answer="y",
                             chat_type="technical", status="accepted"))
        await db.commit()
    assert await run(tid) == 1
    estado = {(s.question, s.status) for s in await pendientes(tid)}
    assert estado == {(A1, "pending"), ("Ya aceptada", "accepted")}   # sin duplicar ni conservar la vieja


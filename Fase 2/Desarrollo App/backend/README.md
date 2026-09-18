# Chatbot de Soporte Genérico · Backend

Backend FastAPI del módulo de administración y chat de soporte multiempresa de Alloxentric.
Implementa los **76 endpoints REST + 2 canales WebSocket** de la *Especificación de API Backend v1.1*
(documento en la carpeta del proyecto), con el stack definido: **FastAPI · PostgreSQL (pgvector) ·
Azure · JWT RS256 (access + refresh) · React como frontend consumidor**.

## Arranque rápido (docker-compose)

```bash
cp .env.example .env          # revisa las variables
docker compose up --build     # db (pgvector) + redis + api + worker
# API:    http://localhost:8000        (docs interactivas en /docs)
# Salud:  http://localhost:8000/health
```

Las migraciones Alembic corren automáticamente al arrancar el contenedor `api`
(`alembic upgrade head`). Sin Docker: `pip install -r requirements.txt`,
levanta PostgreSQL con pgvector y Redis, y ejecuta `alembic upgrade head &&
uvicorn app.main:app --reload`.

## Tests

```bash
pip install -r requirements.txt pytest pytest-asyncio
pytest
```

La suite (16 tests) cubre: login/refresh con rotación y detección de reutilización,
control de roles, creación de tenants y duplicados, aislamiento multi-tenant,
subida/edición/borrado de documentos con ingesta e indexación, CRUD y export de FAQ,
import CSV, flujo completo de chat público → derivación → consola de agente
(claim atómico, respuesta, resolución, valoración) y derivación a ticket sin agentes.
Los tests corren sobre SQLite (aiosqlite) con embeddings deterministas; en producción
la búsqueda vectorial usa pgvector (índice HNSW creado en la migración 0001).

## Integraciones reales y modos de desarrollo

Cada integración externa tiene cliente real y un backend local para desarrollar sin credenciales:

| Integración | Cliente real | Modo dev (variable) |
|---|---|---|
| LLM | DeepSeek `chat/completions` (httpx, API key por tenant) | — (sin key responde error controlado `DEEPSEEK_KEY_MISSING`) |
| Embeddings | Azure OpenAI (`EMBEDDINGS_BACKEND=azure_openai`) | `hash` (determinista, para dev/tests) |
| Secretos | Azure Key Vault (`SECRETS_BACKEND=keyvault`) | `env` (var/secrets.json, chmod 600) |
| Archivos | Azure Blob Storage + SAS (`STORAGE_BACKEND=azure_blob`) | `local` (var/storage) |
| WhatsApp | Meta Cloud API (envío + webhook con firma HMAC) | firma opcional sin `WHATSAPP_APP_SECRET` |
| Colas | arq sobre Redis (`WORKERS_INLINE=false` + servicio `worker`) | `true` = tareas inline |
| Tiempo real | Redis pub/sub entre réplicas | fallback en memoria |

**Nota de arquitectura:** la especificación menciona Azure Service Bus + Celery como opción de colas;
esta implementación usa **arq** (async-nativo sobre Redis) por coherencia con SQLAlchemy async.
En Azure se despliega igual (Container Apps + Azure Cache for Redis); si se exige Service Bus,
`app/workers/tasks.py::enqueue` es el único punto a sustituir.

## Estructura

```
app/
  main.py               # app FastAPI, CORS, manejador del formato de error {"error": {...}}
  models.py             # 15 tablas SQLAlchemy 2.0 (multi-tenant, pgvector en chunks)
  core/                 # config (pydantic-settings), seguridad JWT RS256, deps de auth, errores
  db/                   # sesión async, tipo EmbeddingVector (pgvector ↔ JSON en tests)
  schemas/              # Pydantic v2: auth, admin, knowledge, chat
  api/v1/
    auth.py             # §6  login, refresh (rotación), logout, me, invitaciones, reset (7)
    platform.py         # §7  dashboard global, CRUD tenants, usage por período, agentes RO (10)
    company.py          # §8  dashboard + detalle de KPIs, settings, API key DeepSeek (6)
    documents.py        # §9  documentos por tipo de chat, contenido editable, reingesta (9)
    faqs.py             # §10 CRUD, import CSV, sugerencias IA, mejoras, export pdf/json/docx (11)
    website.py          # §11 URL + escaneos con progreso (4)
    bot_agents.py       # §12 agentes técnico/comercial + preview RAG (3)
    human_agents.py     # §13 CRUD agentes humanos con reasignación (4)
    channels.py         # §14 web/widget/dominios, derivación, WhatsApp (5)
    public_chat.py      # §15 config widget, sesiones, mensajes RAG, escalate, rating (6)
    agent_console.py    # §17 colas, claim atómico, mensajes, sugerencias RAG, tickets (9)
    webhooks.py         # §18 WhatsApp (verificación + eventos firmados) (2)
    ws.py               # §19 /ws/chat/{session_id} y /ws/agent
  services/             # deepseek, embeddings, vectorstore, rag (clasificador+agentes),
                        # ingestion, crawler, escalation, suggestions, exporter, whatsapp,
                        # storage, secrets, usage, realtime, ratelimit
  workers/tasks.py      # tareas arq: ingesta, escaneo, sugerencias, reindexado
alembic/                # migración 0001 (extensión vector + esquema + índice HNSW)
tests/                  # 16 tests (ver arriba)
```

## Primer arranque funcional

1. Crear el superadmin (una vez, en `python -c` o shell):
   ```python
   import asyncio
   from app.db.session import SessionLocal
   from app.models import User
   from app.core.security import hash_password
   async def main():
       async with SessionLocal() as db:
           db.add(User(name="Admin", email="admin@alloxentric.com", role="platform_admin",
                       password_hash=hash_password("CambiaEsta123"), status="active"))
           await db.commit()
   asyncio.run(main())
   ```
2. `POST /api/v1/auth/login` → crear empresas con `POST /api/v1/platform/tenants`
   (aprovisiona agentes del bot, guarda la API key DeepSeek e invita al admin de empresa).
3. El admin de empresa activa su cuenta (`/auth/invitations/accept`), sube documentos,
   FAQ y URL del sitio, y comparte `soporte.allox.ai/{slug}` o el widget.

## Despliegue Azure de referencia

Container Apps (api + worker) · PostgreSQL Flexible Server con `vector` ·
Azure Cache for Redis · Blob Storage · Key Vault (claves JWT y secretos por tenant vía
`DefaultAzureCredential`) · Static Web Apps (frontend React) · Application Insights.

# Chatbot de Soporte Genérico · Backend

![CI](https://github.com/ah7748/Capstone_ChatBot/actions/workflows/ci.yml/badge.svg)

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
pip install -r requirements-dev.txt
ruff check .
python -m pytest
```

Estos mismos pasos los ejecuta el CI (`.github/workflows/ci.yml`) en cada push a `main` y en cada Pull Request.

La suite cubre:: login/refresh con rotación y detección de reutilización,
control de roles, creación de tenants y duplicados, aislamiento multi-tenant,
subida/edición/borrado de documentos con ingesta e indexación, CRUD y export de FAQ,
import CSV, flujo completo de chat público → derivación → consola de agente
(claim atómico, respuesta, resolución, valoración) y derivación a ticket sin agentes.
Los tests corren sobre SQLite (aiosqlite) con embeddings deterministas; en producción
la búsqueda vectorial usa pgvector (índice HNSW creado en la migración 0001).

También hay pruebas de la derivación por intención (hablar con un agente, crear ticket, cerrar la
conversación), de la sesión cerrada (409 `SESSION_CLOSED`), del texto plano del bot y del hash de tokens.

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
| Correo | SMTP (`EMAIL_BACKEND=smtp`) | `console` (dev) / `memory` (tests) |

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
alembic/                # 0001 (extensión vector + esquema + índice HNSW) · 0002 (tokens guardados con hash SHA-256)
tests/                  # suite pytest (ver arriba)
```

## Primer arranque funcional

1. Crear el superadmin. Define en `.env` las variables `SUPERADMIN_EMAIL` y
   `SUPERADMIN_PASSWORD` (puedes partir copiando `.env.example`). El superadmin se crea
   solo al arrancar, con `python -m app.cli seed`. El comando es repetible: si el
   superadmin ya existe, no lo duplica ni le cambia la contraseña.

   Para cargar además una empresa de prueba (solo desarrollo; está bloqueado si
   `APP_ENV` es `prod`): `python -m app.cli seed --demo`, con las variables `DEMO_*`
   del `.env`.
   ```
2. `POST /api/v1/auth/login` → crear empresas con `POST /api/v1/platform/tenants`
   (aprovisiona agentes del bot, guarda la API key DeepSeek e invita al admin de empresa).
3. El admin de empresa activa su cuenta (`/auth/invitations/accept`), sube documentos,
   FAQ y URL del sitio, y comparte `soporte.allox.ai/{slug}` o el widget.

## Configuracion inicial (Obligatorio antes de producción)

Los datos de acceso del repositorio son ficticios. Antes de desplegar:

1. Copia `.env.example` a `.env`.
2. Cambia `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD` por los datos reales del cliente.
3. No uses la opción `--demo` en producción.
4. En producción, define estas variables en el hosting, no en un archivo.

## Despliegue Azure de referencia

Container Apps (api + worker) · PostgreSQL Flexible Server con `vector` ·
Azure Cache for Redis · Blob Storage · Key Vault (claves JWT y secretos por tenant vía
`DefaultAzureCredential`) · Static Web Apps (frontend React) · Application Insights.

## Observabilidad 

| Pilar | Qué hay | Dónde |
|---|---|---|
| Logs estructurados | JSON por línea en prod (`LOG_FORMAT=auto`), con `request_id`, ruta, estado y duración. Nunca se registran cuerpos, cabeceras, consultas ni claves. | stdout (Railway/Azure lo recogen) |
| Métricas | Formato Prometheus: `http_requests_total`, `http_request_duration_seconds`, `app_unhandled_exceptions_total`, `llm_requests_total`, `llm_request_duration_seconds`, `llm_tokens_total`. | `GET /metrics` (con `METRICS_TOKEN` en prod) |
| Trazas / correlación | Cada petición recibe `X-Request-ID` (se respeta el del cliente si es válido). Un error 500 devuelve ese mismo valor como `trace_id`, así que el id que ve el usuario se busca directo en los logs. | cabecera `X-Request-ID` |
| Salud | `/health` (liveness) y `/health/ready` (readiness: base de datos y Redis; 503 si la BD falla). | — |
| Azure Application Insights | Opcional: `pip install -r requirements-azure.txt` y definir `APPLICATIONINSIGHTS_CONNECTION_STRING`. Sin eso no hace nada. | `app/observability/azure_monitor.py` |

Para diagnosticar un error en producción: tomar el `trace_id` de la respuesta y buscarlo en los logs (`request_id`).

## Comportamiento del bot

- El chat detecta tres intenciones sin llamar al modelo: **hablar con una persona** (deriva a un agente en vivo o a ticket
  según la disponibilidad), **crear un ticket** (si la empresa lo permite) y **cerrar la conversación** (queda `resuelta`).
- Una conversación cerrada responde `409 SESSION_CLOSED`; el usuario debe iniciar una nueva.
- Las respuestas se entregan en **texto plano** (`app/services/prompts.py::plain_text`) y a todo prompt se le añaden
  las reglas de estilo (`STYLE_RULES`), aunque la empresa lo haya personalizado. El prompt por defecto se crea con
  `default_agent_prompt(empresa, tipo)`.
- La clave del modelo de IA es por empresa (almacén de secretos), nunca una variable global; el proveedor se configura con
  `DEEPSEEK_BASE_URL` y `DEEPSEEK_DEFAULT_MODEL` (por ejemplo Groq: `https://api.groq.com/openai/v1`, `openai/gpt-oss-120b`).

## Seguridad de tokens

Los tokens de invitación, restablecimiento de contraseña y refresco se guardan como **SHA-256**; el valor en claro solo
viaja por correo o al cliente. La migración `0002_hash_tokens` convierte los existentes al desplegar (los de refresco
siguen funcionando; los de invitación/restablecimiento pendientes se conservan hasheados). Tras un incidente de credenciales,
rotar claves y ejecutar `DELETE FROM refresh_tokens;` cierra todas las sesiones.

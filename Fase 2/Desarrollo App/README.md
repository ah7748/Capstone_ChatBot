# Chatbot de Soporte Genérico · Frontend

SPA en **React 18 + Vite (JavaScript)** que consume el backend FastAPI del proyecto.
Un **login único** (`/login`) autentica contra `POST /api/v1/auth/login` y monta la interfaz
según el rol que devuelve el token:

| Rol | Interfaz | Ruta |
|---|---|---|
| `platform_admin` | Admin Plataforma (dashboard global, empresas con ficha y consumo por período, agentes en solo lectura, configuración) | `/platform` |
| `company_admin` | Admin Empresa (dashboard con KPIs clickeables, documentos por tipo de chat, FAQ con sugerencias IA y export, escaneo del sitio, agentes del bot con vista previa, agentes humanos CRUD, canales, configuración) | `/company` |
| `human_agent` | Consola de Agente (colas en vivo/tickets por WebSocket, transcripción, respuestas sugeridas RAG, tomar/devolver/resolver) | `/console` |
| — (usuario final) | Chat público sin login, con derivación y valoración | `/c/{slug}` |

## Arranque

```bash
npm install
npm run dev        # http://localhost:5173 (proxy /api y /ws → localhost:8000)
npm run build      # dist/ listo para Azure Static Web Apps
```

Variables (`.env`): `VITE_API_URL` (vacío en dev: usa el proxy de Vite) y `VITE_PUBLIC_BASE`.

## Arquitectura

- `src/api/client.js` — fetch con Bearer JWT y **renovación automática**: ante
  `401 AUTH_TOKEN_EXPIRED` llama a `/auth/refresh` (rotación de refresh token) y reintenta
  una vez; errores tipados `{status, code, message}` con los códigos estables de la API.
- `src/context/` — `AuthContext` (login único + ruteo por rol), `ThemeContext`
  (claro/oscuro persistente) e `I18nContext` (ES/EN/PT).
- `src/components/` — `Layout` (topbar + sidebar por rol) y `ui` (Modal, Badge, Kpi, Toast).
- `src/pages/` — una carpeta por interfaz; todas las vistas llaman a la API real
  (sin datos simulados).
- `public/widget.js` — script embebible: burbuja flotante + iframe a `/c/{slug}?embed=1`,
  API `window.AlloxChat` (open/close/toggle/identify/setLang/on/destroy) y evento `allox:ready`,
  como define la sección 16 de la especificación.
- Estilos: `src/styles.css`, heredados del wireframe v5 (paleta Alloxentric, modo oscuro).

## Tiempo real

- Consola de agente: `wss://…/ws/agent?token=<access>` — refresca colas y conversación
  ante `queue.updated` y `message.user`; marca presencia `available` al entrar.
- Chat público: `wss://…/ws/chat/{session_id}?token=<session_token>` — recibe
  `message.agent`, `agent.joined`, `escalation.update` y `session.closed`
  (con *fallback* a REST si el WebSocket no conecta).

## Probar de punta a punta

1. Levanta el backend (`docker compose up` en `backend/`) y crea el superadmin (README del backend).
2. `npm run dev`, entra con el superadmin → interfaz de plataforma; crea una empresa.
3. Activa al admin de empresa (invitación), sube documentos y FAQ, y abre `/c/{slug}`
   en otra pestaña para conversar con el bot; deriva a humano y atiende desde `/console`
   con un usuario `human_agent`.

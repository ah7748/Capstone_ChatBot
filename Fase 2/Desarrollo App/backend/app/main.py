"""Chatbot de Soporte Genérico · Backend FastAPI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import ApiError, internal_error_response
from app.api.v1 import (
    agent_console, auth, bot_agents, channels, company, documents, faqs,
    human_agents, platform, public_chat, webhooks, website, ws,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Chatbot de Soporte Genérico · API",
    version="1.1",
    description="Backend FastAPI del módulo de administración y chat de soporte multiempresa "
                "(Alloxentric). Especificación funcional: Especificacion_API_Backend v1.1.",
    lifespan=lifespan,
)

@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        return internal_error_response(request, exc)
    
class PathAwareCORS:
    
    PUBLIC_PREFIX = f"/api/v1/public/chat"

    def __init__(self, app):
        comun = dict(allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
        self._publico = CORSMiddleware(app, allow_origins=["*"], **comun)
        self._privado = CORSMiddleware(
            app, allow_origins=settings.CORS_ORIGINS,
            allow_origin_regex=settings.CORS_ORIGIN_REGEX, **comun)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(self.PUBLIC_PREFIX):
            await self._publico(scope, receive, send)
        else:
            await self._privado(scope, receive, send)


app.add_middleware(PathAwareCORS)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {
        "code": "VALIDATION_ERROR",
        "message": "Cuerpo o parámetros inválidos.",
        "detail": exc.errors()}})

@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    return internal_error_response(request, exc)

API = "/api/v1"
for r in (auth.router, platform.router, company.router, documents.router, faqs.router,
          website.router, bot_agents.router, human_agents.router, channels.router,
          public_chat.router, agent_console.router, webhooks.router):
    app.include_router(r, prefix=API)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV}

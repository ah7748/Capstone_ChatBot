"""Chatbot de Soporte Genérico · Backend FastAPI."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import ApiError
from app.api.v1 import (
    agent_console, auth, bot_agents, channels, company, documents, faqs,
    human_agents, platform, public_chat, webhooks, website, ws,
)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_origin_regex=r"https?://.*",  # los endpoints públicos validan Origin por tenant
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {
        "code": "VALIDATION_ERROR",
        "message": "Cuerpo o parámetros inválidos.",
        "detail": exc.errors()}})


API = "/api/v1"
for r in (auth.router, platform.router, company.router, documents.router, faqs.router,
          website.router, bot_agents.router, human_agents.router, channels.router,
          public_chat.router, agent_console.router, webhooks.router):
    app.include_router(r, prefix=API)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV}

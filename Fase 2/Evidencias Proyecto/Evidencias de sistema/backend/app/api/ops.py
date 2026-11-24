"""Endpoints operativos: /health/ready (readiness) y /metrics (formato Prometheus)."""
import asyncio
import hmac
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import not_found, unauthorized
from app.db.session import SessionLocal
from app.observability import metrics
from app.services import ratelimit

logger = logging.getLogger("app.ops")
router = APIRouter(tags=["ops"], include_in_schema=False)


@router.get("/metrics")
async def metrics_endpoint(request: Request):
    token = settings.METRICS_TOKEN
    if not token and settings.APP_ENV == "prod":
        raise not_found("No encontrado.", "NOT_FOUND")  # en producción, sin token configurado: deshabilitado
    if token:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            raise unauthorized("METRICS_UNAUTHORIZED", "Token de métricas inválido o ausente.")
    return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health/ready")
async def readiness():
    """200 si la base de datos responde; 503 si no. Redis es opcional (hay respaldo en memoria)."""
    checks: dict[str, str] = {}
    try:
        async with SessionLocal() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=3)
        checks["database"] = "ok"
    except Exception:
        logger.exception("readiness: la base de datos no responde")
        checks["database"] = "unavailable"
    checks["redis"] = "ok" if await ratelimit._get_redis() is not None else "fallback_memory"
    ok = checks["database"] == "ok"
    return JSONResponse(status_code=200 if ok else 503,
                        content={"status": "ok" if ok else "degraded", "checks": checks})

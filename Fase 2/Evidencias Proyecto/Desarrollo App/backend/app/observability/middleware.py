"""Middleware ASGI de observabilidad: request_id, registro de acceso y métricas HTTP.

Es ASGI puro (sin BaseHTTPMiddleware) para no interferir con streaming ni WebSockets y para
quedar como capa más externa: ve también las respuestas 500 que generan otros manejadores.
"""
import logging
import re
import time
import uuid

from app.observability import metrics
from app.observability.logging_config import request_id_var

access_log = logging.getLogger("app.access")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NUMBER = re.compile(r"^\d+$")
QUIET_PATHS = frozenset({"/health", "/health/ready", "/metrics"})  # sondeos: se registran en DEBUG


def normalize_path(path: str) -> str:
    """Sustituye ids numéricos y UUID por {id} para acotar la cardinalidad de las etiquetas."""
    parts = ["{id}" if (_NUMBER.match(p) or _UUID.match(p)) else p for p in path.split("/")]
    return "/".join(parts)


def route_label(scope: dict, status: int) -> str:
    """Plantilla de la ruta ('/api/v1/company/faqs/{faq_id}'); 'unmatched' si no hubo coincidencia."""
    route = scope.get("route")
    template = getattr(route, "path", None) or getattr(route, "path_format", None)
    if template:
        return template
    if status == 404:
        return "unmatched"  # rutas inexistentes (escáneres, bots): una sola etiqueta
    return normalize_path(scope.get("path", "/"))


def _incoming_request_id(scope: dict) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_ID.match(candidate) else None
    return None


class ObservabilityMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        result = {"status": 500}

        async def send_with_id(message) -> None:
            if message["type"] == "http.response.start":
                result["status"] = message["status"]
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            result["status"] = 500
            raise
        finally:
            duration = time.perf_counter() - started
            status = result["status"]
            method = scope.get("method", "GET")
            route = route_label(scope, status)
            metrics.HTTP_REQUESTS.inc(method=method, route=route, status=status)
            metrics.HTTP_DURATION.observe(duration, method=method, route=route)
            path = scope.get("path", "")
            level = (logging.DEBUG if path in QUIET_PATHS
                     else logging.WARNING if status >= 500 else logging.INFO)
            access_log.log(
                level, "%s %s %s %.0fms", method, route, status, duration * 1000,
                extra={"method": method, "route": route, "status": status,
                       "duration_ms": round(duration * 1000, 1)},
            )
            request_id_var.reset(token)

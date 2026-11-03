"""Logs estructurados (JSON) con correlación por request_id.

Reglas de seguridad: el middleware registra solo método, ruta (plantilla), estado y duración.
Nunca se registran cuerpos, cabeceras, query strings ni claves de API.
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

# Identificador de la petición en curso; lo fija el middleware y lo lee el formateador.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

# Atributos estándar de LogRecord: todo lo demás que venga en `extra=` se incluye como campo propio.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}
_OWN_HANDLER = "_app_observability_handler"


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro: ts, level, logger, message, request_id + campos extra."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Formato legible para desarrollo; añade el request_id si existe."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        rid = request_id_var.get()
        return f"{line} [request_id={rid}]" if rid else line


class _StdoutHandler(logging.StreamHandler):
    """Escribe en el stdout vigente en cada emisión (evita streams cerrados bajo pytest)."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:  # StreamHandler.__init__ asigna el stream; lo ignoramos
        pass


def resolve_log_format(fmt: str, env: str) -> str:
    """'auto' → json en producción, texto en el resto; cualquier otro valor se respeta si es válido."""
    fmt = (fmt or "auto").lower()
    if fmt == "auto":
        return "json" if env == "prod" else "text"
    return fmt if fmt in ("json", "text") else "text"


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configura el logging raíz. Es idempotente: reemplaza solo su propio handler."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _OWN_HANDLER, False):
            root.removeHandler(handler)
    handler = _StdoutHandler()
    setattr(handler, _OWN_HANDLER, True)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    # uvicorn: sus registros pasan por nuestro formato; el access log lo reemplaza el middleware.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True

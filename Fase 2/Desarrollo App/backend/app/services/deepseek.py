"""Cliente de la API de IA (chat/completions compatible con OpenAI), una API key por tenant.

Instrumentado (RF-BE-06): cada llamada registra duración, resultado y tokens en las métricas
y deja una línea de log estructurada. Nunca se registran los mensajes ni la clave.
"""
import logging
import time

import httpx

from app.core.config import settings
from app.core.errors import err
from app.observability import metrics

log = logging.getLogger("app.llm")

# resultado de la llamada → etiqueta de la métrica llm_requests_total
_OUTCOMES = {"DEEPSEEK_KEY_MISSING": "key_missing", "DEEPSEEK_KEY_REJECTED": "key_rejected",
             "DEEPSEEK_UNREACHABLE": "unreachable"}


class DeepSeekError(Exception):
    def __init__(self, code: str, message: str, outcome: str | None = None):
        self.code, self.message = code, message
        self.outcome = outcome or _OUTCOMES.get(code, "error")
        super().__init__(message)


async def _request(api_key: str, messages: list[dict], model: str, temperature: float) -> tuple[str, int]:
    if not api_key:
        raise DeepSeekError("DEEPSEEK_KEY_MISSING", "La empresa no tiene API key configurada o válida.")
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    try:
        async with httpx.AsyncClient(base_url=settings.DEEPSEEK_BASE_URL, timeout=60) as client:
            r = await client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError:
        raise DeepSeekError("DEEPSEEK_UNREACHABLE", "No se pudo contactar la API de DeepSeek; reintentar.")
    if r.status_code in (401, 402, 403):
        raise DeepSeekError("DEEPSEEK_KEY_REJECTED", "DeepSeek rechazó la clave (inválida o sin crédito).")
    if r.status_code >= 400:
        raise DeepSeekError("DEEPSEEK_UNREACHABLE", f"DeepSeek respondió {r.status_code}.")
    try:
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        tokens = int((data.get("usage") or {}).get("total_tokens", 0))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise DeepSeekError("DEEPSEEK_UNREACHABLE", "DeepSeek devolvió una respuesta con formato inesperado.",
                            outcome="bad_response")
    if not isinstance(text, str) or not text.strip():
        raise DeepSeekError("DEEPSEEK_UNREACHABLE", "DeepSeek devolvió una respuesta vacía.",
                            outcome="bad_response")
    return text, tokens


async def chat_completion(api_key: str, messages: list[dict],
                          model: str | None = None, temperature: float = 0.3) -> tuple[str, int]:
    """Devuelve (texto, tokens_totales). Lanza DeepSeekError en fallos."""
    model = model or settings.DEEPSEEK_DEFAULT_MODEL
    started = time.perf_counter()
    outcome = "ok"
    try:
        text, tokens = await _request(api_key, messages, model, temperature)
        metrics.LLM_TOKENS.inc(tokens)
        log.info("llm_call ok", extra={"outcome": "ok", "model": model, "tokens": tokens,
                                       "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
        return text, tokens
    except DeepSeekError as e:
        outcome = e.outcome
        log.warning("llm_call %s", e.outcome, extra={
            "outcome": e.outcome, "code": e.code, "model": model,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
        raise
    except Exception:
        outcome = "error"
        raise
    finally:
        metrics.LLM_REQUESTS.inc(outcome=outcome)
        metrics.LLM_DURATION.observe(time.perf_counter() - started)


async def validate_key(api_key: str) -> dict:
    text, tokens = await chat_completion(api_key, [{"role": "user", "content": "ping"}])
    return {"valid": True, "model": settings.DEEPSEEK_DEFAULT_MODEL, "tokens": tokens}


def as_api_error(e: DeepSeekError):
    status = {"DEEPSEEK_KEY_MISSING": 400, "DEEPSEEK_KEY_REJECTED": 400,
              "DEEPSEEK_UNREACHABLE": 502}.get(e.code, 502)
    return err(status, e.code, e.message)


def key_has_valid_format(api_key: str) -> bool:
    return api_key.startswith(tuple(settings.LLM_KEY_PREFIXES))

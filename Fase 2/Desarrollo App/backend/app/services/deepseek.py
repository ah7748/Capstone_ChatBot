"""Cliente real de la API de DeepSeek (chat/completions), una API key por tenant."""
import httpx

from app.core.config import settings
from app.core.errors import err


class DeepSeekError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


async def chat_completion(api_key: str, messages: list[dict],
                          model: str | None = None, temperature: float = 0.3) -> tuple[str, int]:
    """Devuelve (texto, tokens_totales). Lanza DeepSeekError en fallos."""
    if not api_key:
        raise DeepSeekError("DEEPSEEK_KEY_MISSING", "La empresa no tiene API key configurada o válida.")
    payload = {
        "model": model or settings.DEEPSEEK_DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
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
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    tokens = int(data.get("usage", {}).get("total_tokens", 0))
    return text, tokens


async def validate_key(api_key: str) -> dict:
    text, tokens = await chat_completion(api_key, [{"role": "user", "content": "ping"}])
    return {"valid": True, "model": settings.DEEPSEEK_DEFAULT_MODEL, "tokens": tokens}


def as_api_error(e: DeepSeekError):
    status = {"DEEPSEEK_KEY_MISSING": 400, "DEEPSEEK_KEY_REJECTED": 400,
              "DEEPSEEK_UNREACHABLE": 502}.get(e.code, 502)
    return err(status, e.code, e.message)

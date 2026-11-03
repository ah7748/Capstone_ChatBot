"""Cliente real de WhatsApp Business Cloud API (Meta Graph) + verificación de firma de webhooks."""
import hashlib
import hmac

import httpx

from app.core.config import settings
from app.services.secrets import SecretStore, secret_store


class MetaApiError(Exception):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(str(detail))


async def send_text(tenant_id, phone_number_id: str, to: str, text: str) -> None:
    token = secret_store.get(SecretStore.whatsapp_token_name(tenant_id))
    if not token:
        raise MetaApiError("Sin token de WhatsApp para el tenant.")
    async with httpx.AsyncClient(base_url=settings.META_GRAPH_BASE_URL, timeout=30) as client:
        r = await client.post(
            f"/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": to,
                  "type": "text", "text": {"body": text[:4096]}},
        )
        if r.status_code >= 400:
            raise MetaApiError(r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


async def verify_connection(phone_number_id: str, access_token: str) -> dict:
    """Comprueba credenciales consultando el número en la Graph API."""
    async with httpx.AsyncClient(base_url=settings.META_GRAPH_BASE_URL, timeout=30) as client:
        r = await client.get(f"/{phone_number_id}",
                             headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code >= 400:
            raise MetaApiError(r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
        return r.json()  # incluye display_phone_number


def valid_signature(body: bytes, signature_header: str | None) -> bool:
    if not settings.WHATSAPP_APP_SECRET:
        return True  # dev sin secret configurado
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)

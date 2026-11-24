"""Secretos por tenant (API keys DeepSeek, tokens de WhatsApp).

SECRETS_BACKEND=keyvault → Azure Key Vault (DefaultAzureCredential).
SECRETS_BACKEND=env      → almacén local cifrado en tabla no; en dev se guarda en un dict
                           persistido a disco (var/secrets.json). Nunca se expone por API.
"""
import json
import os
from pathlib import Path

from app.core.config import settings

_LOCAL_PATH = Path("./var/secrets.json")


class SecretStore:
    def __init__(self):
        self.backend = settings.SECRETS_BACKEND
        self._client = None

    def _kv(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            self._client = SecretClient(vault_url=settings.AZURE_KEY_VAULT_URL,
                                        credential=DefaultAzureCredential())
        return self._client

    def set(self, name: str, value: str) -> None:
        if self.backend == "keyvault":
            self._kv().set_secret(name, value)
            return
        data = {}
        if _LOCAL_PATH.exists():
            data = json.loads(_LOCAL_PATH.read_text())
        data[name] = value
        _LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_PATH.write_text(json.dumps(data))
        os.chmod(_LOCAL_PATH, 0o600)

    def get(self, name: str) -> str | None:
        if self.backend == "keyvault":
            try:
                return self._kv().get_secret(name).value
            except Exception:
                return None
        if _LOCAL_PATH.exists():
            return json.loads(_LOCAL_PATH.read_text()).get(name)
        return None

    # convenciones de nombres
    @staticmethod
    def deepseek_key_name(tenant_id) -> str:
        return f"deepseek-key-{tenant_id}"

    @staticmethod
    def whatsapp_token_name(tenant_id) -> str:
        return f"whatsapp-token-{tenant_id}"


secret_store = SecretStore()


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:7]}•••{key[-3:]}"

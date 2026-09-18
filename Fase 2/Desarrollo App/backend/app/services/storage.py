"""Almacenamiento de documentos originales: Azure Blob Storage o disco local (dev)."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings


class Storage:
    def __init__(self):
        self.backend = settings.STORAGE_BACKEND

    async def save(self, tenant_id, filename: str, data: bytes) -> str:
        path = f"{tenant_id}/{uuid.uuid4().hex}-{filename}"
        if self.backend == "azure_blob":
            from azure.storage.blob.aio import BlobServiceClient
            async with BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            ) as svc:
                blob = svc.get_blob_client(settings.AZURE_STORAGE_CONTAINER, path)
                await blob.upload_blob(data, overwrite=True)
            return path
        p = Path(settings.LOCAL_STORAGE_DIR) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return path

    async def delete(self, path: str) -> None:
        if self.backend == "azure_blob":
            from azure.storage.blob.aio import BlobServiceClient
            async with BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            ) as svc:
                blob = svc.get_blob_client(settings.AZURE_STORAGE_CONTAINER, path)
                try:
                    await blob.delete_blob()
                except Exception:
                    pass
            return
        p = Path(settings.LOCAL_STORAGE_DIR) / path
        p.unlink(missing_ok=True)

    async def download_url(self, path: str, expires_seconds: int = 300) -> str:
        """URL SAS (Azure) o URL local servida por la API en dev."""
        if self.backend == "azure_blob":
            from azure.storage.blob import BlobSasPermissions, generate_blob_sas
            from azure.storage.blob.aio import BlobServiceClient
            async with BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            ) as svc:
                sas = generate_blob_sas(
                    account_name=svc.account_name,
                    container_name=settings.AZURE_STORAGE_CONTAINER,
                    blob_name=path,
                    account_key=svc.credential.account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_seconds),
                )
                return f"https://{svc.account_name}.blob.core.windows.net/{settings.AZURE_STORAGE_CONTAINER}/{path}?{sas}"
        return f"{settings.API_BASE_URL}/local-files/{path}"


storage = Storage()

"""JWT RS256 (access + refresh + session tokens públicos) y hashing de contraseñas."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

_generated_keys: dict[str, str] = {}


def _keys() -> tuple[str, str]:
    """Claves RS256: de settings (Key Vault/env) o efímeras en dev."""
    if settings.JWT_PRIVATE_KEY_PEM and settings.JWT_PUBLIC_KEY_PEM:
        return settings.JWT_PRIVATE_KEY_PEM, settings.JWT_PUBLIC_KEY_PEM
    if not _generated_keys:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _generated_keys["priv"] = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        _generated_keys["pub"] = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
    return _generated_keys["priv"], _generated_keys["pub"]


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def check_password_policy(plain: str) -> bool:
    return (
        len(plain) >= 10
        and any(c.islower() for c in plain)
        and any(c.isupper() for c in plain)
        and any(c.isdigit() for c in plain)
    )


def _encode(claims: dict, lifetime: timedelta) -> str:
    priv, _ = _keys()
    now = datetime.now(timezone.utc)
    claims = {**claims, "iat": now, "exp": now + lifetime, "jti": uuid.uuid4().hex}
    return jwt.encode(claims, priv, algorithm="RS256")


def create_access_token(user) -> str:
    return _encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "name": user.name,
            "lang": user.lang,
            "scope": "api",
        },
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    )


def create_session_token(conversation_id, tenant_id) -> str:
    return _encode(
        {
            "sub": f"session:{conversation_id}",
            "session_id": str(conversation_id),
            "tenant_id": str(tenant_id),
            "scope": "public_chat",
        },
        timedelta(hours=settings.SESSION_TOKEN_HOURS),
    )


def decode_token(token: str) -> dict:
    _, pub = _keys()
    return jwt.decode(token, pub, algorithms=["RS256"])


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)

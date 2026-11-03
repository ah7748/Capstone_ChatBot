"""Dependencias de autenticación/autorización y paginación."""
import uuid

import jwt as pyjwt
from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import err, forbidden, unauthorized
from app.core.security import decode_token
from app.db.session import get_db
from app.models import Conversation, Tenant, User


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise unauthorized("AUTH_TOKEN_MISSING", "No se envió el token de autenticación.")
    return auth.removeprefix("Bearer ").strip()


def _decode(token: str) -> dict:
    try:
        return decode_token(token)
    except pyjwt.ExpiredSignatureError:
        raise unauthorized("AUTH_TOKEN_EXPIRED", "El access token expiró; use /auth/refresh.")
    except pyjwt.PyJWTError:
        raise unauthorized("AUTH_TOKEN_INVALID", "El token es inválido o está mal formado.")


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    claims = _decode(_bearer(request))
    if claims.get("scope") != "api":
        raise unauthorized("AUTH_TOKEN_INVALID", "El token es inválido para esta API.")
    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.status != "active":
        raise unauthorized("AUTH_TOKEN_INVALID", "El usuario del token no está activo.")
    return user


def require_role(*roles: str):
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden()
        return user
    return dep


platform_admin = require_role("platform_admin")
company_admin = require_role("company_admin")
human_agent = require_role("human_agent")


async def get_tenant(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Tenant:
    tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
    if tenant is None:
        raise forbidden("TENANT_MISMATCH", "El recurso pertenece a otro tenant.")
    if tenant.status == "disabled":
        raise forbidden("TENANT_MISMATCH", "La empresa está desactivada.")
    return tenant


async def get_public_session(request: Request, db: AsyncSession = Depends(get_db)) -> Conversation:
    """Session token del chat público: autoriza solo la sesión propia."""
    claims = _decode(_bearer(request))
    if claims.get("scope") != "public_chat":
        raise unauthorized("AUTH_TOKEN_INVALID", "El token no es un session token de chat.")
    session_id = request.path_params.get("session_id")
    if session_id and str(session_id) != claims.get("session_id"):
        raise forbidden("TENANT_MISMATCH", "El token no corresponde a esta sesión.")
    convo = await db.get(Conversation, uuid.UUID(claims["session_id"]))
    if convo is None:
        raise unauthorized("SESSION_EXPIRED", "La sesión expiró; crear una nueva.")
    return convo


class Page:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size

    def wrap(self, items: list, total: int) -> dict:
        return {"items": items, "page": self.page, "page_size": self.page_size, "total": total}


PERIODS = {"today", "7d", "30d", "prev_month", "3m", "year"}


def validate_period(period: str) -> str:
    if period not in PERIODS:
        raise err(422, "PERIOD_INVALID", "El período no es uno de los valores admitidos.",
                  {"allowed": sorted(PERIODS)})
    return period

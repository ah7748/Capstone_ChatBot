"""Sección 6 — Autenticación."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import conflict, err, forbidden, unauthorized, unprocessable
from app.core.security import (
    check_password_policy, create_access_token, hash_password, new_opaque_token, verify_password,
)
from app.db.session import get_db
from app.models import RefreshToken, Tenant, User, now
from app.schemas.auth import (
    InviteAcceptIn, LoginIn, LogoutIn, MeOut, RefreshIn, ResetConfirmIn, ResetRequestIn, TokenPair, UserOut,
)
from app.services.ratelimit import allow

router = APIRouter(prefix="/auth", tags=["auth"])

PERMISSIONS = {
    "platform_admin": ["platform:*"],
    "company_admin": ["company:*"],
    "human_agent": ["agent:*"],
}


async def _issue_pair(db: AsyncSession, user: User, family: str | None = None) -> dict:
    token = new_opaque_token()
    db.add(RefreshToken(
        user_id=user.id, token=token, family=family or uuid.uuid4().hex,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    ))
    await db.flush()
    return {
        "access_token": create_access_token(user),
        "expires_in": settings.ACCESS_TOKEN_MINUTES * 60,
        "refresh_token": token,
    }


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        # solo los intentos fallidos consumen el presupuesto (5 por 15 min por email)
        if not await allow(f"loginfail:{body.email.lower()}", 5, 900):
            raise err(429, "AUTH_TOO_MANY_ATTEMPTS", "Demasiados intentos fallidos; reintente más tarde.")
        raise unauthorized("AUTH_INVALID_CREDENTIALS", "Email o contraseña incorrectos.")
    if user.status != "active":
        raise forbidden("AUTH_USER_DISABLED", "La cuenta está deshabilitada.")
    if user.tenant_id:
        tenant = await db.get(Tenant, user.tenant_id)
        if tenant and tenant.status == "disabled":
            raise forbidden("AUTH_USER_DISABLED", "La empresa está desactivada.")
    pair = await _issue_pair(db, user)
    await db.commit()
    return {**pair, "user": UserOut.model_validate(user, from_attributes=True)}


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    rt = (await db.execute(select(RefreshToken).where(RefreshToken.token == body.refresh_token))).scalar_one_or_none()
    if rt is None or rt.revoked:
        raise unauthorized("AUTH_REFRESH_INVALID", "El refresh token no existe o fue revocado.")
    if rt.rotated:
        # reutilización: revocar toda la familia
        await db.execute(update(RefreshToken).where(RefreshToken.family == rt.family)
                         .values(revoked=True))
        await db.commit()
        raise unauthorized("AUTH_REFRESH_REUSED", "Reutilización detectada; sesión revocada por seguridad.")
    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized("AUTH_REFRESH_EXPIRED", "El refresh token expiró; se requiere login.")
    user = await db.get(User, rt.user_id)
    if user is None or user.status != "active":
        raise unauthorized("AUTH_REFRESH_INVALID", "El usuario ya no está activo.")
    rt.rotated = True
    pair = await _issue_pair(db, user, family=rt.family)
    await db.commit()
    return pair


@router.post("/logout", status_code=204)
async def logout(body: LogoutIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if body.all_sessions:
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    else:
        await db.execute(update(RefreshToken).where(RefreshToken.token == body.refresh_token,
                                                    RefreshToken.user_id == user.id).values(revoked=True))
    await db.commit()


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
    out = MeOut.model_validate(user, from_attributes=True)
    out.tenant_name = tenant.name if tenant else None
    out.permissions = PERMISSIONS.get(user.role, [])
    return out


@router.post("/invitations/accept")
async def accept_invitation(body: InviteAcceptIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.invitation_token == body.invitation_token))).scalar_one_or_none()
    if user is None:
        raise err(400, "INVITE_INVALID", "La invitación no existe o fue revocada.")
    if user.status == "active":
        raise conflict("INVITE_ALREADY_USED", "La cuenta ya fue activada.")
    if user.invitation_expires_at and user.invitation_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise err(410, "INVITE_EXPIRED", "La invitación expiró; el administrador debe reenviarla.")
    if not check_password_policy(body.password):
        raise unprocessable("PASSWORD_WEAK", "La contraseña no cumple la política (10+, mayúscula, minúscula y número).")
    user.password_hash = hash_password(body.password)
    if body.name:
        user.name = body.name
    user.status = "active"
    user.invitation_token = None
    await db.commit()
    return {"activated": True, "email": user.email}


@router.post("/password/reset-request")
async def reset_request(body: ResetRequestIn, db: AsyncSession = Depends(get_db)):
    if not await allow(f"reset:{body.email.lower()}", 3, 3600):
        raise err(429, "RESET_RATE_LIMIT", "Máximo 3 solicitudes por hora.")
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is not None:
        user.reset_token = new_opaque_token()
        user.reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()
        # el envío de email queda a cargo del servicio de notificaciones (Azure Communication Services)
    return {"sent": True}


@router.post("/password/reset-confirm")
async def reset_confirm(body: ResetConfirmIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.reset_token == body.reset_token))).scalar_one_or_none()
    if user is None:
        raise err(400, "RESET_INVALID", "Token inexistente o ya usado.")
    if user.reset_expires_at and user.reset_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise err(410, "RESET_EXPIRED", "El token expiró (1 hora).")
    if not check_password_policy(body.new_password):
        raise unprocessable("PASSWORD_WEAK", "La contraseña no cumple la política.")
    user.password_hash = hash_password(body.new_password)
    user.reset_token = None
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    await db.commit()
    return {"reset": True}

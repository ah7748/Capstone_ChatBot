import argparse
import asyncio
import sys
import uuid
 
from sqlalchemy import select
 
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import BotAgent, Tenant, User

def _need(name: str) -> str:
    value = getattr(settings, name)
    if not value:
        sys.exit(f"Falta la variable {name}: defínela en el entorno o en el archivo .env")
    return value

async def _hay_superadmin(db) -> bool:
    row = await db.execute(select(User.id).where(User.role == "platform_admin").limit(1))
    return row.first() is not None

async def _ensure_user(db, *, email: str, **fields) -> bool:
    email = email.lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        return False
    db.add(User(email=email, **fields))
    return True

async def seed_superadmin(db) -> bool:
    if await _hay_superadmin(db) and not (settings.SUPERADMIN_EMAIL and settings.SUPERADMIN_PASSWORD):
        return "omitido"
    creado = await _ensure_user(
        db,
        email=_need("SUPERADMIN_EMAIL"),
        name=settings.SUPERADMIN_NAME,
        password_hash=hash_password(_need("SUPERADMIN_PASSWORD")),
        role="platform_admin", tenant_id=None, lang="es", status="active",
    )
    return "creado" if creado else "ya existía"

async def seed_demo(db) -> list[str]:
    #Empresa demo con sus usuarios y agentes del bot. Solo para dev/test.
    if settings.APP_ENV not in ("dev", "test"):
        sys.exit("--demo solo se permite con APP_ENV=dev o test")
    pwd = hash_password(_need("DEMO_PASSWORD"))
    creados = []
 
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == settings.DEMO_TENANT_SLUG))).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(), name=settings.DEMO_TENANT_NAME, slug=settings.DEMO_TENANT_SLUG,
            legal_name=f"{settings.DEMO_TENANT_NAME} SpA", tax_id="12345678-9", country="CL",
            language="es", languages=["es"], status="active",
            token_limit_month=settings.DEFAULT_TOKEN_LIMIT_MONTH,
        )
        db.add(tenant)
        await db.flush()
        creados.append(f"empresa {tenant.slug}")
 
    if await _ensure_user(db, email=_need("DEMO_COMPANY_ADMIN_EMAIL"), name="Admin Empresa",
                          password_hash=pwd, role="company_admin", tenant_id=tenant.id,
                          lang="es", status="active"):
        creados.append("admin de empresa")
    if await _ensure_user(db, email=_need("DEMO_AGENT_EMAIL"), name="Trabajador Consola",
                          password_hash=pwd, role="human_agent", tenant_id=tenant.id,
                          lang="es", status="active", escalation_type="both",
                          channel="web", presence="available"):
        creados.append("agente humano")
 
    for tipo, nombre, activo in (("technical", "Soporte Técnico", True),
                                 ("commercial", "Soporte Comercial", False)):
        existe = (await db.execute(select(BotAgent).where(
            BotAgent.tenant_id == tenant.id, BotAgent.agent_type == tipo))).scalar_one_or_none()
        if not existe:
            db.add(BotAgent(tenant_id=tenant.id, agent_type=tipo, enabled=activo,
                            display_name=f"{nombre} {tenant.name}",
                            system_prompt=f"Eres el {nombre.lower()} de {tenant.name}."))
            creados.append(f"agente bot {tipo}")
    return creados

async def cmd_seed(demo: bool) -> None:
    async with SessionLocal() as db:
        estado = await seed_superadmin(db)
        if estado == "omitido":
            print("[seed] superadmin: ya existe uno; no se requieren SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD")
        else:
            print(f"[seed] superadmin {settings.SUPERADMIN_EMAIL.lower()}: {estado}")
        if demo:
            nuevos = await seed_demo(db)
            print(f"[seed] demo: {', '.join(nuevos) if nuevos else 'ya existía todo'}")
        await db.commit()

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("seed", help="crea el superadmin y los datos base (repetible)")
    p.add_argument("--demo", action="store_true", help="crea también la empresa demo (solo dev/test)")
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(cmd_seed(args.demo))
 
 
if __name__ == "__main__":
    main()
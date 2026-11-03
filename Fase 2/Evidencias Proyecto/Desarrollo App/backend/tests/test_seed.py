#RF-BE-07

import uuid
 
import pytest
from sqlalchemy import func, select
 
from app import cli
from app.core.config import settings
from app.core.security import verify_password
from app.db.session import SessionLocal
from app.models import BotAgent, Tenant, User
 
pytestmark = pytest.mark.asyncio
 
 
@pytest.fixture
def cfg(monkeypatch):
    u = uuid.uuid4().hex[:8]
    valores = {
        "SUPERADMIN_EMAIL": f"root-{u}@example.com", "SUPERADMIN_PASSWORD": "Clave-Super-1",
        "DEMO_PASSWORD": "Clave-Demo-1", "DEMO_TENANT_SLUG": f"demo-{u}",
        "DEMO_COMPANY_ADMIN_EMAIL": f"admin-{u}@example.com", "DEMO_AGENT_EMAIL": f"agente-{u}@example.com",
    }
    for k, v in valores.items():
        monkeypatch.setattr(settings, k, v)
    return valores
 
 
async def _count(model, *where):
    async with SessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar()
 
 
async def test_seed_crea_el_superadmin_con_valores_del_entorno(cfg):
    await cli.cmd_seed(demo=False)
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == cfg["SUPERADMIN_EMAIL"]))).scalar_one()
    assert u.role == "platform_admin" and u.tenant_id is None and u.status == "active"
    assert verify_password(cfg["SUPERADMIN_PASSWORD"], u.password_hash)
 
 
async def test_seed_guarda_el_correo_en_minusculas(cfg, monkeypatch):
    monkeypatch.setattr(settings, "SUPERADMIN_EMAIL", cfg["SUPERADMIN_EMAIL"].upper())
    await cli.cmd_seed(demo=False)
    assert await _count(User, User.email == cfg["SUPERADMIN_EMAIL"]) == 1
 
 
async def test_seed_es_repetible_y_no_pisa_la_clave(cfg):
    await cli.cmd_seed(demo=True)
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == cfg["SUPERADMIN_EMAIL"]))).scalar_one()
        u.password_hash = "cambiada-por-el-usuario"
        await db.commit()
    await cli.cmd_seed(demo=True)                       # segunda ejecución
    assert await _count(User, User.email == cfg["SUPERADMIN_EMAIL"]) == 1
    assert await _count(Tenant, Tenant.slug == cfg["DEMO_TENANT_SLUG"]) == 1
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == cfg["SUPERADMIN_EMAIL"]))).scalar_one()
        tid = (await db.execute(select(Tenant.id).where(Tenant.slug == cfg["DEMO_TENANT_SLUG"]))).scalar_one()
    assert u.password_hash == "cambiada-por-el-usuario"
    assert await _count(BotAgent, BotAgent.tenant_id == tid) == 2
 
 
async def test_seed_falla_si_no_hay_superadmin_y_faltan_las_variables(cfg, monkeypatch):
    async def sin_superadmin(db):
        return False
 
    monkeypatch.setattr(cli, "_hay_superadmin", sin_superadmin)
    monkeypatch.setattr(settings, "SUPERADMIN_PASSWORD", "")
    with pytest.raises(SystemExit):
        await cli.cmd_seed(demo=False)
 
 
async def test_seed_no_exige_variables_si_ya_existe_un_superadmin(cfg, monkeypatch):
    # la suite ya crea un platform_admin (conftest), así que ya "hay superadmin"
    assert await _count(User, User.role == "platform_admin") >= 1
    antes = await _count(User)
    monkeypatch.setattr(settings, "SUPERADMIN_EMAIL", "")
    monkeypatch.setattr(settings, "SUPERADMIN_PASSWORD", "")
    await cli.cmd_seed(demo=False)                      # no debe terminar con SystemExit
    assert await _count(User) == antes                  # y no crea nada
 
 
async def test_demo_esta_prohibido_en_produccion(cfg, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    with pytest.raises(SystemExit):
        await cli.cmd_seed(demo=True)
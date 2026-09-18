"""Fixtures: BD SQLite en memoria (aiosqlite), app con dependencias reales y datos semilla."""
import asyncio
import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./var/test.db")
os.environ.setdefault("WORKERS_INLINE", "true")
os.environ.setdefault("EMBEDDINGS_BACKEND", "hash")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("SECRETS_BACKEND", "env")
os.environ.setdefault("LOCAL_STORAGE_DIR", "./var/test-storage")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.models import BotAgent, Tenant, User


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    if os.path.exists("./var/test.db"):
        os.remove("./var/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(scope="session")
async def seed():
    async with SessionLocal() as db:
        platform = User(name="Root", email="root@alloxentric.com", role="platform_admin",
                        password_hash=hash_password("Password123!"), status="active")
        tenant = Tenant(name="WellQ", slug="wellq", legal_name="WellQ Health Ltd.",
                        tax_id="GB 14523870", country="GB", language="es",
                        languages=["es", "en"], status="active",
                        deepseek_key_status="unvalidated")
        db.add_all([platform, tenant])
        await db.flush()
        admin = User(tenant_id=tenant.id, name="Max", email="max@wellq.co.uk",
                     role="company_admin", password_hash=hash_password("Password123!"),
                     status="active")
        agent = User(tenant_id=tenant.id, name="Sofía Andrade", email="sofia@wellq.co.uk",
                     role="human_agent", password_hash=hash_password("Password123!"),
                     status="active", escalation_type="both", channel="web",
                     presence="available")
        db.add_all([
            admin, agent,
            BotAgent(tenant_id=tenant.id, agent_type="technical", enabled=True,
                     display_name="Asistente WellQ · Técnico"),
            BotAgent(tenant_id=tenant.id, agent_type="commercial", enabled=True,
                     display_name="Asistente WellQ · Comercial"),
        ])
        await db.commit()
        return {"tenant_id": str(tenant.id)}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client, email, password="Password123!"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data

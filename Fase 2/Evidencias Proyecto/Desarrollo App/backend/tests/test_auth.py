import pytest

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_login_ok(client, seed):
    headers, data = await login(client, "max@wellq.co.uk")
    assert data["user"]["role"] == "company_admin"
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["tenant_name"] == "WellQ"


async def test_login_bad_credentials(client, seed):
    r = await client.post("/api/v1/auth/login",
                          json={"email": "max@wellq.co.uk", "password": "malamala1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_refresh_rotation_and_reuse(client, seed):
    _, data = await login(client, "max@wellq.co.uk")
    rt = data["refresh_token"]
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    # reutilizar el token ya rotado revoca la familia
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "AUTH_REFRESH_REUSED"
    r3 = await client.post("/api/v1/auth/refresh",
                           json={"refresh_token": r1.json()["refresh_token"]})
    assert r3.status_code == 401


async def test_role_forbidden(client, seed):
    headers, _ = await login(client, "max@wellq.co.uk")
    r = await client.get("/api/v1/platform/tenants", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN_ROLE"


async def test_missing_token(client, seed):
    r = await client.get("/api/v1/company/dashboard")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

import pytest

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_create_tenant_and_duplicates(client, seed):
    headers, _ = await login(client, "root@alloxentric.com")
    body = {"name": "Directa", "slug": "directa", "legal_name": "Directa SpA",
            "tax_id": "77.123.456-7", "country": "cl", "language": "es",
            "admin_email": "admin@directa.cl", "deepseek_api_key": "sk-test-directa-123"}
    r = await client.post("/api/v1/platform/tenants", json=body, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["chat_url"] == "soporte.allox.ai/directa"

    r2 = await client.post("/api/v1/platform/tenants", json=body, headers=headers)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "TENANT_SLUG_TAKEN"

    bad = {**body, "slug": "directa2", "admin_email": "otro@directa.cl",
           "deepseek_api_key": "no-formato"}
    r3 = await client.post("/api/v1/platform/tenants", json=bad, headers=headers)
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "DEEPSEEK_KEY_INVALID_FORMAT"


async def test_tenant_detail_and_usage(client, seed):
    headers, _ = await login(client, "root@alloxentric.com")
    r = await client.get("/api/v1/platform/tenants", headers=headers)
    tenant_id = r.json()["items"][0]["tenant_id"]
    d = await client.get(f"/api/v1/platform/tenants/{tenant_id}", headers=headers)
    assert d.status_code == 200
    assert d.json()["tenant"]["legal_name"]
    u = await client.get(f"/api/v1/platform/tenants/{tenant_id}/usage?period=7d", headers=headers)
    assert u.status_code == 200
    bad = await client.get(f"/api/v1/platform/tenants/{tenant_id}/usage?period=nope", headers=headers)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "PERIOD_INVALID"


async def test_dashboard(client, seed):
    headers, _ = await login(client, "root@alloxentric.com")
    r = await client.get("/api/v1/platform/dashboard?period=7d", headers=headers)
    assert r.status_code == 200
    assert "kpis" in r.json()

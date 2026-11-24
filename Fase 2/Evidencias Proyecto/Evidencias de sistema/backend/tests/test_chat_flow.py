"""Flujo de punta a punta: sesión pública → mensaje → derivación → consola de agente.
El LLM no está disponible en tests, así que el envío de mensaje del bot devuelve 400/502
(DEEPSEEK_KEY_MISSING) — se prueba el manejo del error y el flujo de derivación explícita."""
import pytest

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _create_session(client):
    r = await client.post("/api/v1/public/chat/wellq/sessions",
                          json={"lang": "es", "user": {"name": "María González"}})
    assert r.status_code == 201, r.text
    return r.json()


async def test_public_config_and_session(client, seed):
    cfg = await client.get("/api/v1/public/chat/wellq/config")
    assert cfg.status_code == 200
    assert cfg.json()["bot_name"]

    missing = await client.get("/api/v1/public/chat/noexiste/config")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TENANT_NOT_FOUND"

    data = await _create_session(client)
    assert data["session_token"]
    sid = data["session_id"]
    token = {"Authorization": f"Bearer {data['session_token']}"}

    hist = await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)
    assert hist.status_code == 200
    assert hist.json()["messages"][0]["role"] == "bot"  # bienvenida

    # sin API key de DeepSeek configurada → error controlado
    msg = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                            json={"content": "No puedo subir mi examen"}, headers=token)
    assert msg.status_code == 400
    assert msg.json()["error"]["code"] == "DEEPSEEK_KEY_MISSING"


async def test_escalation_to_live_and_agent_console(client, seed):
    data = await _create_session(client)
    sid = data["session_id"]
    token = {"Authorization": f"Bearer {data['session_token']}"}

    esc = await client.post(f"/api/v1/public/chat/sessions/{sid}/escalate",
                            json={"reason": "Quiero hablar con una persona"}, headers=token)
    assert esc.status_code == 200
    assert esc.json()["mode"] == "live"  # Sofía está available

    again = await client.post(f"/api/v1/public/chat/sessions/{sid}/escalate",
                              json={}, headers=token)
    assert again.status_code == 409

    # consola del agente
    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    q = await client.get("/api/v1/agent/queue?type=live", headers=agent_headers)
    assert q.status_code == 200
    ids = [i["conversation_id"] for i in q.json()["items"]]
    assert sid in ids

    claim = await client.post(f"/api/v1/agent/conversations/{sid}/claim", headers=agent_headers)
    assert claim.status_code == 200
    claim2 = await client.post(f"/api/v1/agent/conversations/{sid}/claim", headers=agent_headers)
    assert claim2.status_code == 409  # ya reclamada

    reply = await client.post(f"/api/v1/agent/conversations/{sid}/messages",
                              json={"content": "Hola María, reviso tu caso."}, headers=agent_headers)
    assert reply.status_code == 201

    # el usuario ve el mensaje del agente
    hist = await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)
    roles = [m["role"] for m in hist.json()["messages"]]
    assert "agent" in roles

    resolve = await client.post(f"/api/v1/agent/conversations/{sid}/resolve",
                                json={}, headers=agent_headers)
    assert resolve.status_code == 200

    rate = await client.post(f"/api/v1/public/chat/sessions/{sid}/rating",
                             json={"rating": "up"}, headers=token)
    assert rate.status_code == 201
    rate2 = await client.post(f"/api/v1/public/chat/sessions/{sid}/rating",
                              json={"rating": "up"}, headers=token)
    assert rate2.status_code == 409


async def test_escalation_to_ticket_when_no_agent(client, seed):
    # poner a Sofía offline → la derivación crea ticket
    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    await client.patch("/api/v1/agent/presence", json={"presence": "offline"},
                       headers=agent_headers)
    data = await _create_session(client)
    sid = data["session_id"]
    token = {"Authorization": f"Bearer {data['session_token']}"}
    esc = await client.post(f"/api/v1/public/chat/sessions/{sid}/escalate", json={}, headers=token)
    assert esc.status_code == 200
    assert esc.json()["mode"] == "ticket"
    assert esc.json()["ticket_number"].startswith("T-")

    q = await client.get("/api/v1/agent/queue?type=tickets", headers=agent_headers)
    assert any(t["conversation_id"] == sid for t in q.json()["items"])
    ticket_id = [t for t in q.json()["items"] if t["conversation_id"] == sid][0]["ticket_id"]

    take = await client.patch(f"/api/v1/agent/tickets/{ticket_id}",
                              json={"assign_to_me": True, "status": "pending"},
                              headers=agent_headers)
    assert take.status_code == 200
    # dejarla disponible de nuevo para otros tests
    await client.patch("/api/v1/agent/presence", json={"presence": "available"},
                       headers=agent_headers)


async def test_company_dashboard_and_human_agents(client, seed):
    headers, _ = await login(client, "max@wellq.co.uk")
    d = await client.get("/api/v1/company/dashboard?period=7d", headers=headers)
    assert d.status_code == 200
    assert "pending_tickets" in d.json()["kpis"]

    det = await client.get("/api/v1/company/dashboard/detail?metric=escalations", headers=headers)
    assert det.status_code == 200
    bad = await client.get("/api/v1/company/dashboard/detail?metric=nope", headers=headers)
    assert bad.status_code == 422

    # CRUD agente humano
    r = await client.post("/api/v1/company/human-agents", headers=headers, json={
        "name": "Diego Pardo", "email": "diego@wellq.co.uk",
        "escalation_type": "commercial", "channel": "web"})
    assert r.status_code == 201
    agent_id = r.json()["agent_id"]
    upd = await client.patch(f"/api/v1/company/human-agents/{agent_id}", headers=headers,
                             json={"escalation_type": "both"})
    assert upd.status_code == 200
    dele = await client.delete(f"/api/v1/company/human-agents/{agent_id}?confirm=true",
                               headers=headers)
    assert dele.status_code == 200


async def test_tenant_isolation(client, seed):
    """Un admin de otra empresa no puede ver documentos de WellQ."""
    root, _ = await login(client, "root@alloxentric.com")
    await client.post("/api/v1/platform/tenants", headers=root, json={
        "name": "Dani27001", "slug": "dani27001", "legal_name": "Dani Compliance SpA",
        "tax_id": "76.888.999-1", "country": "cl", "language": "es",
        "admin_email": "admin@dani27001.cl", "deepseek_api_key": "sk-test-dani"})
    # activar la cuenta invitada directamente en BD
    from app.db.session import SessionLocal
    from app.core.security import hash_password
    from sqlalchemy import select
    from app.models import User
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == "admin@dani27001.cl"))).scalar_one()
        u.password_hash = hash_password("Password123!")
        u.status = "active"
        await db.commit()
    dani_headers, _ = await login(client, "admin@dani27001.cl")
    docs = await client.get("/api/v1/company/documents", headers=dani_headers)
    assert docs.status_code == 200
    assert docs.json()["total"] == 0  # no ve los documentos de WellQ

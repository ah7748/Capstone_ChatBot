"""Derivación a humano: detección de la petición del usuario, mensajes del agente y estado de sesión."""
import pytest

from app.api.v1 import agent_console
from app.services.escalation import wants_human
from tests.conftest import login


@pytest.mark.parametrize("texto", [
    "quiero hablar con un agente", "necesito hablar con un agente", "Quiero hablar con una persona",
    "quisiera hablar con un humano", "me pueden comunicar con un asesor?", "pasame con un ejecutivo",
    "agente humano por favor", "quiero un agente", "I want to talk to a human",
    "can I speak with an agent", "quero falar com uma pessoa", "necesito ayuda humana",
])
def test_detecta_la_peticion_de_hablar_con_una_persona(texto):
    assert wants_human(texto)


@pytest.mark.parametrize("texto", [
    "¿Cómo restablezco mi contraseña?", "el agente de soporte me dijo que reiniciara",
    "cuál es el horario de atención", "necesito cambiar mi plan", "mi persona de contacto es Juan",
    "quiero cancelar mi suscripción", "how do I reset my password", "pasa algo con mi cuenta",
    "x" * 400 + " quiero hablar con un agente",
])
def test_no_confunde_consultas_normales_con_una_derivacion(texto):
    assert not wants_human(texto)


async def _session(client):
    r = await client.post("/api/v1/public/chat/wellq/sessions", json={"lang": "es", "user": {"name": "Ana"}})
    assert r.status_code == 201, r.text
    d = r.json()
    return d["session_id"], {"Authorization": f"Bearer {d['session_token']}"}


async def test_escribir_quiero_hablar_con_un_agente_deriva_sin_usar_el_modelo(client, seed):
    sid, token = await _session(client)
    # sin clave de IA configurada: si pasara por el modelo daría 400 DEEPSEEK_KEY_MISSING
    r = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                          json={"content": "quiero hablar con un agente"}, headers=token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalation"]["mode"] == "live"
    assert "persona" in body["bot_reply"]["content"]

    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    q = await client.get("/api/v1/agent/queue?type=live", headers=agent_headers)
    assert sid in [i["conversation_id"] for i in q.json()["items"]]

    # ya derivada: los siguientes mensajes van al agente, no al bot
    r2 = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                           json={"content": "sigo aquí"}, headers=token)
    assert r2.status_code == 200 and r2.json()["bot_reply"] is None


async def test_la_peticion_crea_ticket_si_no_hay_agentes(client, seed):
    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    await client.patch("/api/v1/agent/presence", json={"presence": "offline"}, headers=agent_headers)
    try:
        sid, token = await _session(client)
        r = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                              json={"content": "necesito hablar con un agente"}, headers=token)
        assert r.status_code == 200
        assert r.json()["escalation"]["mode"] == "ticket"
        assert "ticket" in r.json()["bot_reply"]["content"]
    finally:
        await client.patch("/api/v1/agent/presence", json={"presence": "available"}, headers=agent_headers)


async def test_el_evento_del_agente_lleva_message_id_y_el_get_informa_el_estado(client, seed, monkeypatch):
    eventos = []

    async def captura(session_id, payload):
        eventos.append(payload)

    monkeypatch.setattr(agent_console, "publish_session_event", captura)

    sid, token = await _session(client)
    await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                      json={"content": "quiero hablar con una persona"}, headers=token)
    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    await client.post(f"/api/v1/agent/conversations/{sid}/claim", headers=agent_headers)
    r = await client.post(f"/api/v1/agent/conversations/{sid}/messages",
                          json={"content": "Hola Ana, te ayudo."}, headers=agent_headers)
    assert r.status_code == 201

    ev = next(e for e in eventos if e["event"] == "message.agent")
    assert ev["data"]["message_id"] == r.json()["message_id"]

    hist = (await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)).json()
    assert hist["status"] == "live"
    assert any(m["role"] == "agent" and m["message_id"] == r.json()["message_id"] for m in hist["messages"])

    await client.post(f"/api/v1/agent/conversations/{sid}/resolve", json={}, headers=agent_headers)
    hist = (await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)).json()
    assert hist["status"] == "resolved"

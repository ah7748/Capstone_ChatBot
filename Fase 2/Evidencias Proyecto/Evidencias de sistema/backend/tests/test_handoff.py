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


# ------------------------------------------------------------------ cierre de la conversación por el bot
@pytest.mark.parametrize("texto", [
    "quiero cerrar la conversacion", "eso es todo", "nada más, gracias", "ya no necesito nada más",
    "mi problema ya se resolvió", "el problema quedó resuelto", "ya funciona, gracias", "listo, terminemos el chat",
    "adiós", "that's all", "close the chat", "no tengo más dudas", "quero encerrar a conversa",
])
def test_detecta_cuando_el_usuario_da_por_terminada_la_conversacion(texto):
    from app.services.escalation import wants_close
    assert wants_close(texto)


@pytest.mark.parametrize("texto", [
    "gracias", "hola", "¿Cómo restablezco mi contraseña?", "no puedo cerrar la sesión", "quiero cerrar mi cuenta",
    "mi problema no se resolvió", "aún no se resuelve mi problema", "no quiero cerrar la conversación",
    "necesito más ayuda", "quiero hablar con un agente", "x" * 200 + " eso es todo",
])
def test_no_cierra_por_frases_que_no_lo_piden(texto):
    from app.services.escalation import wants_close
    assert not wants_close(texto)


async def test_el_bot_cierra_la_conversacion_y_permite_valorar(client, seed):
    sid, token = await _session(client)
    r = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                          json={"content": "quiero cerrar la conversacion"}, headers=token)
    assert r.status_code == 200, r.text          # sin pasar por el modelo (no hay clave en tests)
    assert r.json()["closed"] is True and "cerrada" in r.json()["bot_reply"]["content"]

    hist = (await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)).json()
    assert hist["status"] == "resolved"

    rate = await client.post(f"/api/v1/public/chat/sessions/{sid}/rating", json={"rating": "up"}, headers=token)
    assert rate.status_code == 201


async def test_si_la_atiende_una_persona_el_bot_no_cierra(client, seed):
    sid, token = await _session(client)
    await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                      json={"content": "quiero hablar con un agente"}, headers=token)
    r = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                          json={"content": "eso es todo, gracias"}, headers=token)
    assert r.status_code == 200 and r.json()["bot_reply"] is None and "closed" not in r.json()
    hist = (await client.get(f"/api/v1/public/chat/sessions/{sid}/messages", headers=token)).json()
    assert hist["status"] == "queued"


# ------------------------------------------------------------------ pedir un ticket
@pytest.mark.parametrize("texto", [
    "quiero iniciar un ticket", "deseo abrir un ticket", "necesito un ticket", "crear ticket",
    "abre un ticket por favor", "I want to open a ticket", "quero criar um ticket", "puedo abrir un ticket?",
])
def test_detecta_la_peticion_de_abrir_un_ticket(texto):
    from app.services.escalation import wants_ticket
    assert wants_ticket(texto)


@pytest.mark.parametrize("texto", [
    "¿cómo creo un ticket?", "qué es un ticket", "necesito saber el estado de mi ticket",
    "mi ticket T-1001 sigue abierto", "quiero iniciar sesión", "quiero hablar con un agente", "hola",
])
def test_no_crea_ticket_por_frases_que_no_lo_piden(texto):
    from app.services.escalation import wants_ticket
    assert not wants_ticket(texto)


async def test_pedir_un_ticket_crea_ticket_aunque_haya_agentes_en_linea(client, seed):
    agent_headers, _ = await login(client, "sofia@wellq.co.uk")
    await client.patch("/api/v1/agent/presence", json={"presence": "available"}, headers=agent_headers)
    sid, token = await _session(client)
    r = await client.post(f"/api/v1/public/chat/sessions/{sid}/messages",
                          json={"content": "quiero iniciar un ticket"}, headers=token)
    assert r.status_code == 200, r.text
    assert r.json()["escalation"]["mode"] == "ticket"          # no lo manda a un agente en vivo
    assert r.json()["escalation"]["ticket_number"].startswith("T-")
    assert "ticket" in r.json()["bot_reply"]["content"]

    q = await client.get("/api/v1/agent/queue?type=tickets", headers=agent_headers)
    assert sid in [t["conversation_id"] for t in q.json()["items"]]
    live = await client.get("/api/v1/agent/queue?type=live", headers=agent_headers)
    assert sid not in [c["conversation_id"] for c in live.json()["items"]]

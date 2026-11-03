"""Hash de tokens, texto plano del bot, prompt por defecto y sesión cerrada."""
import pytest
from sqlalchemy import select

from app.core.security import hash_token, new_opaque_token
from app.services.prompts import STYLE_RULES, default_agent_prompt, plain_text
from tests.conftest import login


def test_hash_token_es_determinista_y_no_reversible():
    t = new_opaque_token()
    assert hash_token(t) == hash_token(t)
    assert hash_token(t) != t and len(hash_token(t)) == 64
    assert hash_token(t) != hash_token(new_opaque_token())


@pytest.mark.parametrize("entrada,esperado", [
    ("**Hola** mundo", "Hola mundo"),
    ("## Título\ntexto", "Título\ntexto"),
    ("* uno\n* dos", "- uno\n- dos"),
    ("usa `ajustes` ahora", "usa ajustes ahora"),
    ("ver [ayuda](https://x.com/a)", "ver ayuda (https://x.com/a)"),
    ("texto normal sin formato", "texto normal sin formato"),
    ("2 * 3 = 6", "2 * 3 = 6"),
])
def test_plain_text_quita_markdown(entrada, esperado):
    assert plain_text(entrada) == esperado


def test_prompt_por_defecto_segun_tipo():
    assert "soporte técnico de Acme" in default_agent_prompt("Acme", "support")
    assert "comercial de Acme" in default_agent_prompt("Acme", "commercial")
    assert "Markdown" in STYLE_RULES


async def test_el_refresh_token_se_guarda_hasheado(client, seed):
    from app.db.session import SessionLocal
    from app.models import RefreshToken

    _, data = await login(client, "sofia@wellq.co.uk")
    raw = data["refresh_token"]
    async with SessionLocal() as s:
        stored = (await s.execute(select(RefreshToken.token))).scalars().all()
    assert raw not in stored and hash_token(raw) in stored
    ok = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert ok.status_code == 200, ok.text


async def test_sesion_cerrada_no_acepta_mas_mensajes(client, seed):
    r = await client.post("/api/v1/public/chat/wellq/sessions", json={"lang": "es", "user": {"name": "Ana"}})
    d = r.json()
    h = {"Authorization": f"Bearer {d['session_token']}"}
    url = f"/api/v1/public/chat/sessions/{d['session_id']}/messages"
    c = await client.post(url, json={"content": "eso es todo, gracias"}, headers=h)
    assert c.json()["closed"] is True
    again = await client.post(url, json={"content": "una pregunta más"}, headers=h)
    assert again.status_code == 409 and again.json()["error"]["code"] == "SESSION_CLOSED", again.text

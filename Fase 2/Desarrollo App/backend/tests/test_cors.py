import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio

PERMITIDO = settings.CORS_ORIGINS[0]
AJENO = "https://sitio-malicioso.example"
PUBLICA = "/api/v1/public/chat/demo/sessions"
PRIVADA = "/api/v1/auth/login"


def _preflight(origen):
    return {"Origin": origen, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type"}


async def test_el_panel_acepta_su_origen(client):
    r = await client.options(PRIVADA, headers=_preflight(PERMITIDO))
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == PERMITIDO


async def test_el_panel_rechaza_otros_origenes(client):
    r = await client.options(PRIVADA, headers=_preflight(AJENO))
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
    g = await client.get("/health", headers={"Origin": AJENO})
    assert "access-control-allow-origin" not in g.headers


async def test_el_chat_publico_acepta_cualquier_origen(client):
    r = await client.options(PUBLICA, headers=_preflight(AJENO))
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"


async def test_nunca_se_permiten_credenciales(client):
    for ruta, origen in ((PRIVADA, PERMITIDO), (PUBLICA, AJENO)):
        r = await client.options(ruta, headers=_preflight(origen))
        assert "access-control-allow-credentials" not in r.headers
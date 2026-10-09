"""RF-BE-02: los errores no controlados devuelven el formato estándar con trace_id."""
import pytest

from app.main import app

pytestmark = pytest.mark.asyncio


@app.get("/__boom")  # ruta solo para pruebas: lanza una excepción no controlada
async def _boom():
    raise RuntimeError("secreto-interno")


async def test_500_formato_estandar_con_trace_id(client, caplog):
    with caplog.at_level("ERROR", logger="app.errors"):
        r = await client.get("/__boom")
    assert r.status_code == 500
    error = r.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    trace_id = error["detail"]["trace_id"]
    assert len(trace_id) == 32
    assert r.headers["x-trace-id"] == trace_id
    # no se filtra el detalle de la excepción al cliente
    assert "secreto-interno" not in r.text
    # queda en el log con el mismo trace_id y con traceback
    registros = [rec for rec in caplog.records if trace_id in rec.getMessage()]
    assert registros and registros[0].exc_info


async def test_cada_error_tiene_un_trace_id_distinto(client):
    a = (await client.get("/__boom")).json()["error"]["detail"]["trace_id"]
    b = (await client.get("/__boom")).json()["error"]["detail"]["trace_id"]
    assert a != b


async def test_500_incluye_cabeceras_cors(client):
    r = await client.get("/__boom", headers={"Origin": "https://cliente.com"})
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == "https://cliente.com"


async def test_los_errores_controlados_no_cambian(client):
    r = await client.get("/api/v1/company/dashboard")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_TOKEN_MISSING"
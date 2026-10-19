"""RF-BE-06: observabilidad integrada en la app (request_id, /metrics, /health/ready, métricas del LLM)."""
import logging
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.observability import metrics
from app.services import deepseek
from app.services.deepseek import DeepSeekError, chat_completion


# ------------------------------------------------------------------ request_id
async def test_cada_respuesta_trae_x_request_id(client):
    r = await client.get("/health")
    assert len(r.headers["x-request-id"]) == 32


async def test_se_respeta_el_request_id_enviado_por_el_cliente(client):
    r = await client.get("/health", headers={"X-Request-ID": "front-1234-abcd"})
    assert r.headers["x-request-id"] == "front-1234-abcd"


async def test_el_trace_id_de_un_500_es_el_request_id(client):
    from tests.test_errors import _boom  # noqa: F401  (registra la ruta /__boom)
    r = await client.get("/__boom", headers={"X-Request-ID": "traza-visible-01"})
    assert r.status_code == 500
    assert r.json()["error"]["detail"]["trace_id"] == "traza-visible-01"
    assert r.headers["x-request-id"] == "traza-visible-01"


async def test_el_log_de_acceso_lleva_ruta_estado_y_duracion(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.post("/api/v1/auth/login", json={"email": "nadie@x.com", "password": "mala-clave-123"})
    rec = next(r for r in caplog.records if r.name == "app.access")
    assert rec.route.endswith("/auth/login") and rec.status in (401, 429) and rec.duration_ms >= 0
    # nunca se registran datos del cuerpo
    assert "mala-clave-123" not in " ".join(r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ /metrics
async def test_metrics_expone_las_peticiones_en_formato_prometheus(client):
    await client.get("/health")
    r = await client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "# TYPE http_requests_total counter" in r.text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in r.text
    assert "http_request_duration_seconds_bucket" in r.text


async def test_metrics_exige_el_token_si_esta_configurado(client, monkeypatch):
    monkeypatch.setattr(settings, "METRICS_TOKEN", "t0ken-secreto")
    assert (await client.get("/metrics")).status_code == 401
    assert (await client.get("/metrics", headers={"Authorization": "Bearer otro"})).status_code == 401
    ok = await client.get("/metrics", headers={"Authorization": "Bearer t0ken-secreto"})
    assert ok.status_code == 200


async def test_metrics_esta_deshabilitado_en_produccion_sin_token(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    assert (await client.get("/metrics")).status_code == 404


# ------------------------------------------------------------------ /health/ready
async def test_readiness_confirma_la_base_de_datos(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] in ("ok", "fallback_memory")


async def test_readiness_responde_503_si_la_base_falla(client, monkeypatch):
    from app.api import ops

    class _Caida:
        async def __aenter__(self):
            raise ConnectionError("db caída")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ops, "SessionLocal", lambda: _Caida())
    r = await client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "unavailable"
    assert "db caída" not in r.text                      # no se filtra el detalle del error


async def test_health_sigue_siendo_liveness_simple(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


# ------------------------------------------------------------------ métricas del proveedor de IA
def _con_respuesta(monkeypatch, status=200, json_body=None, excepcion=None):
    """Reemplaza httpx dentro de deepseek por un transporte simulado (sin red)."""
    real = httpx.AsyncClient

    def handler(request):
        if excepcion:
            raise excepcion
        return httpx.Response(status, json=json_body)

    def factory(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(deepseek, "httpx", SimpleNamespace(AsyncClient=factory, HTTPError=httpx.HTTPError))


OK = {"choices": [{"message": {"content": "hola"}}], "usage": {"total_tokens": 7}}


async def test_una_llamada_exitosa_cuenta_resultado_tokens_y_duracion(monkeypatch):
    _con_respuesta(monkeypatch, json_body=OK)
    ok0, tok0, dur0 = (metrics.LLM_REQUESTS.get(outcome="ok"), metrics.LLM_TOKENS.get(),
                       metrics.LLM_DURATION.count())
    assert await chat_completion("sk-test", [{"role": "user", "content": "x"}]) == ("hola", 7)
    assert metrics.LLM_REQUESTS.get(outcome="ok") == ok0 + 1
    assert metrics.LLM_TOKENS.get() == tok0 + 7
    assert metrics.LLM_DURATION.count() == dur0 + 1


@pytest.mark.parametrize("status,outcome", [(401, "key_rejected"), (402, "key_rejected"),
                                            (410, "unreachable"), (500, "unreachable")])
async def test_los_errores_del_proveedor_se_cuentan_por_resultado(monkeypatch, status, outcome):
    _con_respuesta(monkeypatch, status=status, json_body={"error": "x"})
    antes = metrics.LLM_REQUESTS.get(outcome=outcome)
    with pytest.raises(DeepSeekError):
        await chat_completion("sk-test", [])
    assert metrics.LLM_REQUESTS.get(outcome=outcome) == antes + 1


async def test_sin_clave_se_cuenta_como_key_missing():
    antes = metrics.LLM_REQUESTS.get(outcome="key_missing")
    with pytest.raises(DeepSeekError) as e:
        await chat_completion("", [])
    assert e.value.code == "DEEPSEEK_KEY_MISSING"
    assert metrics.LLM_REQUESTS.get(outcome="key_missing") == antes + 1


async def test_un_fallo_de_red_se_cuenta_como_unreachable(monkeypatch):
    _con_respuesta(monkeypatch, excepcion=httpx.ConnectError("sin red"))
    antes = metrics.LLM_REQUESTS.get(outcome="unreachable")
    with pytest.raises(DeepSeekError) as e:
        await chat_completion("sk-test", [])
    assert e.value.code == "DEEPSEEK_UNREACHABLE"
    assert metrics.LLM_REQUESTS.get(outcome="unreachable") == antes + 1


@pytest.mark.parametrize("cuerpo", [{"sin": "choices"}, {"choices": []}, {"choices": [{"message": {}}]},
                                    {"choices": [{"message": {"content": None}}]},
                                    {"choices": [{"message": {"content": "  "}}]}])
async def test_una_respuesta_con_formato_inesperado_es_un_error_controlado(monkeypatch, cuerpo):
    _con_respuesta(monkeypatch, json_body=cuerpo)
    antes = metrics.LLM_REQUESTS.get(outcome="bad_response")
    with pytest.raises(DeepSeekError) as e:
        await chat_completion("sk-test", [])
    assert e.value.code == "DEEPSEEK_UNREACHABLE"          # el chat muestra el mensaje de "problema técnico"
    assert metrics.LLM_REQUESTS.get(outcome="bad_response") == antes + 1


async def test_el_log_del_llm_no_contiene_mensajes_ni_clave(monkeypatch, caplog):
    _con_respuesta(monkeypatch, json_body=OK)
    with caplog.at_level(logging.INFO, logger="app.llm"):
        await chat_completion("sk-clave-super-secreta", [{"role": "user", "content": "dato-privado"}])
    texto = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "sk-clave-super-secreta" not in texto and "dato-privado" not in texto
    rec = next(r for r in caplog.records if r.name == "app.llm")
    assert rec.outcome == "ok" and rec.tokens == 7 and rec.model == settings.DEEPSEEK_DEFAULT_MODEL

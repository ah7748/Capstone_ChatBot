"""RF-BE-06: núcleo de observabilidad (logs JSON, métricas, middleware ASGI, Application Insights).

No depende de la base de datos ni de FastAPI: prueba las piezas con una app ASGI de juguete.
"""
import json
import logging
import sys
from types import SimpleNamespace

import pytest

from app.observability import metrics
from app.observability.azure_monitor import setup_azure_monitor
from app.observability.logging_config import (
    JsonFormatter, TextFormatter, request_id_var, resolve_log_format, setup_logging,
)
from app.observability.middleware import ObservabilityMiddleware, normalize_path, route_label


# ------------------------------------------------------------------ logs estructurados
def _record(msg="hola", level=logging.INFO, exc_info=None, **extra):
    rec = logging.LogRecord("app.test", level, __file__, 1, msg, None, exc_info)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_el_log_json_tiene_los_campos_basicos():
    data = json.loads(JsonFormatter().format(_record("hola mundo")))
    assert data["level"] == "INFO" and data["logger"] == "app.test" and data["message"] == "hola mundo"
    assert data["ts"].endswith("+00:00")
    assert "request_id" not in data


def test_el_log_json_incluye_request_id_y_campos_extra():
    token = request_id_var.set("req-abc12345")
    try:
        data = json.loads(JsonFormatter().format(_record(status=200, route="/x", duration_ms=12.5)))
    finally:
        request_id_var.reset(token)
    assert data["request_id"] == "req-abc12345"
    assert (data["status"], data["route"], data["duration_ms"]) == (200, "/x", 12.5)


def test_el_log_json_incluye_la_excepcion():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        rec = _record("falló", level=logging.ERROR, exc_info=sys.exc_info())
    data = json.loads(JsonFormatter().format(rec))
    assert "RuntimeError: boom" in data["exception"]


def test_el_log_json_no_rompe_con_valores_no_serializables():
    data = json.loads(JsonFormatter().format(_record(objeto=object())))
    assert "objeto" in data


def test_el_formato_texto_agrega_el_request_id():
    token = request_id_var.set("req-xyz98765")
    try:
        assert TextFormatter().format(_record("hola")).endswith("[request_id=req-xyz98765]")
    finally:
        request_id_var.reset(token)


def test_resolve_log_format():
    assert resolve_log_format("auto", "prod") == "json"
    assert resolve_log_format("auto", "dev") == "text"
    assert resolve_log_format("json", "dev") == "json"
    assert resolve_log_format("raro", "prod") == "text"


def test_setup_logging_es_idempotente():
    root = logging.getLogger()
    antes = len(root.handlers)
    setup_logging("INFO", "json")
    setup_logging("INFO", "text")
    propios = [h for h in root.handlers if getattr(h, "_app_observability_handler", False)]
    assert len(propios) == 1 and len(root.handlers) <= antes + 1
    assert isinstance(propios[0].formatter, TextFormatter)


# ------------------------------------------------------------------ métricas
def test_contador_con_etiquetas_y_salida_prometheus():
    reg = metrics.Registry()
    c = metrics.Counter("pedidos_total", "Pedidos.", ("estado",), registry=reg)
    c.inc(estado="ok")
    c.inc(2, estado="ok")
    c.inc(estado="error")
    assert c.get(estado="ok") == 3 and c.get(estado="nunca") == 0
    out = reg.render()
    assert "# HELP pedidos_total Pedidos." in out and "# TYPE pedidos_total counter" in out
    assert 'pedidos_total{estado="ok"} 3' in out and 'pedidos_total{estado="error"} 1' in out


def test_contador_sin_etiquetas_se_publica_en_cero():
    reg = metrics.Registry()
    metrics.Counter("vacio_total", "Sin datos.", registry=reg)
    assert "vacio_total 0" in reg.render()


def test_las_etiquetas_se_validan_y_se_escapan():
    reg = metrics.Registry()
    c = metrics.Counter("x_total", "x", ("ruta",), registry=reg)
    with pytest.raises(ValueError):
        c.inc(otra="a")
    c.inc(ruta='a"b\\c')
    assert 'ruta="a\\"b\\\\c"' in reg.render()


def test_no_se_permiten_metricas_duplicadas():
    reg = metrics.Registry()
    metrics.Counter("dup_total", "a", registry=reg)
    with pytest.raises(ValueError):
        metrics.Counter("dup_total", "b", registry=reg)


def test_histograma_acumula_buckets_suma_y_conteo():
    reg = metrics.Registry()
    h = metrics.Histogram("dur_seconds", "d", ("ruta",), buckets=(0.1, 1.0), registry=reg)
    for v in (0.05, 0.5, 5.0):
        h.observe(v, ruta="/a")
    assert h.count(ruta="/a") == 3 and abs(h.total(ruta="/a") - 5.55) < 1e-9
    out = reg.render()
    assert 'dur_seconds_bucket{ruta="/a",le="0.1"} 1' in out
    assert 'dur_seconds_bucket{ruta="/a",le="1.0"} 2' in out
    assert 'dur_seconds_bucket{ruta="/a",le="+Inf"} 3' in out
    assert 'dur_seconds_count{ruta="/a"} 3' in out


def test_las_metricas_de_la_aplicacion_estan_registradas():
    out = metrics.render()
    for name in ("http_requests_total", "http_request_duration_seconds", "app_unhandled_exceptions_total",
                 "llm_requests_total", "llm_request_duration_seconds", "llm_tokens_total"):
        assert f"# TYPE {name} " in out


# ------------------------------------------------------------------ middleware ASGI
def test_normalize_path():
    assert normalize_path("/api/v1/faqs/123/edit") == "/api/v1/faqs/{id}/edit"
    assert normalize_path("/x/3f2b8c1e-8a5d-4e0f-9a31-0c5d9e7b1a42") == "/x/{id}"
    assert normalize_path("/health") == "/health"


def test_route_label_prefiere_la_plantilla_de_la_ruta():
    scope = {"route": SimpleNamespace(path="/api/v1/faqs/{faq_id}"), "path": "/api/v1/faqs/77"}
    assert route_label(scope, 200) == "/api/v1/faqs/{faq_id}"
    assert route_label({"path": "/wp-admin/x.php"}, 404) == "unmatched"
    assert route_label({"path": "/a/9"}, 200) == "/a/{id}"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _scope(path="/ping", method="GET", headers=None, route=None):
    scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
    if route:
        scope["route"] = SimpleNamespace(path=route)
    return scope


async def _call(app, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await ObservabilityMiddleware(app)(scope, receive, send)
    return sent


def _app(status=200, boom=False, seen=None):
    async def app(scope, receive, send):
        if seen is not None:
            seen.append(request_id_var.get())
        if boom:
            raise RuntimeError("secreto-interno")
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def _header(sent, name):
    for k, v in sent[0]["headers"]:
        if k == name:
            return v.decode()


async def test_el_middleware_genera_y_devuelve_un_request_id():
    seen = []
    sent = await _call(_app(seen=seen), _scope())
    rid = _header(sent, b"x-request-id")
    assert len(rid) == 32 and seen == [rid]
    assert request_id_var.get() is None            # no se filtra fuera de la petición


async def test_acepta_un_request_id_valido_del_cliente():
    sent = await _call(_app(), _scope(headers=[(b"x-request-id", b"mi-id-de-prueba-01")]))
    assert _header(sent, b"x-request-id") == "mi-id-de-prueba-01"


async def test_reemplaza_un_request_id_invalido_o_malicioso():
    for malo in (b"corto", b"con espacios y \"comillas\" xxx", b"x" * 200):
        sent = await _call(_app(), _scope(headers=[(b"x-request-id", malo)]))
        assert _header(sent, b"x-request-id") != malo.decode("latin-1")
        assert len(_header(sent, b"x-request-id")) == 32


async def test_registra_acceso_y_metricas_con_la_plantilla_de_la_ruta():
    cap = _Capture()
    logger = logging.getLogger("app.access")
    logger.addHandler(cap)
    logger.setLevel(logging.INFO)
    antes = metrics.HTTP_REQUESTS.get(method="GET", route="/items/{item_id}", status=200)
    try:
        await _call(_app(), _scope(path="/items/42?token=secreto".split("?")[0], route="/items/{item_id}"))
    finally:
        logger.removeHandler(cap)
    assert metrics.HTTP_REQUESTS.get(method="GET", route="/items/{item_id}", status=200) == antes + 1
    assert metrics.HTTP_DURATION.count(method="GET", route="/items/{item_id}") >= 1
    [rec] = cap.records
    assert (rec.route, rec.status, rec.method) == ("/items/{item_id}", 200, "GET")
    assert rec.levelno == logging.INFO and rec.duration_ms >= 0
    assert "42" not in rec.getMessage()            # el id concreto no entra al log de acceso


async def test_un_500_se_registra_como_advertencia_y_se_propaga():
    cap = _Capture()
    logger = logging.getLogger("app.access")
    logger.addHandler(cap)
    logger.setLevel(logging.INFO)
    try:
        with pytest.raises(RuntimeError):
            await _call(_app(boom=True), _scope(path="/boom", route="/boom"))
    finally:
        logger.removeHandler(cap)
    [rec] = cap.records
    assert rec.status == 500 and rec.levelno == logging.WARNING
    assert metrics.HTTP_REQUESTS.get(method="GET", route="/boom", status=500) >= 1


async def test_las_rutas_inexistentes_comparten_una_sola_etiqueta():
    await _call(_app(status=404), _scope(path="/wp-admin/setup.php"))
    await _call(_app(status=404), _scope(path="/otra/cosa/rara"))
    assert metrics.HTTP_REQUESTS.get(method="GET", route="unmatched", status=404) >= 2


async def test_los_sondeos_de_salud_se_registran_en_debug():
    cap = _Capture()
    logger = logging.getLogger("app.access")
    logger.addHandler(cap)
    logger.setLevel(logging.DEBUG)
    try:
        await _call(_app(), _scope(path="/health", route="/health"))
    finally:
        logger.removeHandler(cap)
        logger.setLevel(logging.NOTSET)
    assert cap.records[0].levelno == logging.DEBUG


async def test_lo_que_no_es_http_pasa_sin_tocarse():
    llamado = []

    async def ws_app(scope, receive, send):
        llamado.append(scope["type"])

    await ObservabilityMiddleware(ws_app)({"type": "websocket"}, None, None)
    assert llamado == ["websocket"]


# ------------------------------------------------------------------ Application Insights (opcional)
def test_sin_cadena_de_conexion_no_hace_nada():
    assert setup_azure_monitor("") is False


def test_sin_el_paquete_instalado_no_rompe_el_arranque(monkeypatch):
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", None)   # simula paquete ausente
    assert setup_azure_monitor("InstrumentationKey=00000000-0000-0000-0000-000000000000") is False

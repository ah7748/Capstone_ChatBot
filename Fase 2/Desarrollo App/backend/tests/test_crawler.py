import uuid
from types import SimpleNamespace
 
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
 
from app.db.session import SessionLocal
from app.models import Chunk, Tenant, WebsiteScan
from app.services import crawler

pytestmark = pytest.mark.asyncio

HOST = "sitio.test"
BASE = f"https://{HOST}/"
HTML = "text/html; charset=utf-8"
ROBOTS = "User-agent: *\nDisallow: /private/\n"

def page(body, links=()):
    anchors = "".join(f'<a href="{h}">enlace</a>' for h in links)
    return f"<html><body><main>{body}</main>{anchors}</body></html>"

def sitio_basico():
    """path -> (status, content-type, cuerpo). '/roto' no existe (404)."""
    return {
        "/": (200, HTML, page("Bienvenido a la tienda de ejemplo",
                              ["/a", "/a#detalle", "/b", "/private/secret", "/roto",
                               "/manual.pdf", "https://otro.test/externo"])),
        "/a": (200, HTML, page("Politica de devoluciones de la tienda", ["/", "/b"])),
        "/b": (200, HTML, page("Preguntas sobre envios y plazos")),
        "/private/secret": (200, HTML, page("Informacion interna que no debe indexarse")),
        "/manual.pdf": (200, "application/pdf", "%PDF-1.4 binario"),
    }

class FakeSite:
    """Servidor HTTP simulado: registra lo que el crawler pide."""
 
    def __init__(self, pages, robots=None, errors=()):
        self.pages = pages
        self.robots = robots          # None -> /robots.txt responde 404
        self.errors = set(errors)     # paths que fallan con error de red
        self.requests = []            # paths pedidos (sin robots.txt)
        self.robots_requested = False
        self.foreign = []             # peticiones a otros dominios
 
    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != HOST:
            self.foreign.append(str(request.url))
            return httpx.Response(200, text="externo", headers={"content-type": HTML})
        path = request.url.path
        if path == "/robots.txt":
            self.robots_requested = True
        else:
            self.requests.append(path)
        if path in self.errors:
            raise httpx.ConnectError("sin conexión", request=request)
        if path == "/robots.txt":
            if self.robots is None:
                return httpx.Response(404, text="no existe", headers={"content-type": "text/plain"})
            return httpx.Response(200, text=self.robots, headers={"content-type": "text/plain"})
        status, ctype, body = self.pages.get(path, (404, HTML, "no existe"))
        return httpx.Response(status, text=body, headers={"content-type": ctype})


@pytest.fixture
def mock_site(monkeypatch):
    """Instala un FakeSite como servidor del crawler (solo dentro del módulo crawler)."""
    def install(site):
        real = httpx.AsyncClient
 
        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(site)
            return real(*args, **kwargs)
 
        monkeypatch.setattr(crawler, "httpx",
                            SimpleNamespace(AsyncClient=factory, HTTPError=httpx.HTTPError))
        return site
    return install

@pytest_asyncio.fixture
async def make_tenant():
    """Crea empresas aisladas para no tocar los datos del resto de la suite; las borra al final."""
    ids = []
 
    async def _make():
        async with SessionLocal() as db:
            t = Tenant(name="zz-crawler", slug=f"crawler-{uuid.uuid4().hex[:8]}",
                       legal_name="Crawler Test SpA", tax_id="1-9", country="CL",
                       language="es", languages=["es"], status="active")
            db.add(t)
            await db.commit()
            ids.append(t.id)
            return t.id
 
    yield _make
    async with SessionLocal() as db:
        for tid in ids:
            await db.execute(delete(Chunk).where(Chunk.tenant_id == tid))
            await db.execute(delete(WebsiteScan).where(WebsiteScan.tenant_id == tid))
            await db.execute(delete(Tenant).where(Tenant.id == tid))
        await db.commit()


@pytest_asyncio.fixture
async def tenant_id(make_tenant):
    return await make_tenant()
 
 
async def scan_site(tid, url=BASE):
    async with SessionLocal() as db:
        scan = WebsiteScan(tenant_id=tid)
        db.add(scan)
        await db.flush()
        await crawler.run_scan(db, scan, url)
        await db.commit()
        return scan
 
 
async def web_chunks(tid):
    async with SessionLocal() as db:
        return (await db.execute(select(Chunk).where(
            Chunk.tenant_id == tid, Chunk.source_kind == "web"))).scalars().all()
 
 
def sources(chunks):
    return {c.source_name for c in chunks}

# ---------------------------------------------------------------- robots.txt
async def test_respeta_robots_txt(tenant_id, mock_site):
    site = mock_site(FakeSite(sitio_basico(), robots=ROBOTS))
    scan = await scan_site(tenant_id)
    assert scan.status == "done" and scan.progress_pct == 100
    assert site.robots_requested
    assert "/private/secret" not in site.requests          # ni siquiera se pide
    assert sources(await web_chunks(tenant_id)) == {BASE, BASE + "a", BASE + "b"}
    # excluidas: /private/secret (robots), /roto (404) y /manual.pdf (no es HTML)
    assert scan.pages_indexed == 3 and scan.pages_excluded == 3
 
 
async def test_sin_robots_txt_rastrea_todo(tenant_id, mock_site):
    mock_site(FakeSite(sitio_basico(), robots=None))        # robots.txt responde 404
    scan = await scan_site(tenant_id)
    assert scan.status == "done"
    assert BASE + "private/secret" in sources(await web_chunks(tenant_id))
    assert scan.pages_indexed == 4 and scan.pages_excluded == 2
 
 
async def test_robots_txt_inaccesible_no_bloquea_el_escaneo(tenant_id, mock_site):
    mock_site(FakeSite(sitio_basico(), errors={"/robots.txt"}))
    scan = await scan_site(tenant_id)
    assert scan.status == "done"
    assert scan.pages_indexed == 4
 
 
# ------------------------------------------------------ alcance del rastreo
async def test_no_repite_urls_ni_sale_del_dominio(tenant_id, mock_site):
    site = mock_site(FakeSite(sitio_basico(), robots=ROBOTS))
    await scan_site(tenant_id)
    # '/a#detalle' se normaliza a '/a' y cada URL se pide una sola vez
    assert site.requests == ["/", "/a", "/b", "/roto", "/manual.pdf"]
    assert site.foreign == []                               # el enlace externo no se sigue
 
 
# ------------------------------------------------------------- MAX_PAGES
async def test_respeta_max_pages(tenant_id, mock_site, monkeypatch):
    monkeypatch.setattr(crawler, "MAX_PAGES", 5)
    pages = {"/": (200, HTML, page("Inicio del sitio", [f"/p{i}" for i in range(1, 21)]))}
    pages.update({f"/p{i}": (200, HTML, page(f"Pagina numero {i}")) for i in range(1, 21)})
    site = mock_site(FakeSite(pages))
    scan = await scan_site(tenant_id)
    assert scan.status == "done"
    assert scan.pages_indexed == 5
    assert len(site.requests) == 5                          # al llegar al límite no pide más
    assert len(sources(await web_chunks(tenant_id))) == 5
 
 
# ------------------------------------------------------------- reindexado
async def test_reindexa_reemplazando_el_contenido_anterior(tenant_id, mock_site):
    mock_site(FakeSite({
        "/": (200, HTML, page("Inicio version uno", ["/a"])),
        "/a": (200, HTML, page("Contenido antiguo sobre garantias")),
    }))
    primero = await scan_site(tenant_id)
    assert primero.pages_indexed == 2
    antes = await web_chunks(tenant_id)
    assert any("antiguo" in c.content for c in antes)
 
    mock_site(FakeSite({
        "/": (200, HTML, page("Inicio version dos", ["/b"])),
        "/b": (200, HTML, page("Contenido nuevo sobre envios")),
    }))
    segundo = await scan_site(tenant_id)
    despues = await web_chunks(tenant_id)
    assert segundo.status == "done" and segundo.pages_indexed == 2
    assert sources(despues) == {BASE, BASE + "b"}           # /a ya no existe en el índice
    assert not any("antiguo" in c.content for c in despues)
    assert any("nuevo" in c.content for c in despues)
    assert len(despues) == 2                                # sin duplicados
 
 
async def test_reindexar_no_toca_otras_fuentes_ni_otras_empresas(make_tenant, mock_site):
    tid, otro = await make_tenant(), await make_tenant()
    async with SessionLocal() as db:
        db.add_all([
            Chunk(tenant_id=tid, source_kind="faq", source_name="FAQ",
                  chat_type="technical", content="faq de la empresa"),
            Chunk(tenant_id=otro, source_kind="web", source_name="https://otro.test/",
                  chat_type="both", content="web de otra empresa"),
        ])
        await db.commit()
    mock_site(FakeSite({"/": (200, HTML, page("Inicio"))}))
    await scan_site(tid)
    async with SessionLocal() as db:
        faqs = (await db.execute(select(func.count()).select_from(Chunk).where(
            Chunk.tenant_id == tid, Chunk.source_kind == "faq"))).scalar()
    assert faqs == 1
    assert [c.content for c in await web_chunks(otro)] == ["web de otra empresa"]
 
 
# ------------------------------------------------------ contenido y errores
async def test_indexa_solo_texto_visible(tenant_id, mock_site):
    html = ("<html><head><style>.x{color:red}</style></head><body><nav>MENU_NAV</nav>"
            "<script>var CODIGO_JS=1</script><main>Texto util del producto</main>"
            "<footer>PIE_PAGINA</footer></body></html>")
    mock_site(FakeSite({"/": (200, HTML, html)}))
    await scan_site(tenant_id)
    contenido = " ".join(c.content for c in await web_chunks(tenant_id))
    assert "Texto util del producto" in contenido
    for ruido in ("MENU_NAV", "CODIGO_JS", "PIE_PAGINA", "color:red"):
        assert ruido not in contenido
 
 
async def test_pagina_con_error_de_red_se_excluye_sin_abortar(tenant_id, mock_site):
    mock_site(FakeSite(sitio_basico(), errors={"/a"}))
    scan = await scan_site(tenant_id)
    assert scan.status == "done"
    assert scan.pages_excluded >= 1
    assert BASE + "a" not in sources(await web_chunks(tenant_id))
 
 
async def test_error_inesperado_marca_el_escaneo_como_fallido(tenant_id, mock_site, monkeypatch):
    mock_site(FakeSite(sitio_basico()))
 
    async def boom(*args, **kwargs):
        raise RuntimeError("fallo de indexación")
 
    monkeypatch.setattr(crawler.vectorstore, "index_chunks", boom)
    scan = await scan_site(tenant_id)
    assert scan.status == "failed"
    assert "fallo de indexación" in scan.error_detail
    assert scan.finished_at is not None
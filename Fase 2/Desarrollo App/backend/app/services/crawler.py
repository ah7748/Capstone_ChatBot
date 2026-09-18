"""Escáner del sitio del cliente: BFS del mismo dominio, respeta robots.txt, indexa el contenido."""
import urllib.parse
import urllib.robotparser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebsiteScan, now
from app.services import vectorstore

MAX_PAGES = 150


def _clean(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


async def run_scan(db: AsyncSession, scan: WebsiteScan, base_url: str) -> None:
    parsed = urllib.parse.urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    rp = urllib.robotparser.RobotFileParser()
    excluded = 0
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": "AlloxSupportBot/1.0"}) as client:
            try:
                robots = await client.get(f"{origin}/robots.txt")
                rp.parse(robots.text.splitlines() if robots.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])

            queue, seen, pages = [base_url], {base_url}, []
            while queue and len(pages) < MAX_PAGES:
                url = queue.pop(0)
                if not rp.can_fetch("AlloxSupportBot", url):
                    excluded += 1
                    continue
                try:
                    r = await client.get(url)
                except httpx.HTTPError:
                    excluded += 1
                    continue
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                    excluded += 1
                    continue
                text = _clean(r.text)
                if text:
                    pages.append((url, text))
                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.find_all("a", href=True):
                    nxt = urllib.parse.urljoin(url, a["href"]).split("#")[0]
                    if nxt.startswith(origin) and nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
                scan.progress_pct = min(95, int(len(pages) / MAX_PAGES * 100))
                await db.flush()

        prev = scan.pages_indexed
        await vectorstore.delete_source(db, scan.tenant_id, "web")
        total_chunks = 0
        for url, text in pages:
            total_chunks += await vectorstore.index_chunks(
                db, scan.tenant_id, "web", None, url, "both", vectorstore.chunk_text(text))
        scan.pages_indexed = len(pages)
        scan.pages_excluded = excluded
        scan.new_pages = max(0, len(pages) - prev)
        scan.status = "done"
        scan.progress_pct = 100
    except Exception as e:
        scan.status = "failed"
        scan.error_detail = str(e)[:500]
    scan.finished_at = now()
    await db.flush()

"""Sección 11 — Sitio web del cliente y escaneos."""
import uuid

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import company_admin, get_tenant
from app.core.errors import conflict, err, not_found
from app.db.session import get_db
from app.models import Tenant, WebsiteScan
from app.schemas.admin import WebsiteIn
from app.services.ratelimit import allow
from app.workers.tasks import enqueue

router = APIRouter(prefix="/company/website", tags=["website"], dependencies=[Depends(company_admin)])


def _scan_out(s: WebsiteScan) -> dict:
    return {"scan_id": str(s.id), "status": s.status, "progress_pct": s.progress_pct,
            "pages_indexed": s.pages_indexed, "pages_excluded": s.pages_excluded,
            "new_pages": s.new_pages, "error_detail": s.error_detail,
            "started_at": s.started_at.isoformat(),
            "finished_at": s.finished_at.isoformat() if s.finished_at else None}


@router.get("")
async def get_website(tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    if not tenant.website_url:
        raise not_found("Aún no se registró una URL.", "WEBSITE_NOT_SET")
    last = (await db.execute(select(WebsiteScan).where(WebsiteScan.tenant_id == tenant.id)
                             .order_by(WebsiteScan.started_at.desc()).limit(1))).scalar_one_or_none()
    return {"url": tenant.website_url,
            "last_scan": _scan_out(last) if last else None,
            "scanning": bool(last and last.status == "running"),
            "auto_rescan_days": tenant.auto_rescan_days}


@router.put("")
async def put_website(body: WebsiteIn, tenant: Tenant = Depends(get_tenant),
                      db: AsyncSession = Depends(get_db)):
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(body.url)
            reachable = r.status_code < 500
    except httpx.HTTPError:
        raise err(400, "URL_UNREACHABLE", "El sitio no respondió (timeout 10 s).")
    tenant.website_url = body.url
    tenant.auto_rescan_days = body.auto_rescan_days
    await db.commit()
    return {"url": tenant.website_url, "reachable": reachable}


@router.post("/scans", status_code=202)
async def start_scan(tenant: Tenant = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    if not tenant.website_url:
        raise not_found("No hay URL registrada.", "WEBSITE_NOT_SET")
    running = (await db.execute(select(WebsiteScan).where(
        WebsiteScan.tenant_id == tenant.id, WebsiteScan.status == "running"))).scalar_one_or_none()
    if running:
        raise conflict("SCAN_IN_PROGRESS", "Ya hay un escaneo en curso.",
                       {"scan_id": str(running.id)})
    if not await allow(f"scan:{tenant.id}", 1, 3600):
        raise err(429, "SCAN_RATE_LIMIT", "Máximo un escaneo manual por hora.")
    scan = WebsiteScan(tenant_id=tenant.id)
    db.add(scan)
    await db.commit()
    await enqueue("task_scan_website", str(scan.id), tenant.website_url)
    return {"scan_id": str(scan.id), "status": "running"}


@router.get("/scans/{scan_id}")
async def get_scan(scan_id: uuid.UUID, tenant: Tenant = Depends(get_tenant),
                   db: AsyncSession = Depends(get_db)):
    s = await db.get(WebsiteScan, scan_id)
    if s is None or s.tenant_id != tenant.id:
        raise not_found("No existe.", "SCAN_NOT_FOUND")
    return _scan_out(s)

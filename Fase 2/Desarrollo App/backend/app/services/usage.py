"""Agregación de consumo de tokens y ventanas de tiempo de los dashboards."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Tenant, UsageEvent


def period_range(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "7d":
        return now - timedelta(days=7), now
    if period == "30d":
        return now - timedelta(days=30), now
    if period == "prev_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_prev = first_this - timedelta(seconds=1)
        first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return first_prev, first_this
    if period == "3m":
        return now - timedelta(days=90), now
    return now - timedelta(days=365), now  # year


async def usage_breakdown(db: AsyncSession, tenant: Tenant, period: str) -> dict:
    start, end = period_range(period)
    stmt = (select(UsageEvent.bot_type, UsageEvent.channel, func.sum(UsageEvent.tokens))
            .where(UsageEvent.tenant_id == tenant.id,
                   UsageEvent.created_at >= start, UsageEvent.created_at < end)
            .group_by(UsageEvent.bot_type, UsageEvent.channel))
    rows = (await db.execute(stmt)).all()
    total = sum(int(r[2] or 0) for r in rows) or 0
    return {
        "period": period,
        "total_tokens": total,
        "limit_tokens": tenant.token_limit_month or settings.DEFAULT_TOKEN_LIMIT_MONTH,
        "rows": [
            {"bot": r[0], "channel": r[1], "tokens": int(r[2] or 0),
             "pct": round(int(r[2] or 0) * 100 / total) if total else 0}
            for r in rows
        ],
    }


async def month_usage(db: AsyncSession, tenant_id) -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = (await db.execute(select(func.sum(UsageEvent.tokens)).where(
        UsageEvent.tenant_id == tenant_id, UsageEvent.created_at >= start))).scalar()
    return int(total or 0)


async def quota_exceeded(db: AsyncSession, tenant: Tenant) -> bool:
    limit = tenant.token_limit_month or settings.DEFAULT_TOKEN_LIMIT_MONTH
    return await month_usage(db, tenant.id) >= limit

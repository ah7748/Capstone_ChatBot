"""Rate limiting simple por clave (Redis con fallback en memoria)."""
import time
from collections import defaultdict, deque

from app.core.config import settings

_local: dict[str, deque] = defaultdict(deque)
_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis.ping()
        except Exception:
            _redis = False
    return _redis or None


async def allow(key: str, limit: int, window_seconds: int) -> bool:
    r = await _get_redis()
    if r is not None:
        try:
            bucket = f"rl:{key}:{int(time.time() // window_seconds)}"
            n = await r.incr(bucket)
            if n == 1:
                await r.expire(bucket, window_seconds)
            return n <= limit
        except Exception:
            pass
    q = _local[key]
    now = time.time()
    while q and q[0] < now - window_seconds:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True

"""Tiempo real: gestor de WebSockets con pub/sub Redis entre réplicas (fallback en memoria)."""
import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

from app.core.config import settings

_local_channels: dict[str, set[WebSocket]] = defaultdict(set)
_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis.ping()
        except Exception:
            _redis = False  # sin redis: solo entrega local
    return _redis or None


def _session_channel(session_id) -> str:
    return f"ws:session:{session_id}"


def _agent_channel(tenant_id) -> str:
    return f"ws:agents:{tenant_id}"


async def register(channel: str, ws: WebSocket) -> None:
    _local_channels[channel].add(ws)


async def unregister(channel: str, ws: WebSocket) -> None:
    _local_channels[channel].discard(ws)


async def _deliver_local(channel: str, payload: dict) -> None:
    dead = []
    for ws in list(_local_channels.get(channel, ())):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _local_channels[channel].discard(ws)


async def publish(channel: str, payload: dict) -> None:
    r = await _get_redis()
    if r is not None:
        try:
            await r.publish(channel, json.dumps(payload))
            return
        except Exception:
            pass
    await _deliver_local(channel, payload)


async def publish_session_event(session_id, payload: dict) -> None:
    await publish(_session_channel(session_id), payload)


async def publish_agent_event(tenant_id, payload: dict) -> None:
    await publish(_agent_channel(tenant_id), payload)


async def subscribe_loop(channel: str, ws: WebSocket) -> None:
    """Reenvía a este WebSocket lo publicado en Redis (o cola local si no hay Redis)."""
    r = await _get_redis()
    await register(channel, ws)
    if r is None:
        # sin redis: register basta, publish entrega localmente; mantener viva la conexión
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"event": "ping", "data": {}})
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_json(json.loads(msg["data"]))
    finally:
        await pubsub.unsubscribe(channel)

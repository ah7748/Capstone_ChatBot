"""Sección 19 — Canales WebSocket (usuario final y consola de agente)."""
import uuid

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models import User
from app.services.realtime import subscribe_loop, unregister

router = APIRouter()


@router.websocket("/ws/chat/{session_id}")
async def ws_chat(ws: WebSocket, session_id: str, token: str = Query(...)):
    try:
        claims = decode_token(token)
        assert claims.get("scope") == "public_chat"
        assert claims.get("session_id") == session_id
    except (pyjwt.PyJWTError, AssertionError):
        await ws.close(code=4401)
        return
    await ws.accept()
    channel = f"ws:session:{session_id}"
    try:
        await subscribe_loop(channel, ws)
    except WebSocketDisconnect:
        pass
    finally:
        await unregister(channel, ws)


@router.websocket("/ws/agent")
async def ws_agent(ws: WebSocket, token: str = Query(...)):
    try:
        claims = decode_token(token)
        assert claims.get("scope") == "api" and claims.get("role") == "human_agent"
    except (pyjwt.PyJWTError, AssertionError):
        await ws.close(code=4401)
        return
    async with SessionLocal() as db:
        user = await db.get(User, uuid.UUID(claims["sub"]))
        if user is None or user.status != "active":
            await ws.close(code=4403)
            return
        tenant_id = user.tenant_id
    await ws.accept()
    channel = f"ws:agents:{tenant_id}"
    try:
        await subscribe_loop(channel, ws)
    except WebSocketDisconnect:
        pass
    finally:
        await unregister(channel, ws)

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.services import email as mail
from app.services.email_templates import invitation_email, reset_email
from app.services.notifications import deliver_invitation
from tests.conftest import login

pytestmark = pytest.mark.asyncio


def _token(text: str) -> str:
    return re.search(r"token=([\w\-]+)", text).group(1)


def _boom(msg):
    raise ConnectionError("SMTP caído")


# ---------------- Fase 1 ----------------
async def test_send_email_memory():
    mail.outbox.clear()
    assert await mail.send_email("a@b.com", "Hola", "Texto") is True
    assert mail.outbox[0]["to"] == "a@b.com"


async def test_send_email_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(mail, "_smtp_send", _boom)
    assert await mail.send_email("a@b.com", "Hola", "Texto") is False


async def test_console_and_memory_blocked_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    mail.outbox.clear()
    assert await mail.send_email("a@b.com", "Hola", "Texto") is False
    assert mail.outbox == []


@pytest.mark.parametrize("lang,word", [("es", "invitó"), ("en", "invited"), ("pt", "convidou")])
async def test_invitation_templates(lang, word):
    subject, text, html = invitation_email(lang, "Ana", "WellQ", "http://x/accept-invitation?token=abc")
    assert "WellQ" in subject and word in text
    assert "token=abc" in text and "token=abc" in html


async def test_reset_template_and_delivery():
    _, text, _ = reset_email("en", "Ana", "http://x/reset-password?token=zzz")
    assert "token=zzz" in text
    mail.outbox.clear()
    await deliver_invitation("n@x.com", "Nico", "pt", "tok123", "WellQ")
    assert "/accept-invitation?token=tok123&lang=pt" in mail.outbox[0]["text"]

# ---------------- Fase 2 ----------------
async def _create_tenant(client, root, slug, email, lang="pt"):
    return await client.post("/api/v1/platform/tenants", headers=root, json={
        "name": slug.title(), "slug": slug, "legal_name": f"{slug} SpA", "tax_id": "76.111.222-3",
        "country": "cl", "language": lang, "admin_email": email,
        "deepseek_api_key": f"sk-test-{slug}"})


async def test_tenant_invitation_full_flow(client, seed):
    mail.outbox.clear()
    root, _ = await login(client, "root@alloxentric.com")
    r = await _create_tenant(client, root, "mailco", "admin@mailco.cl")
    assert r.status_code == 201
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg["to"] == "admin@mailco.cl" and "convidou" in msg["text"]      # idioma pt
    assert "&lang=pt" in msg["text"]
    acc = await client.post("/api/v1/auth/invitations/accept",
                            json={"invitation_token": _token(msg["text"]), "password": "Password123!"})
    assert acc.status_code == 200
    _, data = await login(client, "admin@mailco.cl")                          # ya puede entrar
    assert data["user"]["role"] == "company_admin"


async def test_platform_resend_invalidates_old_token(client, seed):
    mail.outbox.clear()
    root, _ = await login(client, "root@alloxentric.com")
    r = await _create_tenant(client, root, "resendco", "admin@resendco.cl", lang="en")
    tid = r.json()["tenant_id"]
    res = await client.post(f"/api/v1/platform/tenants/{tid}/resend-invitation", headers=root)
    assert res.status_code == 200 and len(mail.outbox) == 2
    old, new = _token(mail.outbox[0]["text"]), _token(mail.outbox[1]["text"])
    assert old != new
    bad = await client.post("/api/v1/auth/invitations/accept",
                            json={"invitation_token": old, "password": "Password123!"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVITE_INVALID"
    ok = await client.post("/api/v1/auth/invitations/accept",
                           json={"invitation_token": new, "password": "Password123!"})
    assert ok.status_code == 200


async def test_agent_invitation_expiry_and_resend(client, seed):
    mail.outbox.clear()
    headers, _ = await login(client, "max@wellq.co.uk")
    r = await client.post("/api/v1/company/human-agents", headers=headers, json={
        "name": "Lucía Mora", "email": "lucia@wellq.co.uk",
        "escalation_type": "technical", "channel": "web"})
    assert r.status_code == 201
    agent_id = r.json()["agent_id"]
    old = _token(mail.outbox[0]["text"])

    from app.db.session import SessionLocal
    from app.models import User
    async with SessionLocal() as db:                      # forzar expiración
        u = (await db.execute(select(User).where(User.email == "lucia@wellq.co.uk"))).scalar_one()
        u.invitation_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()
    exp = await client.post("/api/v1/auth/invitations/accept",
                            json={"invitation_token": old, "password": "Password123!"})
    assert exp.status_code == 410 and exp.json()["error"]["code"] == "INVITE_EXPIRED"

    res = await client.post(f"/api/v1/company/human-agents/{agent_id}/resend-invitation",
                            headers=headers)
    assert res.status_code == 200 and len(mail.outbox) == 2
    new = _token(mail.outbox[1]["text"])
    ok = await client.post("/api/v1/auth/invitations/accept",
                           json={"invitation_token": new, "password": "Password123!"})
    assert ok.status_code == 200
    again = await client.post(f"/api/v1/company/human-agents/{agent_id}/resend-invitation",
                              headers=headers)
    assert again.status_code == 409                       # ya activada: no se reenvía


async def test_agent_email_change_sends_to_new_address(client, seed):
    mail.outbox.clear()
    headers, _ = await login(client, "max@wellq.co.uk")
    r = await client.post("/api/v1/company/human-agents", headers=headers, json={
        "name": "Tomás Ruiz", "email": "tomas@wellq.co.uk",
        "escalation_type": "both", "channel": "web"})
    aid = r.json()["agent_id"]
    await client.patch(f"/api/v1/company/human-agents/{aid}", headers=headers,
                       json={"email": "tomas.nuevo@wellq.co.uk"})
    assert [m["to"] for m in mail.outbox] == ["tomas@wellq.co.uk", "tomas.nuevo@wellq.co.uk"]


async def test_reset_request_same_response_for_unknown_email(client, seed):
    mail.outbox.clear()
    a = await client.post("/api/v1/auth/password/reset-request", json={"email": "max@wellq.co.uk"})
    b = await client.post("/api/v1/auth/password/reset-request", json={"email": "nadie@nada.com"})
    assert a.json() == b.json() == {"sent": True}
    assert len(mail.outbox) == 1 and "reset-password?token=" in mail.outbox[0]["text"]


async def test_api_survives_email_failure(client, seed, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(mail, "_smtp_send", _boom)
    headers, _ = await login(client, "max@wellq.co.uk")
    r = await client.post("/api/v1/company/human-agents", headers=headers, json={
        "name": "Rosa Vera", "email": "rosa@wellq.co.uk",
        "escalation_type": "commercial", "channel": "web"})
    assert r.status_code == 201                           # el proveedor falló, la API no

async def test_invitation_sent_flag_and_resend_failure(client, seed, monkeypatch):
    headers, _ = await login(client, "max@wellq.co.uk")
    body = {"name": "Ana Ruiz", "email": "ana.ruiz@wellq.co.uk",
            "escalation_type": "technical", "channel": "web"}
    ok = await client.post("/api/v1/company/human-agents", headers=headers, json=body)
    assert ok.status_code == 201 and ok.json()["invitation_sent"] is True

    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(mail, "_smtp_send", _boom)
    bad = await client.post("/api/v1/company/human-agents", headers=headers,
                            json={**body, "email": "ana.ruiz2@wellq.co.uk"})
    assert bad.status_code == 201 and bad.json()["invitation_sent"] is False
    r = await client.post(f"/api/v1/company/human-agents/{bad.json()['agent_id']}/resend-invitation",
                          headers=headers)
    assert r.status_code == 502 and r.json()["error"]["code"] == "EMAIL_SEND_FAILED"

async def test_resend_failure_returns_false(monkeypatch):
    async def caido(msg):
        raise RuntimeError("Resend caído")
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "resend")
    monkeypatch.setattr(mail, "_resend_send", caido)
    assert await mail.send_email("a@b.com", "Hola", "Texto") is False

async def test_brevo_failure_returns_false(monkeypatch):
    async def caido(msg):
        raise RuntimeError("Brevo caído")
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(mail, "_brevo_send", caido)
    assert await mail.send_email("a@b.com", "Hola", "Texto") is False
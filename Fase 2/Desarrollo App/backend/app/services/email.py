"""Envío de correo: memory (tests) · console (dev) · smtp · resend (real). Nunca lanza excepción."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings

log = logging.getLogger("email")
outbox: list[dict] = []   # solo con EMAIL_BACKEND=memory


def _smtp_send(msg: dict) -> None:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = settings.EMAIL_FROM, msg["to"], msg["subject"]
    m.set_content(msg["text"])
    if msg.get("html"):
        m.add_alternative(msg["html"], subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        if settings.SMTP_TLS:
            s.starttls()
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(m)


async def _resend_send(msg: dict) -> None:
    payload = {"from": settings.EMAIL_FROM, "to": [msg["to"]],
               "subject": msg["subject"], "text": msg["text"]}
    if msg.get("html"):
        payload["html"] = msg["html"]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.resend.com/emails", json=payload,
                              headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"})
    if r.status_code >= 400:
        raise RuntimeError(f"Resend respondió {r.status_code}: {r.text[:200]}")


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    msg = {"to": to, "subject": subject, "text": text, "html": html}
    try:
        backend = settings.EMAIL_BACKEND
        if backend in ("console", "memory") and settings.APP_ENV not in ("dev", "test"):
            # imprimiría tokens de activación en los logs de producción
            raise RuntimeError(f"EMAIL_BACKEND={backend} no se permite con APP_ENV={settings.APP_ENV}")
        if backend == "memory":
            outbox.append(msg)
        elif backend == "console":
            print(f"\n=== EMAIL → {to} | {subject}\n{text}\n===", flush=True)
        elif backend == "smtp":
            await asyncio.to_thread(_smtp_send, msg)
        elif backend == "resend":
            await _resend_send(msg)
        else:
            raise ValueError(f"EMAIL_BACKEND desconocido: {backend}")
        return True
    except Exception:
        log.exception("No se pudo enviar el correo a %s", to)
        return False
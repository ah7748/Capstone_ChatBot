from app.core.config import settings
from app.services.email import send_email
from app.services.email_templates import invitation_email, reset_email


def _base() -> str:
    return settings.FRONTEND_BASE_URL.rstrip("/")


async def deliver_invitation(to: str, name: str, lang: str, token: str, tenant_name: str) -> None:
    link = f"{_base()}/accept-invitation?token={token}&lang={lang}"
    subject, text, html = invitation_email(lang, name, tenant_name, link)
    await send_email(to, subject, text, html)


async def deliver_reset(to: str, name: str, lang: str, token: str) -> None:
    link = f"{_base()}/reset-password?token={token}&lang={lang}"
    subject, text, html = reset_email(lang, name, link)
    await send_email(to, subject, text, html)
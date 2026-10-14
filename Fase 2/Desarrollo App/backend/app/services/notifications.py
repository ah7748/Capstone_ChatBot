from app.core.config import settings
from app.services.email import send_email
from app.services.email_templates import invitation_email, reset_email


def _base() -> str:
    return settings.FRONTEND_BASE_URL.rstrip("/")


async def deliver_invitation(to, name, lang, token, tenant_name) -> bool:
    link = f"{_base()}/accept-invitation?token={token}&lang={lang}"
    subject, text, html = invitation_email(lang, name, tenant_name, link)
    return await send_email(to, subject, text, html)


async def deliver_reset(to, name, lang, token) -> bool:
    link = f"{_base()}/reset-password?token={token}&lang={lang}"
    subject, text, html = reset_email(lang, name, link)
    return await send_email(to, subject, text, html)
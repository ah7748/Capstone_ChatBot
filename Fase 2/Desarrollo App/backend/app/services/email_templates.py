"""Plantillas de correo es/en/pt: (asunto, texto plano, html)."""
from html import escape

PRODUCT = "Chatbot de Soporte Genérico · Alloxentric"

T = {
    "es": {
        "inv_subject": "Te invitaron a {tenant}",
        "inv_body": "Hola {name},\n\n{tenant} te invitó a {product}.\n"
                    "Activa tu cuenta y define tu contraseña aquí (válido 7 días):\n{link}\n\n"
                    "Si no esperabas este correo, puedes ignorarlo.",
        "inv_btn": "Activar mi cuenta",
        "rst_subject": "Restablece tu contraseña",
        "rst_body": "Hola {name},\n\nPara crear una nueva contraseña entra aquí (válido 1 hora):\n{link}\n\n"
                    "Si no lo solicitaste, ignora este correo.",
        "rst_btn": "Restablecer contraseña",
    },
    "en": {
        "inv_subject": "You have been invited to {tenant}",
        "inv_body": "Hi {name},\n\n{tenant} invited you to {product}.\n"
                    "Activate your account and set your password here (valid for 7 days):\n{link}\n\n"
                    "If you were not expecting this email, you can ignore it.",
        "inv_btn": "Activate my account",
        "rst_subject": "Reset your password",
        "rst_body": "Hi {name},\n\nTo set a new password go here (valid for 1 hour):\n{link}\n\n"
                    "If you did not request this, ignore this email.",
        "rst_btn": "Reset password",
    },
    "pt": {
        "inv_subject": "Você foi convidado para {tenant}",
        "inv_body": "Olá {name},\n\n{tenant} convidou você para {product}.\n"
                    "Ative sua conta e defina sua senha aqui (válido por 7 dias):\n{link}\n\n"
                    "Se você não esperava este e-mail, pode ignorá-lo.",
        "inv_btn": "Ativar minha conta",
        "rst_subject": "Redefina sua senha",
        "rst_body": "Olá {name},\n\nPara criar uma nova senha acesse aqui (válido por 1 hora):\n{link}\n\n"
                    "Se você não solicitou, ignore este e-mail.",
        "rst_btn": "Redefinir senha",
    },
}


def _html(text: str, link: str, btn: str) -> str:
    body = escape(text).replace("\n", "<br>")
    return (f'<div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px">{body}'
            f'<p><a href="{escape(link)}" style="background:#00a79d;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;font-weight:600">{escape(btn)}</a></p></div>')


def _render(kind: str, lang: str, name: str, link: str, tenant: str = "") -> tuple[str, str, str]:
    t = T.get(lang, T["es"])
    vars_ = {"name": name, "tenant": tenant, "product": PRODUCT, "link": link}
    subject = t[f"{kind}_subject"].format(**vars_)
    text = t[f"{kind}_body"].format(**vars_)
    return subject, text, _html(text, link, t[f"{kind}_btn"])


def invitation_email(lang, name, tenant, link):
    return _render("inv", lang, name, link, tenant)


def reset_email(lang, name, link):
    return _render("rst", lang, name, link)
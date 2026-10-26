"""Prompts por defecto del bot y limpieza del texto que devuelve el modelo."""
import re

# Reglas de estilo que se añaden SIEMPRE al prompt del agente (aunque la empresa lo haya personalizado).
STYLE_RULES = (
    "Estilo: tono cordial y profesional. Responde breve (máximo 4 frases o una lista corta). "
    "No uses Markdown ni asteriscos; si necesitas una lista, usa líneas que empiecen con un guion. "
    "No expliques cómo derivar a una persona ni cómo abrir un ticket: el sistema lo hace solo cuando "
    "el usuario lo pide. No menciones frases que el usuario deba escribir."
)


def default_agent_prompt(company: str, agent_type: str) -> str:
    """Prompt inicial de un agente del bot (la empresa puede editarlo desde la aplicación)."""
    if agent_type == "commercial":
        role = f"Eres el asistente comercial de {company}: resuelves dudas sobre planes, precios y contratación."
    else:
        role = f"Eres el asistente de soporte técnico de {company}: ayudas a resolver problemas de uso y acceso."
    return f"{role} Usa solo la documentación de la empresa; si algo no está en ella, dilo con honestidad."


_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])")
_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_CODE = re.compile(r"`{1,3}([^`]*)`{1,3}")
_BULLET = re.compile(r"(?m)^(\s*)[*•]\s+")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def plain_text(text: str) -> str:
    """Quita el formato Markdown (el chat muestra texto plano)."""
    text = _LINK.sub(r"\1 (\2)", text)
    text = _BOLD.sub(r"\2", text)
    text = _CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _BULLET.sub(r"\1- ", text)
    text = _ITALIC.sub(r"\1", text)
    return text.replace("**", "").strip()

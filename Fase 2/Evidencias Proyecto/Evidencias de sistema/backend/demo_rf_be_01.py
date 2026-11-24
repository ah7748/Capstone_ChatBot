"""Demo antes/despues de RF-BE-01. Uso (desde backend): python demo_rf_be_01.py"""
from app.services.rag import COMMERCIAL_HINTS

try:
    from app.services.rag import heuristic_intent
except ImportError:          # rama main: todavia no existe
    heuristic_intent = None

CASOS = [
    ("Can you give me an explanation of this error?", "technical"),
    ("Aprecio su ayuda, no puedo entrar", "technical"),
    ("¿Cómo exporto la planilla de usuarios?", "technical"),
    ("Me da error 415 al subir un PDF", "technical"),
    ("Necesito la factura de marzo", "commercial"),
    ("Quiero la renovacion de mi suscripcion", "commercial"),
    ("Do you offer a discount for teams?", "commercial"),
    ("¿Cuánto me sale tenerlo todo el año?", "commercial"),
    ("El plan da error al pagar", "ambiguo"),
    ("Hola, necesito ayuda", "ambiguo"),
]


def antes(texto):
    """Logica vieja: substring en COMMERCIAL_HINTS; si calza, llama al endpoint roto."""
    if any(h in texto.lower() for h in COMMERCIAL_HINTS):
        return "LLAMADA ROTA"
    return "technical"


def ahora(texto):
    if heuristic_intent is None:
        return "(no disponible)"
    return heuristic_intent(texto) or "-> LLM"


print(f"{'MENSAJE':48} {'CORRECTO':11} {'ANTES':14} AHORA")
print("-" * 92)
for texto, correcto in CASOS:
    print(f"{texto[:47]:48} {correcto:11} {antes(texto):14} {ahora(texto)}")
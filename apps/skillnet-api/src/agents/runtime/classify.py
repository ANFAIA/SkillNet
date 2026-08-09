"""El router semantico de funciones de contenido — prototipo de la fase 3/4.

Por que existe
==============

``shape.py`` clasifica la forma del texto con expresiones regulares y solo sabe decir
cuatro cosas, tres de las cuales terminan en ``Table``. Medido los dias 8 y 9 de agosto:
sobre 71 renders y siete documentos de tres generos distintos, 15 de los 22 componentes
del kit no se emitieron **ni una vez**, y ninguna intervencion en la capa de prompt lo
movio (quitar el veto a los contenedores, reescribir las descripciones, y anadir una
regla explicita de encaminamiento dieron los tres el mismo resultado: cero).

La causa no es que el modelo no sepa. Ante un documento de contraste emitio
``Table(["Situacion","Resultado"], ...)``: entendio la semantica y no tenia por donde
sacarla, porque ningun detector puede nombrar ``BeforeAfter``.

Este modulo prueba la otra mitad: que la funcion se decida **por significado** en vez de
por forma del texto. La resolucion funcion -> componente ya no vive aqui, vive en
``UI_KIT.candidates_for`` desde la fase 2.

Que hereda de ``shape.py``, y no es negociable
==============================================

La asimetria. El modulo original lo dice literalmente: *"a missed hint costs nothing,
while a hint the material cannot support sends the model to invent rows"*. Aqui vale
igual y con mas motivo, porque una funcion equivocada manda a un productor que no encaja:
**ante la duda, se devuelve ``None``**. El prompt lo dice tres veces y el parseo trata
cualquier respuesta rara como ``None``.

Estado
======

Prototipo tras una feature flag (``SEMANTIC_ROUTER``, por defecto ``False``). No hay
productores por funcion todavia: la funcion detectada se convierte en un ``ShapeSignal``
mas y viaja por el mismo camino que los deterministas. Es deliberado — mide el router
solo, sin confundirlo con el efecto de partir la generacion.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.render.kit import ContentFunction

logger = logging.getLogger(__name__)

#: Solo las funciones que hoy NO tiene ningun detector determinista. Las tres que si
#: (enumerar, procedimentar, cuantificar) se dejan a las regex: son gratis, estan
#: calibradas contra fallos reales y el router no tiene nada que anadir ahi.
ROUTABLE: tuple[ContentFunction, ...] = (
    ContentFunction.CONTRASTAR,
    ContentFunction.VARIAR,
    ContentFunction.EXPLORAR,
)

ROUTER_TEMPERATURE = 0.0
ROUTER_MAX_TOKENS = 120
ROUTER_USE_CASE = "clasifica_funcion"

FUNCTION_ROUTER_SYSTEM = """\
Eres un clasificador. Lees material de formacion laboral y dices que HACE ese material,
no como se veria en pantalla.

Responde SOLO con JSON: {"funcion": "<valor>", "evidencia": "<cita literal breve>"}

Valores posibles:

- "contrastar": el material enfrenta DOS estados. Lo correcto contra lo incorrecto, el
  antes contra el despues, lo que funciona contra lo que no. Tiene que haber dos lados
  reconocibles, no una lista de errores sueltos.
- "variar": el MISMO proceso cambia segun el caso — segun el turno, el tipo de cliente,
  el tipo de tramite. Tiene que ser el mismo proceso con variantes, no procesos distintos.
- "explorar": el material enuncia una RELACION entre una variable y un efecto: cuanto mas
  de X, mas de Y. La relacion tiene que estar dicha en el texto, no deducida por ti.
- "ninguna": cualquier otra cosa.

Reglas duras:

1. Ante la duda, "ninguna". Es la respuesta correcta la mayoria de las veces.
2. "evidencia" es una cita LITERAL del material, de menos de 15 palabras. Si no puedes
   citar una frase que lo demuestre, la respuesta es "ninguna".
3. Una lista de cosas NO es contrastar. Un procedimiento con pasos NO es variar.
4. No expliques nada fuera del JSON.\
"""


def build_router_prompt(*, title: str, summary: str, source: str) -> str:
    """El material, recortado. El router lee mucho menos que el generador."""
    body = source.strip()[:2500]
    parts = [f"TITULO: {title}".strip()]
    if summary.strip():
        parts.append(f"RESUMEN: {summary.strip()}")
    parts.append("MATERIAL:")
    parts.append(body)
    return "\n".join(parts)


def parse_router_response(raw: str) -> ContentFunction | None:
    """``None`` ante cualquier cosa que no sea una funcion enrutable con evidencia.

    Todo camino dudoso devuelve ``None`` a proposito: es la asimetria de ``shape.py``.
    """
    try:
        payload: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    value = str(payload.get("funcion") or "").strip().lower()
    evidence = str(payload.get("evidencia") or "").strip()

    # Sin cita no hay funcion: la regla 2 del prompt, aplicada del lado servidor para que
    # no dependa de que el modelo se acuerde.
    if not evidence:
        return None

    for function in ROUTABLE:
        if value == function.value:
            return function
    return None


async def classify_function(
    *, title: str, summary: str, source: str, llm: Any
) -> tuple[ContentFunction | None, Any]:
    """Devuelve ``(funcion, usage)``. ``funcion`` es ``None`` si no hay una clara.

    Nunca levanta: un router que rompe la generacion seria peor que un router que no
    aporta. Un fallo se registra y se trata como "ninguna".
    """
    if not source.strip():
        return None, None
    prompt = build_router_prompt(title=title, summary=summary, source=source)
    try:
        raw, usage = await llm.complete_with_usage(
            FUNCTION_ROUTER_SYSTEM,
            prompt,
            temperature=ROUTER_TEMPERATURE,
            max_tokens=ROUTER_MAX_TOKENS,
            json_mode=True,
        )
    except Exception as exc:  # noqa: BLE001 - degradar, nunca romper el render
        logger.warning("router semantico fallo, se sigue sin funcion: %s", exc)
        return None, None
    return parse_router_response(raw), usage


__all__ = [
    "FUNCTION_ROUTER_SYSTEM",
    "ROUTABLE",
    "ROUTER_USE_CASE",
    "build_router_prompt",
    "classify_function",
    "parse_router_response",
]

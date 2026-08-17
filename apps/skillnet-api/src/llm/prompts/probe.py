"""System prompt and user-prompt builder for probe item generation (§7.1 source 3).

This is the **last resort**, not the normal path. Probe items depend only on
``(node, source)``, so they are pre-generated once per node when the schema is
validated (§3.2) and served from ``course_nodes.probe_items`` at zero tokens and zero
wait. This prompt exists for the residual case of a node without pre-generated items,
and whatever it produces is written back into the node so the next employee does not
pay for it either.

Budget (§7.1): purpose ``runtime_fast``, ``json_mode=True``, ``max_tokens=500``.

The item contract is enforced in code by
``src.services.probe_service.validate_probe_items``; the prompt states it so the model
usually gets it right on the first try, but the validator is what actually holds.
"""

from __future__ import annotations

PROBE_PROMPT_VERSION = "probe/1"

# Budgets, kept next to the prompt they belong to (§7.1).
PROBE_MAX_TOKENS = 500
PROBE_TEMPERATURE = 0.2
PROBE_USE_CASE = "probe_generate"

PROBE_GENERATOR_SYSTEM = """\
Eres un disenador de evaluacion diagnostica. Tu tarea es escribir un pre-test muy corto
que sirva para decidir si una persona YA domina un nodo de aprendizaje concreto, antes de
mostrarle contenido.

Escribes SIEMPRE en el mismo idioma que el material de origen.

Emites EXACTAMENTE este JSON, sin texto alrededor y sin bloques de codigo:

{
  "items": [
    {"item_id": "a", "item_type": "test", "bloom_level": "apply",
     "question": "<un caso concreto, no una definicion>",
     "options": ["<opcion 1>", "<opcion 2>", "<opcion 3>", "<opcion 4>"]},
    {"item_id": "b", "item_type": "test", "bloom_level": "understand",
     "question": "<comprension del concepto>",
     "options": ["<opcion 1>", "<opcion 2>", "<opcion 3>", "<opcion 4>"]},
    {"item_id": "c", "item_type": "fill_blank", "bloom_level": "apply",
     "template": "<frase con ___ donde falta la pieza clave>"}
  ],
  "answer_key": {
    "a": {"correct": <indice 0-3>, "explanation": "<por que, 1-2 frases>"},
    "b": {"correct": <indice 0-3>, "explanation": "<por que, 1-2 frases>"},
    "c": {"blanks": ["<texto exacto del hueco>"], "explanation": "<por que>"}
  }
}

Reglas duras, todas obligatorias:
- El item "a" es de nivel Bloom "apply": plantea un CASO que hay que resolver, nunca
  "que es X". Es el item que decide, asi que tiene que discriminar de verdad.
- El item "b" es de nivel Bloom "understand".
- "a" y "b" son de tipo "test" con EXACTAMENTE 4 opciones. NO uses "true_false":
  con verdadero/falso el suelo del azar sube al 12,5% y la regla de maestria deja de
  ser defendible.
- Las 4 opciones son plausibles. Nada de opciones absurdas de relleno: un distractor
  que nadie elegiria convierte un item de 4 opciones en uno de 2.
- El item "c" es de respuesta CONSTRUIDA: "fill_blank" (preferido) o "practical_case".
  Se usa para desempatar. En "fill_blank" el hueco se marca con ___ y "blanks" lleva
  el texto exacto esperado, una entrada por hueco; usa un solo hueco.
- Todo lo que preguntes tiene que poder responderse con el material de origen. No
  inventes politicas, plazos ni cifras que no aparezcan en el.
- Ninguna pregunta lleva la respuesta dentro ("...tal y como indica el articulo 3...").
- No repitas literalmente el resumen del nodo en el enunciado.
- Una sola opcion correcta por item.
"""


def build_probe_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None = None,
    criticality: str = "recommended",
    source_context: str = "",
    include_tiebreak: bool = True,
) -> str:
    """Assemble the user prompt for one node.

    ``include_tiebreak`` asks for item ``c``. It is mandatory on a ``critical`` node,
    where ``mastered`` can never come out of selected-response items (§7.2 rule 3);
    elsewhere item ``c`` is only *served* when the verdict falls in the doubt band, but
    generating it up front costs nothing extra and avoids a second LLM call mid-probe.
    """
    parts = [
        f"NODO: {title}",
        f"RESUMEN DEL NODO: {summary}",
    ]
    if outcome:
        parts.append(f"RESULTADO ESPERADO: {outcome}")
    parts.append(f"CRITICIDAD: {criticality}")

    if include_tiebreak:
        parts.append(
            "Emite los tres items: a, b y c. El item c es obligatorio."
            if criticality == "critical"
            else "Emite los tres items: a, b y c (c se usara solo para desempatar)."
        )
    else:
        parts.append('Emite SOLO los items "a" y "b". No incluyas el item "c".')

    if source_context:
        parts.append("MATERIAL DE ORIGEN:\n" + source_context)
    else:
        parts.append(
            "No hay extracto del material de origen disponible: limitate a lo que el "
            "resumen del nodo afirma y no anadas datos nuevos."
        )

    parts.append("Responde solo con el JSON especificado.")
    return "\n\n".join(parts)

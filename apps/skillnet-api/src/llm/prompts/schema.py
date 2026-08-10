"""System prompt and user-prompt builder for the design-time schema designer (v2).

One LLM call per proposal (§4.1). It emits a *schema* only — nodes, summaries,
criticality, prerequisites — and **never** any lesson content: content is generated
per learner at runtime.

Two hard rules the prompt enforces, both because breaking them produces a silent
failure rather than a visible one:

1. **Prerequisites are indices into the emitted list**, never uuids. The model
   cannot know the uuids ``persist_schema`` will mint, so a "uuid" would be an
   invented string that maps to nothing.
2. **``source_headings`` is chosen from a closed list.** An invented heading
   matches no chunk, so ``load_context`` would hand ``genera_ui`` an empty source
   and the result is plausible content with no documentary basis.
"""

from __future__ import annotations

import json

from src.models import NodeCriticality, UiFormat

_CRITICALITY_VALUES = ", ".join(m.value for m in NodeCriticality)
_UI_FORMAT_VALUES = ", ".join(
    m.value for m in UiFormat if m is not UiFormat.SIMULATION
)

# How many headings go into the prompt. A long policy manual can carry hundreds;
# past this the closed list stops being readable for an 8B model.
MAX_HEADINGS_IN_PROMPT = 120

# Length budget per intent_density step (§3.1: 1 = condensed, 5 = expanded).
# Son TECHOS, no objetivos: medido en manuales procedimentales reales, un objetivo
# de "6-10 nodos" empuja al modelo a rellenar con nodos genericos ("Fundamentos del
# servicio al cliente") cuando el material solo da para 3. La cifra es un maximo; el
# material manda.
_DENSITY_GUIDANCE: dict[int, str] = {
    1: "Muy condensado: hasta 5 nodos, solo lo imprescindible.",
    2: "Condensado: hasta 7 nodos.",
    3: "Equilibrado: hasta 10 nodos.",
    4: "Extenso: hasta 14 nodos, admite nodos contextuales.",
    5: "Muy extenso: hasta 18 nodos, desglosa cada procedimiento.",
}


SCHEMA_DESIGNER_SYSTEM = f"""\
Eres un disenador instruccional. Tu tarea es proponer el ESQUEMA de un curso: la
lista de nodos de aprendizaje y sus dependencias. NO escribes contenido: el
contenido se genera despues, adaptado a cada empleado.

Un nodo es una unidad minima de competencia: algo que el empleado sabe hacer o no
sabe hacer. "Plazo de devolucion" es un nodo; "Politica comercial" es un curso.

Para cada nodo devuelves:
- title: nombre corto y concreto (maximo 80 caracteres)
- summary: 1-3 frases que describan QUE cubre el nodo. Obligatorio y no vacio: el
  tutor lee el arbol de summaries para decidir que nodo es relevante.
- outcome: que sabra hacer el empleado al terminarlo, en una frase
- criticality: uno de [{_CRITICALITY_VALUES}]
- default_ui_format: uno de [{_UI_FORMAT_VALUES}]
- estimated_minutes: entero entre 2 y 20
- source_headings: lista de headings del documento que respaldan este nodo
- prerequisites: lista de INDICES (base 0) de otros nodos de esta misma lista

Reglas, todas obligatorias:
1. prerequisites usa INDICES de la lista que estas devolviendo (0 = el primer
   nodo), nunca identificadores ni titulos. Un nodo no puede ser prerrequisito de
   si mismo, y el grafo debe ser aciclico: si A depende de B, B no puede depender
   de A ni por cadena.
2. source_headings solo puede contener cadenas EXACTAS de la lista
   "HEADINGS DISPONIBLES" del mensaje del usuario. No inventes, no traduzcas, no
   reformules, no abrevies. Si ningun heading respalda el nodo, devuelve [].
3. Al menos un nodo debe ser "critical". Marca "critical" lo que un error
   convertiria en incumplimiento, riesgo o coste real. No marques todo critical.
4. Ordena los nodos de lo fundamental a lo avanzado. Un prerrequisito debe
   aparecer ANTES en la lista que el nodo que lo necesita.
5. El numero de la guia de densidad es un TECHO, no un objetivo. ANTES de listar
   nodos, identifica las secciones o procedimientos REALES del documento y crea UN
   nodo por cada uno; no anadas ninguno mas. Usa MENOS nodos si el material es fino
   (un manual corto puede dar solo 3-4 nodos) y no rellenes para llegar a una cifra.
   Toda afirmacion debe rastrearse al material. Esta regla manda sobre la densidad.
6. Escribe title, summary y outcome en el MISMO IDIOMA que el documento de origen.
   Si el documento esta en espanol, responde en espanol; si esta en ingles, en
   ingles. Nunca traduzcas ni cambies de idioma.
7. Prefiere anclar cada nodo a un heading de "HEADINGS DISPONIBLES" (source_headings
   no vacio). Un nodo SIN heading solo se justifica si cubre una seccion REAL del
   documento cuyo heading falta o quedo mal extraido (p.ej. un PDF a dos columnas);
   no lo crees si no corresponde a algo concreto que el documento diga. Ante la
   duda: ancla, o no crees el nodo.
8. Cubre TODAS las secciones o procedimientos del documento antes de desglosar uno
   solo. Si el documento describe varios procedimientos o plataformas equivalentes,
   da un nodo a cada uno; no sobre-detalles el primero dejando los demas sin cubrir.
   En un documento que es un procedimiento con pasos, crea un nodo por procedimiento
   y no anadas nodos de teoria que el documento no contiene.

Responde en JSON valido, sin texto alrededor, con la forma:
{{"nodes": [{{"title": str, "summary": str, "outcome": str,
            "criticality": str, "default_ui_format": str,
            "estimated_minutes": int, "source_headings": [str],
            "prerequisites": [int]}}],
 "notes": [str]}}
"""


def build_schema_prompt(
    extracted_themes: list[dict],
    source_metadata: dict,
    available_headings: list[str],
    *,
    intent_density: int = 3,
    course_title: str | None = None,
    course_outcome: str | None = None,
) -> str:
    """User prompt for the schema designer.

    ``available_headings`` is the **closed list** rule 2 of the system prompt
    refers to: the real, distinct ``chunk_metadata->>'heading'`` values of the
    source document. It is rendered as an explicit enumeration (not prose) so the
    model has no room to paraphrase.
    """
    density = _DENSITY_GUIDANCE.get(
        intent_density, _DENSITY_GUIDANCE[3]
    )
    headings = [h for h in available_headings if h and h.strip()]
    truncated = headings[:MAX_HEADINGS_IN_PROMPT]

    if truncated:
        headings_block = "\n".join(f"- {heading}" for heading in truncated)
    else:
        headings_block = (
            "(el documento no expone headings; devuelve source_headings vacio "
            "en todos los nodos)"
        )
    if len(headings) > len(truncated):
        headings_block += (
            f"\n(... {len(headings) - len(truncated)} headings mas omitidos; "
            "usa solo los listados)"
        )

    course_block = ""
    if course_title or course_outcome:
        course_block = (
            "=== CURSO ===\n"
            f"Titulo: {course_title or '(sin titulo)'}\n"
            f"Resultado esperado: {course_outcome or '(sin definir)'}\n\n"
        )

    # Courses created "from topic" have no document — relax the traceability rule.
    topic_note = ""
    if not source_metadata.get("doc_count"):
        topic_note = (
            "=== NOTA ===\n"
            "Este curso se crea a partir del titulo y la descripcion, sin documento "
            "de origen. Disena los nodos basandote en los temas y el titulo del curso. "
            "La regla de rastrearse al material de origen no aplica; "
            "source_headings sera [] en todos los nodos.\n\n"
        )

    return (
        "Propon el esquema de nodos de este curso.\n\n"
        f"{course_block}"
        f"{topic_note}"
        f"=== DENSIDAD PEDIDA (intent_density={intent_density}) ===\n"
        f"{density}\n\n"
        "=== METADATOS DE ORIGEN ===\n"
        f"{json.dumps(source_metadata, ensure_ascii=False, sort_keys=True)}\n\n"
        "=== TEMAS EXTRAIDOS ===\n"
        f"{json.dumps(extracted_themes, ensure_ascii=False, sort_keys=True)}\n\n"
        "=== HEADINGS DISPONIBLES (lista cerrada) ===\n"
        f"{headings_block}"
    )

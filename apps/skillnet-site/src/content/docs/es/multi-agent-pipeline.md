---
title: "Pipeline multiagente"
order: 28
section: "core"
---

# Multi-Agent Render Pipeline

> **Estado: diseño del pipeline de render actual; migración aprobada.** Este documento conserva la
> historia y el detalle operativo del subgrafo que segmenta el nodo monolítico `genera_ui`
> en cuatro agentes especializados, define la estrategia de pre-generacion y streaming, y
> traza la hoja de ruta hacia el formato multimodal.
>
> Para trabajo nuevo, la arquitectura objetivo traslada el trabajo caro a generación/publicación,
> deja al runtime seleccionar variantes preparadas y usa una frontera neutral. Está definida en
> [`learning-experience-architecture.md`](/docs/learning-experience-architecture) y gana sobre este
> documento en esa dirección. Hasta completar sus gates, esta página sigue describiendo el pipeline
> implementado.

Depende de: [v2-dynamic-courses.md](/docs/dynamic-courses),
[openui-adoption.md](/docs/openui-adoption), [tuning.md](/docs/tuning) y
[learning-experience-architecture.md](/docs/learning-experience-architecture).

---

## Indice

1. [Por que segmentar](#1-por-que-segmentar)
2. [El pipeline](#2-el-pipeline)
3. [Los cuatro agentes](#3-los-cuatro-agentes)
4. [Estrategia de pre-generacion](#4-estrategia-de-pre-generacion)
5. [Streaming como red de seguridad](#5-streaming-como-red-de-seguridad)
6. [Manejo de fallos](#6-manejo-de-fallos)
7. [La filosofia: el aprendiz nunca espera](#7-la-filosofia-el-aprendiz-nunca-espera)
8. [SSE y streaming parcial](#8-sse-y-streaming-parcial)
9. [Nuevo subgrafo: `genera_ui_multi`](#9-nuevo-subgrafo-genera_ui_multi)
10. [Feature flag y migracion](#10-feature-flag-y-migracion)
11. [Cache key](#11-cache-key)
12. [Detalle de tokens por agente](#12-detalle-de-tokens-por-agente)
13. [Tests](#13-tests)
14. [Futuro multimodal (v3)](#14-futuro-multimodal-v3)
15. [Decisiones de diseno](#15-decisiones-de-diseno)
16. [Checklist de implementacion](#16-checklist-de-implementacion)

---

## 1. Por que segmentar

### 1.1 El problema medido

El nodo `genera_ui` hace TODO en una sola llamada LLM:

1. Decide que estructura debe tener la pantalla (cuantos bloques, de que tipo, en que orden).
2. Escribe el contenido pedagogico (la explicacion, los ejemplos, los datos).
3. Crea las preguntas de evaluacion (QuizItem, DragOrder).
4. Genera las respuestas correctas (answer key).
5. Produce el programa OpenUI Lang valido.

Medido en el banco de calidad (`scripts/quality_bench.py`, 2026-08-06):

| Metrica | Valor actual |
|---------|-------------|
| Cobertura de catalogo | 6-7 de 22 tipos (27-32 %) |
| Tipos por pantalla (media) | 3.9-4.3 |
| Acierto a la primera | 28-67 % (varia entre ejecuciones) |
| Reparaciones necesarias | 11-57 % |
| Fallbacks | 14-22 % |
| Bloques nunca usados | BeforeAfter, DragOrder, Tabs, StepByStepReveal, Chart, Accordion... |

El modelo produce siempre los mismos tres bloques (Stack + TextContent + QuizItem) porque
el prompt le pide que decida la estructura Y escriba el contenido Y formule preguntas
en una sola salida. Un modelo de 8B no puede atender las tres tareas en
paralelo con calidad.

### 1.2 La solucion

Cuatro agentes, con Content Writer e Interaction Designer en **paralelo**:

```
Blueprint Architect (~1s)
        |
    +---+---+
    |       |
Content   Interaction    (paralelo via asyncio.gather, ~2s)
Writer    Designer
    |       |
    +---+---+
        |
    Assembler (instantaneo, sin LLM)
        |
    Validate + Persist
```

Cada agente tiene una sola responsabilidad, un prompt corto y una salida validable.

### 1.3 Restriccion critica: Groq free tier

El tier gratuito de Groq tiene un techo de 6 000 tokens por minuto (TPM). El `genera_ui`
monolitico ya promedia ~5 250 tokens de entrada. Tres llamadas LLM secuenciales
triplicarian el TPM. La solucion:

- **Agent 1 (Blueprint):** ~1 200 tokens entrada, ~300 tokens salida. JSON compacto.
- **Agent 2 (Content):** ~2 500 tokens entrada, ~600 tokens salida. Solo bloques de contenido.
- **Agent 3 (Interactions):** ~2 000 tokens entrada, ~400 tokens salida. Solo bloques interactivos + answer key.
- **Agent 4 (Assembler):** 0 tokens. Puro Python.

Total: ~5 700 tokens entrada + ~1 300 tokens salida = ~7 000 tokens.
Contra el monolitico: ~5 250 entrada + ~800 salida = ~6 050 tokens.

La diferencia es ~1 000 tokens (+16 %), aceptable porque:
1. Se eliminan las reparaciones (que cuestan una segunda llamada completa).
2. La fuente se envia UNA vez (al Agent 2), no en las tres llamadas.
3. El blueprint es JSON compacto, no dialecte OpenUI.

Agents 2 y 3 corren en **PARALELO** via `asyncio.gather`. Ambos reciben el blueprint
y trabajan independientemente. El Assembler espera a los dos. Con OpenAI no hay
restriccion de TPM. Si se usa Groq free tier, un flag los secuencia con gap de ~15 s.

---

## 2. El pipeline

### 2.1 Diagrama completo

```
Blueprint Architect (LLM, JSON mode, ~500 tokens salida, ~1s)
        |
    +---+---+
    |       |
Content   Interaction      (paralelo via asyncio.gather, ~2s)
Writer    Designer
(LLM,     (LLM,
 stream,   ~400 tok out)
 ~600 tok)
    |       |
    +---+---+
        |
    Assembler (sin LLM, instantaneo)
        |
    Validate (gate.canonicalize)
        |
    Persist (node_renders)
```

### 2.2 Que hace cada agente

| Agente | LLM | Entrada | Salida | Responsabilidad |
|--------|-----|---------|--------|-----------------|
| **Blueprint Architect** | Si (JSON mode) | Metadatos del nodo + perfil del aprendiz + formato + shape hints | JSON blueprint: que componentes, en que orden, con que intencion | Decidir la ESTRUCTURA. No escribe contenido ni preguntas. Elige el componente segun la forma del material (lista -> Table, procedimiento -> StepByStepReveal, comparacion -> BeforeAfter, multiples aspectos -> Tabs). |
| **Content Writer** | Si (streaming) | Blueprint + documento fuente | Declaraciones OpenUI Lang para bloques de contenido (TextContent, Table, StepByStepReveal, Tabs, Callout, etc.) | Escribir el CONTENIDO educativo. Especializado en redaccion pedagogica. Hace streaming para que el frontend pueda mostrar bloques progresivamente. |
| **Interaction Designer** | Si | Blueprint + contexto fuente + perfil del aprendiz | Declaraciones OpenUI Lang para bloques interactivos (QuizItem, DragOrder, BeforeAfter) + answer key | Crear PREGUNTAS con distractores plausibles. Corre en PARALELO con el Content Writer. |
| **Assembler** | No | Salidas del Content Writer + Interaction Designer | Programa OpenUI Lang completo + answer key | Fusionar las salidas, resolver la lista `root.children` segun el orden del blueprint, validar via `gate.canonicalize()`, persistir el render. |

---

## 3. Los cuatro agentes

### 3.1 Agent 1: Blueprint Architect

**Responsabilidad:** Decidir la estructura de la pantalla: cuantos bloques, de que tipo,
en que orden, con que intencion pedagogica. No escribe contenido.

**Fichero:** `apps/skillnet-api/src/agents/runtime/agents/blueprint.py`

**Funcion:**

```python
async def run_blueprint(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
    llm: Any,
) -> Blueprint:
    """Produce el blueprint JSON de la pantalla."""
```

**Salida (JSON):**

```json
{
  "blocks": [
    {"id": "intro", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
    {"id": "tabla", "type": "Table", "intent": "concepto", "columns": 2, "note": "un alergeno por fila"},
    {"id": "q1", "type": "QuizItem", "intent": "verificar", "item_type": "test", "bloom": "apply"}
  ]
}
```

**Tipo Pydantic:**

```python
# apps/skillnet-api/src/agents/runtime/agents/types.py

class BlueprintBlock(BaseModel):
    id: str
    type: str  # nombre del componente del kit
    intent: Literal["enganchar", "concepto", "verificar", "refuerzo"]
    variant: str | None = None       # para TextContent
    columns: int | None = None       # para Table
    item_type: str | None = None     # para QuizItem
    bloom: str | None = None         # para QuizItem/DragOrder
    note: str | None = None          # instruccion libre para los agentes 2/3

class Blueprint(BaseModel):
    blocks: list[BlueprintBlock]
```

**Prompt del sistema:**

```python
BLUEPRINT_SYSTEM = """\
Eres el arquitecto de pantallas de SkillNet. Tu trabajo es decidir la ESTRUCTURA de una
pantalla de aprendizaje: cuantos bloques, de que tipo y en que orden. NO escribes contenido,
NO escribes texto para el aprendiz, NO escribes preguntas. Solo decides la forma.

Responde UNICAMENTE con JSON valido, sin texto antes ni despues:

{"blocks": [
  {"id": "<id_ascii>", "type": "<componente>", "intent": "<enganchar|concepto|verificar|refuerzo>", ...},
  ...
]}

Componentes disponibles para el slot CONCEPTO (elige segun el material):
- Table: listas de cosas, comparativas, pares etiqueta-valor. Indica columns: 1 o 2.
- StepByStepReveal: procedimiento con explicacion por paso.
- BeforeAfter: comparacion de dos estados (bien/mal, antes/despues).
- Tabs: multiples aspectos independientes de un tema (3+ pestanas).
- StepSequence: procedimiento simple sin explicaciones detalladas.
- Card: agrupar bloques relacionados con borde visual.

Componentes disponibles para el slot VERIFICAR (elige segun el concepto):
- QuizItem: pregunta con opciones. Indica item_type y bloom.
- DragOrder: ordenar elementos arrastrando.
- BeforeAfter: si el concepto tiene un bien/mal.

Estructura obligatoria de la pantalla:
1. ENGANCHAR — TextContent con variant "lead". Una situacion real del puesto.
2. CONCEPTO — UN bloque de los de arriba. NUNCA TextContent("body") para el concepto.
3. VERIFICAR — UN bloque interactivo. Si el formato es "mixed" o "exercise", DEBE ser
   QuizItem o DragOrder.
4. Opcionalmente un Callout de refuerzo si el nodo es de cumplimiento obligatorio.

MAXIMO 4 bloques (intro + concepto + practica + opcionalmente un Callout).

Reglas duras:
- Los ids son ASCII sin tildes: "intro", "tabla", "q1", nunca "introducción".
- Cada id es unico.
- El primer bloque siempre es TextContent con variant "lead".
- Si el formato es "exercise" o "mixed", el ultimo bloque es QuizItem o DragOrder.
- NO inventes componentes que no esten en la lista.
- El campo "note" es una instruccion breve para quien rellene el contenido (opcional).
"""
```

**Prompt del usuario:**

```python
def build_blueprint_prompt(
    *,
    title: str,
    summary: str,
    outcome: str | None,
    criticality: str,
    ui_format: str,
    effective_density: int,
    scaffold_band: str,
    role_title: str | None,
    sector: str | None,
    experience_level: str,
    target_bloom: str,
    shape_hints: Sequence[str],
) -> str:
    parts = [
        f"FORMATO: {ui_format}",
        "",
        "NODO",
        f"- Titulo: {title}",
        f"- Resumen: {summary}",
    ]
    if outcome:
        parts.append(f"- Resultado esperado: {outcome}")
    parts.append(f"- {_criticality_rule(criticality)}")
    parts.extend([
        "",
        "APRENDIZ",
        f"- Puesto: {role_title or 'sin declarar'}",
        f"- Sector: {sector or 'sin declarar'}",
        f"- Experiencia: {experience_level}",
        f"- Nivel cognitivo objetivo: {target_bloom}",
        f"- Presupuesto: {_density_budget(effective_density)}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ])
    if shape_hints:
        parts.append("")
        parts.append("FORMA DEL MATERIAL (leido de la fuente)")
        for hint in shape_hints:
            parts.append(f"- {hint}")
    parts.append("")
    parts.append("Responde solo con el JSON.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=512, temperature=0.2, json_mode=True.

**Validacion de salida:** Se parsea como `Blueprint` con Pydantic. Si falla:
- Se intenta `parse_json_response` (las mismas estrategias de siempre).
- Si aun falla, se genera un blueprint por defecto basado en `ui_format` + `shape_hints`.

**Blueprint por defecto (sin LLM):**

```python
def default_blueprint(ui_format: str, shape_hints: Sequence[str]) -> Blueprint:
    """El mismo blueprint que habria elegido el monolitico, sin gastar una llamada."""
    blocks = [
        BlueprintBlock(id="intro", type="TextContent", intent="enganchar", variant="lead"),
    ]
    # Concepto: Table si hay hints de enumeracion, StepSequence si procedimiento, TextContent si nada
    if any("Table" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=2))
    elif any("StepSequence" in h or "StepByStepReveal" in h for h in shape_hints):
        blocks.append(BlueprintBlock(id="concepto", type="StepByStepReveal", intent="concepto"))
    else:
        blocks.append(BlueprintBlock(id="concepto", type="Table", intent="concepto", columns=1))
    # Verificar
    if ui_format in ("exercise", "mixed"):
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="apply"))
    else:
        blocks.append(BlueprintBlock(id="q1", type="QuizItem", intent="verificar", item_type="test", bloom="understand"))
    return Blueprint(blocks=blocks)
```

---

### 3.2 Agent 2: Content Writer

**Responsabilidad:** Escribir los bloques de contenido del blueprint (TextContent, Table,
StepByStepReveal, StepSequence, Callout, Tabs, BeforeAfter, Card) en dialecte OpenUI Lang.
No escribe preguntas ni respuestas. Hace **streaming** de la salida para que el frontend
pueda mostrar bloques progresivamente si es necesario.

**Fichero:** `apps/skillnet-api/src/agents/runtime/agents/content_writer.py`

**Funcion:**

```python
async def run_content_writer(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
    llm: Any,
) -> ContentOutput:
    """Produce las declaraciones OpenUI Lang para los bloques de contenido."""
```

**Salida:**

```python
class ContentOutput(BaseModel):
    """Declaraciones OpenUI Lang para los bloques de contenido, una por linea."""
    declarations: str  # texto en dialecte OpenUI Lang, sin root ni quizzes
```

Ejemplo de salida:
```
intro = TextContent("Un conato de fuego en el almacen: tienes 10 segundos de extintor.", "lead")
pasos = StepByStepReveal("Regla PAS", [["P - Quitar el Pasador", "Tira de la anilla con un gesto seco."], ["A - Apuntar a la base", "Nunca a las llamas."], ["S - Barrer en zigzag", "Desde 2-3 metros, de lado a lado."]])
```

**Prompt del sistema:**

```python
CONTENT_WRITER_SYSTEM: str  # se construye dinamicamente

def content_writer_system() -> str:
    return render_prompt().rstrip("\n") + """

## SkillNet Content Writer: tu tarea especifica

Eres el escritor de CONTENIDO de SkillNet. Recibes un blueprint (la estructura de la
pantalla) y la fuente. Tu trabajo es escribir SOLO los bloques de contenido, en dialecte
OpenUI Lang.

Lo que SI haces:
- Escribir TextContent, Table, StepByStepReveal, StepSequence, Callout, Tabs, TabItem,
  BeforeAfter, Card, Accordion, AccordionItem, Chart, CodeBlock.
- Una declaracion por linea: id = Componente(args...)
- Usar los ids EXACTOS del blueprint.
- Basar todo en la fuente. NO inventar datos.

Lo que NO haces:
- NO escribir QuizItem ni DragOrder (esos los escribe otro agente).
- NO escribir la linea root = Stack(...).
- NO escribir ---ANSWER-KEY---.
- NO escribir prosa antes ni despues del programa.
- NO repetir las instrucciones ni explicar lo que haces.

Reglas del dialecto: las de arriba (SkillNet 1-13), sin excepciones.
- SkillNet 14: ids en ASCII sin tildes.
- SkillNet 16: Callout tiene 3 tonos (info, warn, success), nunca "critical".
- SkillNet 17: a la derecha del = va siempre una llamada a bloque.
- SkillNet 13: NO inventes cifras ni datos que no esten en la fuente.

Responde SOLO con las declaraciones, una por linea. Nada mas.
"""
```

**Prompt del usuario:**

```python
def build_content_prompt(
    *,
    blueprint: Blueprint,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    scaffold_band: str,
    criticality: str,
) -> str:
    content_blocks = [b for b in blueprint.blocks if b.type not in ("QuizItem", "DragOrder")]
    blocks_desc = "\n".join(
        f"- {b.id}: {b.type} (intent={b.intent}"
        + (f", variant={b.variant}" if b.variant else "")
        + (f", columns={b.columns}" if b.columns else "")
        + (f", nota={b.note}" if b.note else "")
        + ")"
        for b in content_blocks
    )
    parts = [
        "BLUEPRINT (escribe SOLO estos bloques, con estos ids exactos)",
        blocks_desc,
        "",
        f"NODO: {title}",
        f"RESUMEN: {summary}",
        f"- {_criticality_rule(criticality)}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ]
    if role_title:
        parts.append(f"- Los ejemplos son situaciones de un/una {role_title}"
                     + (f" del sector {sector}." if sector else "."))
    parts.append("")
    if source_context.strip():
        parts.append("FUENTE (es la unica verdad; no anadas datos que no esten aqui)")
        parts.append(clip_source(source_context))
    else:
        parts.append("NO HAY FUENTE. Limitate al resumen del nodo.")
    parts.append("")
    parts.append("Escribe las declaraciones, una por linea. Nada mas.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=800 (fast) / 1600 (heavy), temperature=0.4.

La fuente se envia SOLO a este agente. Es el unico que necesita leerla para producir
contenido. El Agent 3 recibe la fuente recortada (para verificar respuestas), no completa.

---

### 3.3 Agent 3: Interaction Designer

**Responsabilidad:** Escribir los bloques interactivos del blueprint (QuizItem, DragOrder)
en dialecte OpenUI Lang, mas el answer key. No escribe contenido explicativo. Corre en
**PARALELO** con el Content Writer via `asyncio.gather`.

**Fichero:** `apps/skillnet-api/src/agents/runtime/agents/interaction_designer.py`

**Funcion:**

```python
async def run_interaction_designer(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
    llm: Any,
) -> InteractionOutput:
    """Produce las declaraciones de bloques interactivos + answer key."""
```

**Salida:**

```python
class InteractionOutput(BaseModel):
    declarations: str   # declaraciones OpenUI Lang (QuizItem, DragOrder)
    answer_key: dict    # JSON del answer key
```

Ejemplo de salida:
```
declarations:
q1 = QuizItem("q1", "test", "apply", "Un cliente celiaco pide una fritura. El aceite se uso antes para rebozados. Que le dices?", ["Que si, el aceite no retiene gluten", "Que no es apto: trazas de gluten", "Que pregunte al cocinero", "Que solo si es alergico"])

answer_key:
{"q1": {"correct": 1, "explanation": "El aceite que frio un rebozado con harina contiene trazas de gluten."}}
```

**Prompt del sistema:**

```python
INTERACTION_DESIGNER_SYSTEM: str  # se construye dinamicamente

def interaction_designer_system() -> str:
    return render_prompt().rstrip("\n") + f"""

## SkillNet Interaction Designer: tu tarea especifica

Eres el disenador de INTERACCIONES de SkillNet. Recibes un blueprint y el contenido
ya escrito. Tu trabajo es escribir SOLO los bloques interactivos y de evaluacion.

Lo que SI haces:
- Escribir QuizItem y DragOrder, en dialecte OpenUI Lang.
- Una declaracion por linea: id = Componente(args...)
- Escribir el bloque {ANSWER_KEY_SENTINEL} con las respuestas correctas.
- Usar los ids EXACTOS del blueprint.
- Las preguntas se basan en el contenido ya escrito (que esta abajo).

Lo que NO haces:
- NO escribir TextContent, Table, StepSequence ni ningun otro bloque de contenido.
- NO escribir la linea root = Stack(...).
- NO escribir prosa antes ni despues.

## Como hacer buenas preguntas

Reglas para QuizItem de tipo "test":
- SIEMPRE 4 opciones.
- Los DISTRACTORES son errores reales que un empleado cometeria, no tonterias.
- La pregunta plantea un CASO CONCRETO: "Un cliente te dice...", "Recibes una entrega de...",
  nunca "Cual es..." ni "Que significa...".
- La explicacion dice POR QUE la correcta es correcta.
- QuizItem tiene EXACTAMENTE 5 argumentos: QuizItem("id", "tipo", "bloom", "pregunta?", ["A", "B", "C", "D"]).

Para DragOrder:
- EXACTAMENTE 3 argumentos: DragOrder("instruccion", ["items..."], ["orden correcto..."]).
- 4-6 elementos, acciones concretas.

Formato de la clave de respuestas:
Despues de las declaraciones, una linea con exactamente {ANSWER_KEY_SENTINEL} y a continuacion
un unico JSON:

{ANSWER_KEY_SENTINEL}
{{"q1": {{"correct": 2, "explanation": "Por que esa y no otra."}}}}

Forma de cada entrada segun item_type:
- "test": {{"correct": <indice 0-based>, "explanation": "..."}}
- "true_false": {{"correct": true|false, "explanation": "..."}}
- "fill_blank": {{"blanks": ["texto exacto"], "explanation": "..."}}
- "order_steps": {{"correct_order": [indices], "explanation": "..."}}

Responde con las declaraciones y su clave. Nada mas.
"""
```

**Prompt del usuario:**

```python
def build_interaction_prompt(
    *,
    blueprint: Blueprint,
    content_declarations: str,
    title: str,
    summary: str,
    source_context: str,
    role_title: str | None,
    sector: str | None,
    target_bloom: str,
    scaffold_band: str,
) -> str:
    interaction_blocks = [b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")]
    if not interaction_blocks:
        return ""  # no hay bloques interactivos que escribir
    blocks_desc = "\n".join(
        f"- {b.id}: {b.type} (item_type={b.item_type or 'test'}, bloom={b.bloom or target_bloom})"
        for b in interaction_blocks
    )
    parts = [
        "BLUEPRINT (escribe SOLO estos bloques, con estos ids exactos)",
        blocks_desc,
        "",
        f"NODO: {title}",
        f"RESUMEN: {summary}",
        f"- Nivel cognitivo objetivo: {target_bloom}",
        f"- {_SCAFFOLD_RULES.get(scaffold_band, _SCAFFOLD_RULES['neutral'])}",
    ]
    if role_title:
        parts.append(f"- Las preguntas son sobre situaciones de un/una {role_title}"
                     + (f" del sector {sector}." if sector else "."))
    parts.append("")
    parts.append("CONTENIDO YA ESCRITO (tu pregunta debe basarse en esto)")
    parts.append(content_declarations)
    parts.append("")
    if source_context.strip():
        parts.append("FUENTE ORIGINAL (para verificar que la respuesta es correcta)")
        parts.append(clip_source(source_context, limit=3000))
    parts.append("")
    parts.append("Escribe las declaraciones y la clave de respuestas. Nada mas.")
    return "\n".join(parts)
```

**Token budget:** max_tokens=600 (fast) / 1200 (heavy), temperature=0.3.

Nota: la fuente se recorta a 3 000 caracteres (la mitad del limite habitual) porque
este agente la necesita solo para verificar que su respuesta es correcta, no para
generar contenido nuevo.

---

### 3.4 Agent 4: Assembler (sin LLM)

**Responsabilidad:** Combinar las salidas de los agentes 2 y 3 en un programa OpenUI Lang
completo, validarlo y prepararlo para `validate_ui`. Es instantaneo: no llama a ningun LLM.

**Fichero:** `apps/skillnet-api/src/agents/runtime/agents/assembler.py`

**Funcion:**

```python
def assemble(
    *,
    blueprint: Blueprint,
    content_output: ContentOutput,
    interaction_output: InteractionOutput | None,
    ui_format: str,
) -> tuple[str, dict]:
    """Ensambla el programa completo + answer key. Retorna (raw_dsl, answer_key)."""
```

**Logica:**

```python
def assemble(
    *,
    blueprint: Blueprint,
    content_output: ContentOutput,
    interaction_output: InteractionOutput | None,
    ui_format: str,
) -> tuple[str, dict]:
    # 1. Recopilar todas las declaraciones
    all_declarations: list[str] = []
    declared_ids: set[str] = set()

    # Declaraciones de contenido
    for line in content_output.declarations.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            block_id = line.split("=", 1)[0].strip()
            declared_ids.add(block_id)
        all_declarations.append(line)

    # Declaraciones de interaccion
    if interaction_output and interaction_output.declarations.strip():
        for line in interaction_output.declarations.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                block_id = line.split("=", 1)[0].strip()
                declared_ids.add(block_id)
            all_declarations.append(line)

    # 2. Construir la linea root
    # Los hijos del root son los ids del blueprint, en orden, filtrados por los que
    # realmente se declararon. Si un id del blueprint no se declaro, se omite.
    root_children = [b.id for b in blueprint.blocks if b.id in declared_ids]
    gap = "md"
    root_line = f'root = Stack([{", ".join(root_children)}], "{gap}")'

    # 3. Ensamblar programa completo (root primero para streaming)
    program_lines = [root_line] + all_declarations
    program = "\n".join(program_lines)

    # 4. Answer key
    answer_key = {}
    if interaction_output:
        answer_key = interaction_output.answer_key

    # 5. Reconstruir el raw_dsl completo (programa + sentinel + key)
    raw_dsl = program
    if answer_key:
        raw_dsl += f"\n{ANSWER_KEY_SENTINEL}\n" + json.dumps(answer_key, ensure_ascii=False)

    return raw_dsl, answer_key
```

**Resolucion de conflictos:**

| Conflicto | Resolucion |
|-----------|-----------|
| Id del blueprint no declarado por ningun agente | Se omite de `root.children`. Log de warning. |
| Agente declara un id que no esta en el blueprint | Se incluye (el modelo puede haber renombrado). Log de warning. |
| Ids duplicados entre agentes | Gana el segundo (interaccion sobre contenido). Log de error. |
| Blueprint pide QuizItem pero Agent 3 fallo | Se monta sin interaccion; `validate_ui` rechazara si el formato lo exige y se activara el repair. |

---

## 4. Estrategia de pre-generacion

La generacion de contenido no espera al aprendiz. El sistema trabaja por delante.

### 4.1 Primer nodo: generado en la creacion del curso

Cuando un curso se activa (`schema_status = 'validated'`), se genera el render del primer
nodo de forma **sincrona** (await). En este punto no existe ningun aprendiz, asi que el
contenido es generico — no hay perfil, no hay `format_vector`, no hay historial de errores.

Eso es deliberado: todos los aprendices que abran el curso encontraran el primer nodo
listo inmediatamente. La adaptacion empieza a partir del nodo 2, cuando ya hay datos.

### 4.2 Nodos siguientes: ventana deslizante de 3

Cuando el aprendiz esta en el nodo N, el frontend lanza `POST /nodes/{id}/render`
(fire-and-forget, `{ force: false }`) para los nodos N+1, N+2 y N+3. El codigo esta
en `NodeView.tsx`:

```tsx
// Sliding window: pre-render the next 3 nodes ahead of the current position.
const ahead = ordered
  .filter((n) => n.position > node.position)
  .slice(0, 3)
for (const n of ahead) {
  void post(`/nodes/${n.id}/render`, { force: false }).catch(() => undefined)
}
```

El backend es **idempotente**: si el render ya existe en cache o hay una generacion
en vuelo para ese `cache_key`, no se duplica el trabajo. Cada visita a un nodo
desliza la ventana hacia adelante.

Ademas, cuando el aprendiz abre el curso (`CourseView.tsx`), se pre-renderizan los
primeros nodos desbloqueados que esten en `not_started` o `learning`:

```tsx
// Pre-render the next unlocked node the learner is likely to open.
// Only 1 ahead -- remaining nodes generate on-the-fly adapted to the
// learner's profile. Future: auto-adjust lookahead based on model speed.
return [...dynamicNodes.nodes]
  .sort((a, b) => a.position - b.position)
  .filter((n) => !n.locked && (n.state === 'not_started' || n.state === 'learning'))
  .slice(0, 1)
```

### 4.3 Adaptacion al aprendiz desde el nodo 2

A partir del segundo nodo, el contenido se adapta al perfil del aprendiz:

- **`format_vector`**: 4 dimensiones (visual, textual, interactivo, ejemplo) inferidas de
  los `learning_events` del aprendiz (scroll_slow, quiz_correct, quiz_wrong, explain_click,
  expand, etc.). Ventana deslizante de 30 dias con decaimiento exponencial.
- **`scaffold_band`**: Si el aprendiz comete errores, el sistema baja la intensidad
  (mas explicaciones, menos densidad). Si acierta, sube (mas reto, mas densidad).
- **`target_bloom`**: El nivel cognitivo objetivo se ajusta segun la maestria actual
  del aprendiz en el nodo.
- **Periodo de calibracion**: Los primeros 3 nodos completados (`CALIBRATION_NODES = 3`)
  acumulan el vector pero no lo usan — `vector_bucket` devuelve `""` para que no entre
  en el `cache_key` ni en el prompt.

### 4.4 Futuro: lookahead adaptativo

Auto-ajustar el tamano de la ventana segun la velocidad de inferencia del modelo:

- Modelo rapido (< 1s por render, ej. Groq llama-3.1-8b-instant): 1 nodo adelante.
- Modelo lento (> 5s por render, ej. 7B local en CPU): 3-4 nodos adelante.

---

## 5. Streaming como red de seguridad

### 5.1 El caso ideal: contenido pre-generado

En el caso normal, el contenido ya esta en cache cuando el aprendiz llega al nodo.
La respuesta es instantanea. No hay carga, no hay streaming visible. El aprendiz
abre el nodo y el contenido esta ahi.

### 5.2 El caso fallback: streaming invisible

Si la pre-generacion no completo a tiempo (porque el aprendiz navega rapido, porque
es un nodo que se salto la ventana, o porque el modelo fue lento), el Content Writer
hace streaming de bloques a medida que los genera. El frontend muestra cada bloque
con una transicion de opacidad (fade-in). Mientras tanto, el Interaction Designer
genera el quiz en paralelo.

El objetivo es que el aprendiz **nunca sepa** que la generacion esta ocurriendo.
Nada de "Preparando tu leccion...", nada de skeletons, nada de barras de progreso,
nada de spinners. El contenido simplemente aparece, como si hubiera estado ahi siempre
pero la pagina se estuviera cargando.

### 5.3 Implementacion del streaming

Cada agente que hace streaming llama a `_stream_declarations()`, que parsea
declaraciones individuales a medida que el LLM las produce y las emite como
eventos `ui_block` por SSE:

```python
async def _stream_declarations(
    llm: Any,
    system: str,
    user_prompt: str,
    *,
    request_id: str,
    backend_name: str = "openui",
    usage_out: dict[str, Any] | None = None,
) -> str:
    """Streaming de declaraciones individuales, emitiendo ui_block por cada una."""
    backend = get_render_backend(backend_name)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    chunks: list[str] = []
    announced: set[str] = set()
    async for delta in llm.stream(messages, temperature=..., max_tokens=..., usage_out=usage_out):
        chunks.append(delta)
        if "\n" not in delta:
            continue
        text_so_far = "".join(chunks)
        for line in text_so_far.strip().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            block_id = line.split("=", 1)[0].strip()
            if block_id in announced:
                continue
            try:
                test_program = f'root = Stack([{block_id}], "md")\n{line}'
                partial = backend.parse_partial(test_program, ui_format="explanation")
                for component in partial.components:
                    if component.id == block_id and component.id not in announced:
                        announced.add(component.id)
                        await sse.publish(
                            node_channel(request_id),
                            "ui_block",
                            {"component": component.model_dump()},
                        )
            except Exception:
                continue
    return "".join(chunks)
```

---

## 6. Manejo de fallos

### 6.1 Fallos por agente

El sistema tiene un fallback para cada punto de fallo, de mayor a menor degradacion:

| Agente | Fallo | Respuesta |
|--------|-------|-----------|
| **Blueprint Architect** | LLM no devuelve JSON valido | Usar `default_blueprint()` basado en `ui_format` + `shape_hints`. Log warning. Continuar con el pipeline. |
| **Blueprint Architect** | LLM devuelve tipos de componente desconocidos | Filtrar los desconocidos. Si no queda nada, `default_blueprint()`. |
| **Content Writer** | LLM no produce declaraciones parseables | Fallo del subgrafo. El grafo exterior va al repair loop con el monolitico. |
| **Interaction Designer** | LLM no produce QuizItem valido | Servir el contenido sin quiz (explanation-only). El aprendiz aprende sin practicar. |
| **Interaction Designer** | Answer key incompleto o malformado | Fallo del subgrafo. El repair del monolitico lo arregla. |
| **Content Writer + Interaction Designer** | Ambos fallan | `fallback_seed`: la leccion v1 renderizada como `Markdown`. Red de seguridad final. |
| **Assembler** | `gate.canonicalize()` rechaza el programa | Reintentar el agente que fallo una vez. Si persiste, fallback. |
| **Assembler** | Ids no coinciden | Se montan los que hay. Warning. `validate_ui` decide si es valido. |

### 6.2 Retry: caer al monolitico

El retry loop (`MAX_UI_RETRIES = 1`) usa el monolitico, no el multi-agent:

```python
if retry:
    return await genera_ui(state)  # monolitico, con repair prompt
```

Razon: el repair prompt esta optimizado para recibir el programa anterior y los errores
del validador. Regenerar con multi-agent en el retry no aprovecharia esa informacion.

### 6.3 Invariantes de seguridad

Los tres invariantes de seguridad del docstring de `nodes.py` se mantienen intactos:

1. **Raw bytes nunca se persisten.** El Assembler produce `raw_dsl` que pasa por
   `validate_ui` -> `canonicalize` -> re-serializa. El navegador solo ve la re-serializacion.
2. **Answer key separado.** El Assembler lo separa explicitamente. `validate_ui` hace
   `split_answer_key` como siempre.
3. **Sin tools ni reactivity.** Los prompts de los agentes no mencionan reactivity.
   `check_static_only` sigue corriendo en `canonicalize`.

---

## 7. La filosofia: el aprendiz nunca espera

Seis mecanismos, cada uno cubriendo un escenario:

| Mecanismo | Cuando actua | Resultado |
|-----------|-------------|-----------|
| Primer nodo pre-generado | Al activar el curso | Todos los aprendices encuentran el nodo 1 listo. |
| Ventana deslizante de 3 | Mientras el aprendiz esta en el nodo N | N+1, N+2, N+3 se generan fire-and-forget. |
| Prefetch al abrir el curso | Al cargar `CourseView` | El primer nodo desbloqueado se pre-genera. |
| Idempotencia del backend | Siempre | Si ya hay render o generacion en vuelo, no hay trabajo duplicado. |
| Streaming invisible | Si la pre-generacion no completo | Bloques aparecen con fade-in. El aprendiz no ve "cargando". |
| `format_vector` adaptativo | Desde el nodo 2 en adelante | El contenido se adapta al perfil del aprendiz con cada interaccion. |

El sistema aprende de los eventos del aprendiz: `quiz_correct`, `quiz_wrong`,
`scroll_slow`, `scroll_fast`, `explain_click`, `expand`, `view`. Cada evento tiene un
peso fijo (0.30 para `explain_click`, 0.20 para `quiz_correct`, etc.) y alimenta un
vector de 4 dimensiones que decae con el tiempo (ventana de 30 dias). Ese vector
determina que tipo de contenido recibe el aprendiz.

---

## 8. SSE y streaming parcial

### 8.1 Eventos durante multi-agent

El subgrafo emite `render_step` con mensajes que informan al frontend de la fase actual:

| Fase | Mensaje SSE |
|------|-------------|
| Blueprint | "Disenando la estructura..." |
| Content Writer | "Escribiendo el contenido..." |
| Interaction Designer | "Disenando las preguntas..." |
| Assembler | (sin mensaje: es instantaneo) |

Estos mensajes solo se ven si la pre-generacion no completo a tiempo. En el caso
normal (cache hit), la respuesta es directa y no hay SSE de generacion.

### 8.2 Streaming parcial de bloques

- **Content Writer:** Cada declaracion completada se parsea y se emite como
  `ui_block`, exactamente como el monolitico. El contenido aparece bloque a bloque.
- **Interaction Designer:** Igual que el Content Writer, pero para bloques interactivos.
- El `root` no se emite hasta que el Assembler lo construye, pero como el frontend ya
  conoce el orden por el streaming de los bloques individuales, la experiencia es identica.

---

## 9. Nuevo subgrafo: `genera_ui_multi`

### 9.1 Estructura del subgrafo

El nodo `genera_ui` actual se reemplaza (bajo feature flag) por una funcion que
orquesta los cuatro agentes:

```
genera_ui_multi:
    run_blueprint -> asyncio.gather(run_content_writer, run_interaction_designer) -> assemble
```

Content Writer e Interaction Designer corren en **paralelo**. No hay routing condicional:
es una cadena con un fork paralelo. Si un agente falla, el subgrafo entero falla y el
grafo exterior lo trata como un fallo de `genera_ui` (va al repair loop o al fallback,
exactamente como ahora).

### 9.2 Ficheros nuevos

```
apps/skillnet-api/src/agents/runtime/agents/
    __init__.py
    types.py              # Blueprint, BlueprintBlock, ContentOutput, InteractionOutput
    blueprint.py          # run_blueprint + prompt
    content_writer.py     # run_content_writer + prompt
    interaction_designer.py  # run_interaction_designer + prompt
    assembler.py          # assemble (sin LLM)
```

### 9.3 Integracion con el grafo existente

**Fichero modificado:** `apps/skillnet-api/src/agents/runtime/nodes.py`

Se anade una funcion `genera_ui_multi` que reemplaza `genera_ui` bajo feature flag:

```python
from src.agents.runtime.agents.blueprint import run_blueprint
from src.agents.runtime.agents.content_writer import run_content_writer
from src.agents.runtime.agents.interaction_designer import run_interaction_designer
from src.agents.runtime.agents.assembler import assemble

@runtime_node_error_wrapper("genera_ui")
async def genera_ui_multi(state: NodeRuntimeState) -> dict:
    """Version multi-agente de genera_ui. Misma firma, misma salida."""
    request_id = str(state["request_id"])
    org_id = _uuid(state["org_id"])
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    tier = str(state.get("tier") or "fast")
    ui_format = coerce_ui_format(state.get("ui_format"))
    retry = int(state.get("retry_count") or 0)

    # En retry, se cae al monolitico (el repair prompt esta optimizado para el)
    if retry:
        return await genera_ui(state)

    llm = await _make_llm(org_id, tier)
    mastery = float(node_state.get("mastery") or 0.0)
    threshold = threshold_for(
        node.get("criticality") or "recommended", node.get("mastery_threshold")
    )

    await publish_step(request_id, "genera_ui", "Disenando la estructura...")
    started = time.monotonic()

    # --- Agent 1: Blueprint ---
    blueprint = await run_blueprint(
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        outcome=node.get("outcome"),
        criticality=str(node.get("criticality") or "recommended"),
        ui_format=ui_format,
        effective_density=int(state.get("effective_density") or 3),
        scaffold_band=str(state.get("scaffold_band") or "neutral"),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        experience_level=str(profile.get("experience_level") or "unknown"),
        target_bloom=target_bloom(mastery, threshold),
        shape_hints=list(state.get("shape_hints") or ()),
        llm=llm,
    )
    tokens_in_total = 0
    tokens_out_total = 0

    await publish_step(request_id, "genera_ui", "Escribiendo el contenido...")

    # --- Agents 2+3: Content Writer + Interaction Designer (PARALELO) ---
    content_coro = run_content_writer(
        blueprint=blueprint,
        title=str(node.get("title") or ""),
        summary=str(node.get("summary") or ""),
        source_context=str(state.get("source_context") or ""),
        role_title=profile.get("role_title"),
        sector=profile.get("sector"),
        scaffold_band=str(state.get("scaffold_band") or "neutral"),
        criticality=str(node.get("criticality") or "recommended"),
        llm=llm,
    )

    interaction_coro = None
    interaction_blocks = [b for b in blueprint.blocks if b.type in ("QuizItem", "DragOrder")]
    if interaction_blocks:
        await publish_step(request_id, "genera_ui", "Disenando las preguntas...")
        interaction_coro = run_interaction_designer(
            blueprint=blueprint,
            content_declarations="",  # paralelo: aun no hay contenido
            title=str(node.get("title") or ""),
            summary=str(node.get("summary") or ""),
            source_context=str(state.get("source_context") or ""),
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            target_bloom=target_bloom(mastery, threshold),
            scaffold_band=str(state.get("scaffold_band") or "neutral"),
            llm=llm,
        )

    # Ejecutar en paralelo
    if interaction_coro:
        content_output, interaction_output = await asyncio.gather(
            content_coro, interaction_coro
        )
    else:
        content_output = await content_coro
        interaction_output = None

    # --- Agent 4: Assembler ---
    raw_dsl, answer_key_from_assembler = assemble(
        blueprint=blueprint,
        content_output=content_output,
        interaction_output=interaction_output,
        ui_format=ui_format,
    )

    duration_ms = int((time.monotonic() - started) * 1000)

    return {
        "raw_dsl": raw_dsl,
        "model": getattr(llm, "model", "unknown"),
        "duration_ms": duration_ms + int(state.get("duration_ms") or 0),
        "tokens_in": _accumulate(state.get("tokens_in"), tokens_in_total or None),
        "tokens_out": _accumulate(state.get("tokens_out"), tokens_out_total or None),
        "current_step": "genera_ui",
    }
```

---

## 10. Feature flag y migracion

### 10.1 Feature flag

**Fichero:** `apps/skillnet-api/src/config.py`

```python
# Multi-agent pipeline (experimental)
MULTI_AGENT_RENDER: bool = Field(default=False, env="MULTI_AGENT_RENDER")
```

**Fichero:** `apps/skillnet-api/src/agents/runtime/graph.py`

```python
from src.config import settings

def build_node_graph():
    graph = StateGraph(NodeRuntimeState)

    # Elegir la implementacion de genera_ui
    if settings.MULTI_AGENT_RENDER:
        from src.agents.runtime.nodes import genera_ui_multi
        graph.add_node("genera_ui", genera_ui_multi)
    else:
        graph.add_node("genera_ui", genera_ui)

    # ... resto del grafo identico
```

### 10.2 Comportamiento segun el flag

| Valor de `MULTI_AGENT_RENDER` | Comportamiento |
|-------------------------------|----------------|
| `false` (default) | Monolitico. Todo como hoy. |
| `true` | Multi-agent en el primer intento. Monolitico en el retry. |

### 10.3 Cache key

El cache key NO cambia. La cache se invalida por `PROMPT_VERSION` (que ya se bumpa cuando
cambian los prompts). El multi-agent produce el mismo `raw_dsl` que pasa por el mismo
`validate_ui`, `canonicalize` y `persist_render`.

La clave de cache incluye la version del pipeline, asi que no hay contaminacion cruzada
entre renders generados por el monolitico y el multi-agent:

```python
PROMPT_VERSION = "runtime/12"  # multi-agent pipeline
```

### 10.4 Rollback

Una linea. Poner `MULTI_AGENT_RENDER=false` en el `.env`. No necesita reiniciar: el grafo
se recompila en cada invocacion (`build_node_graph()` se llama por request).

### 10.5 Plan de despliegue

1. **Fase 1: Implementar y testear offline.**
   - Crear `src/agents/runtime/agents/` con los cuatro modulos.
   - Tests unitarios para cada agente con fixtures.
   - Test de integracion del flujo completo con `MULTI_AGENT_RENDER=true`.

2. **Fase 2: Banco de calidad comparativo.**
   - Correr `scripts/quality_bench.py` con `MULTI_AGENT_RENDER=false` (baseline).
   - Correr con `MULTI_AGENT_RENDER=true` (multi-agent).
   - Comparar: cobertura de catalogo, acierto a la primera, tokens, latencia.
   - Criterio de aceptacion: cobertura > 50 %, acierto > 70 %, latencia < 150 % del monolitico.

3. **Fase 3: Activar por defecto.**
   - Cambiar default de `MULTI_AGENT_RENDER` a `true`.
   - Monitorizar en produccion durante 1 semana.
   - Si regresion > 10 % en cualquier metrica, revertir a `false`.

---

## 11. Cache key

El cache key NO cambia de forma. La funcion `build_cache_key` en
`apps/skillnet-api/src/services/cache_key.py` sigue siendo la unica autoridad, y se llama
desde exactamente dos sitios: el check pre-grafo en `NodeRenderService` y `load_context`
dentro del grafo.

Lo que cambia es el `PROMPT_VERSION`, que ya forma parte de la clave. Al activar el
multi-agent se bumpa a `"runtime/12"`, lo que invalida toda la cache del monolitico
sin tocar la logica de hashing.

---

## 12. Detalle de tokens por agente

### 12.1 Agent 1: Blueprint Architect

| Campo | Tokens estimados |
|-------|-----------------|
| System prompt | ~400 |
| User prompt | ~300 |
| **Total entrada** | **~700** |
| Salida (JSON) | ~150-300 |
| max_tokens | 512 |
| temperature | 0.2 |

### 12.2 Agent 2: Content Writer

| Campo | Tokens estimados |
|-------|-----------------|
| System prompt (dialecto + reglas) | ~1 200 |
| User prompt (blueprint + fuente) | ~1 300 |
| **Total entrada** | **~2 500** |
| Salida (declaraciones) | ~300-600 |
| max_tokens fast/heavy | 800 / 1 600 |
| temperature | 0.4 |

### 12.3 Agent 3: Interaction Designer

| Campo | Tokens estimados |
|-------|-----------------|
| System prompt (dialecto + reglas quiz) | ~1 000 |
| User prompt (blueprint + contenido + fuente recortada) | ~1 000 |
| **Total entrada** | **~2 000** |
| Salida (declaraciones + answer key) | ~200-400 |
| max_tokens fast/heavy | 600 / 1 200 |
| temperature | 0.3 |

### 12.4 Comparativa con monolitico

| | Monolitico | Multi-agent |
|--|-----------|-------------|
| Llamadas LLM | 1 (+ 1 si repair) | 3 (+ 1 si repair) |
| Tokens entrada (total) | ~5 250 | ~5 200 |
| Tokens salida (total) | ~800 | ~1 100 |
| Tokens si repair | ~10 500 + ~1 600 | ~5 200 + ~5 250 + ~800 (monolitico en retry) |
| Fuente en el prompt | 1 vez, completa | 1 vez completa (Agent 2) + 1 vez recortada (Agent 3) |

La ventaja real esta en la tasa de reparaciones: si el multi-agent sube el acierto a
la primera del 30-65 % al 70-90 %, el coste total baja porque se eliminan los retries
(que hoy cuestan una segunda llamada completa).

---

## 13. Tests

### 13.1 Tests unitarios nuevos

```
apps/skillnet-api/tests/unit/test_blueprint_agent.py
apps/skillnet-api/tests/unit/test_content_writer_agent.py
apps/skillnet-api/tests/unit/test_interaction_designer_agent.py
apps/skillnet-api/tests/unit/test_assembler.py
```

Cada test usa un fixture LLM (`fixture/local`) que devuelve respuestas predefinidas.

### 13.2 Tests de integracion

```
apps/skillnet-api/tests/integration/test_multi_agent_pipeline.py
```

- Test de flujo completo con `MULTI_AGENT_RENDER=true`.
- Test de fallback al monolitico en retry.
- Test de que los invariantes de seguridad se mantienen (answer key separado, canonicalize).

### 13.3 Banco de calidad

El banco existente (`scripts/quality_bench.py`) funciona sin cambios: el multi-agent
produce la misma salida (`raw_dsl` + answer key) que el monolitico, y el banco mide
el resultado final.

---

## 14. Futuro multimodal (v3)

### 14.1 Vision

Una misma fuente documental genera multiples formatos de contenido:

| Formato | Descripcion |
|---------|-------------|
| Leccion interactiva | El formato actual: texto + quiz (v2). |
| Explicacion en audio | Conversacion estilo NotebookLM, no TTS robotico. Dos voces discuten el concepto. |
| Tarjetas de repaso | Flashcards generadas del mismo material. Spaced repetition integrado. |
| Diagrama | Representacion visual del concepto (mermaid, d3, o SVG generado). |
| Video explicativo | Diapositivas narradas con el audio conversacional como banda sonora. |

### 14.2 Deteccion de formato optimo

El sistema detecta que formato funciona para cada aprendiz y ofrece mas de ese.
El `format_vector` actual tiene 4 dimensiones; en v3 se expande a 6-7:

| Dimension | Actual | v3 |
|-----------|--------|-----|
| visual | Si | Si |
| textual | Si | Si |
| interactivo | Si | Si |
| ejemplo | Si | Si |
| auditivo | - | Nuevo |
| espacial (diagramas) | - | Nuevo |
| repeticion (flashcards) | - | Nuevo |

Los eventos del aprendiz (`audio_play`, `audio_complete`, `flashcard_flip`,
`diagram_zoom`) alimentan las nuevas dimensiones del vector.

### 14.3 Arquitectura

El mismo pipeline multi-agent, con agentes adicionales:

```
Blueprint Architect
        |
    +---+---+---+
    |   |   |   |
Content  Quiz  Audio  Diagram    (paralelo)
Writer   Desn  Script  Generator
    |   |   |   |
    +---+---+---+
        |
    Multi-format Assembler
```

El Blueprint Architect decide no solo la estructura de la leccion sino que formatos
se generan para este nodo, basandose en el `format_vector` del aprendiz.

---

## 15. Decisiones de diseno

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| Agents 2+3 en **paralelo** | Secuencial con gap | Default: paralelo (OpenAI). Flag para secuenciar si se usa Groq free tier (6k TPM). |
| Blueprint como JSON, no como DSL | Blueprint como OpenUI Lang parcial | JSON es mas facil de parsear y validar; el modelo no necesita conocer la sintaxis del dialecto para decidir la estructura. |
| Retry cae al monolitico | Retry repite multi-agent | El repair prompt esta optimizado para el flujo de una sola salida. El multi-agent no aprovecha los errores del validador porque cada agente hizo solo una parte. |
| Los tres agentes comparten el mismo LLM | Agent 1 usa "fast", agents 2+3 usan el tier del formato | Simplifica y evita decisiones de routing. El blueprint es tan barato que no justifica un tier separado. |
| No tocar `validate_ui` ni `persist_render` | Duplicar la validacion por agente | La cadena produce el mismo `raw_dsl` que el monolitico; no hay razon para cambiar nada despues del Assembler. |
| Source context solo en Agent 2 (completo) y Agent 3 (recortado) | Fuente en los tres | El Blueprint no necesita la fuente (decide por `shape_hints`). Ahorrar ~1 500 tokens de entrada por render. |
| Feature flag de entorno | Flag por organizacion | Complejidad innecesaria en la primera iteracion. Todas las organizaciones usan el mismo flag. |
| Primer nodo generico (sin perfil) | Esperar al primer aprendiz | Todos los aprendices encuentran el nodo 1 listo. La adaptacion empieza en el nodo 2, cuando hay datos. |
| Ventana deslizante de 3 (no mas) | Pre-generar todo el curso | Los nodos mas adelante se benefician de mas datos del aprendiz. Pre-generar todo desperdicia adaptacion. |
| Streaming invisible (sin indicadores) | Skeleton screens / progress bars | El aprendiz no debe saber que hay generacion. La UX es "contenido que aparece", no "contenido que se genera". |

---

## 16. Checklist de implementacion

Cada item es una unidad de trabajo independiente y testeable:

- [ ] `src/agents/runtime/agents/__init__.py` — Paquete vacio.
- [ ] `src/agents/runtime/agents/types.py` — `Blueprint`, `BlueprintBlock`, `ContentOutput`, `InteractionOutput`.
- [ ] `src/agents/runtime/agents/blueprint.py` — `run_blueprint`, `default_blueprint`, `BLUEPRINT_SYSTEM`, `build_blueprint_prompt`.
- [ ] `src/agents/runtime/agents/content_writer.py` — `run_content_writer`, `content_writer_system`, `build_content_prompt`.
- [ ] `src/agents/runtime/agents/interaction_designer.py` — `run_interaction_designer`, `interaction_designer_system`, `build_interaction_prompt`.
- [ ] `src/agents/runtime/agents/assembler.py` — `assemble`.
- [ ] `src/agents/runtime/nodes.py` — `genera_ui_multi`.
- [ ] `src/config.py` — `MULTI_AGENT_RENDER`.
- [ ] `src/agents/runtime/graph.py` — Feature flag en `build_node_graph`.
- [ ] `src/llm/prompts/runtime.py` — Bump `PROMPT_VERSION`.
- [ ] `tests/unit/test_blueprint_agent.py`
- [ ] `tests/unit/test_content_writer_agent.py`
- [ ] `tests/unit/test_interaction_designer_agent.py`
- [ ] `tests/unit/test_assembler.py`
- [ ] `tests/integration/test_multi_agent_pipeline.py`
- [ ] Correr `quality_bench.py` con ambos modos y documentar resultados.

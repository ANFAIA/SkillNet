---
title: "SNML spec"
order: 32
section: "core"
---

# SNML: SkillNet Markup Language Specification

> **Status: v1.** Complete format specification for SkillNet training content. Defines a Markdown-compatible authoring format with embedded interactive components and exercises.

Depends on: [data-model.md](data-model.md), [content-generation.md](content-generation.md), [screens.md](screens.md).

---

## 1. Overview

SNML is a content format for SkillNet training materials. It is valid Markdown at its core with extended fenced blocks (`:::`) for interactive components. Any standard Markdown renderer displays SNML as readable, well-structured text. The SkillNet web app renders it with interactive widgets, quiz logic, and visual components.

**Design goals:**

1. **Valid Markdown.** Every SNML document is valid CommonMark. Extended blocks use `:::` fences that Markdown renderers treat as unrecognized containers (ignored or rendered as `<div>` in most implementations). No custom sigils, no invented syntax.
2. **AI-generatable.** The format is line-oriented, uses familiar key: value pairs, and avoids deeply nested structures. An LLM can produce it in a single pass.
3. **Human-readable and editable.** A non-technical admin can read and modify SNML in any text editor. No JSON to escape, no YAML indentation traps.
4. **Parseable.** A regex-based or line-by-line parser can extract all components. No AST required for basic extraction.
5. **Heading-based structure.** The heading tree (`# > ## > ###`) defines the TOC, navigation, and chunking boundaries. This matches the `Course > Module > Lesson` hierarchy.
6. **Two rendering modes.** Doc mode (static reference) and Web mode (interactive exercises, visual components).

**What SNML is NOT:**

- Not a general-purpose document format. It is purpose-built for SkillNet training content.
- Not a replacement for the database. SNML is a transport/authoring format. Content is stored in PostgreSQL as structured data (see [data-model.md](data-model.md)). SNML is how content enters and exits the system.
- Not a templating language. No variables, loops, or conditionals.

---

## 2. Document Structure

Every SNML document represents one **lesson**. A course is a collection of SNML files organized by module. The heading hierarchy maps directly to the data model:

```
---
(YAML frontmatter: lesson metadata)
---

# Lesson Title              --> lessons.title
## Section heading           --> visual structure within lesson
### Sub-section              --> deeper structure (optional)

:::component                 --> interactive block
...
:::

Regular markdown text        --> lessons.content
```

### 2.1 Frontmatter (Lesson Metadata)

Every SNML document begins with YAML frontmatter. This maps directly to database fields.

```yaml
---
title: "Plazos y condiciones de devolucion"
module: "Fundamentos de la Politica"
module_position: 1
lesson_position: 1
estimated_minutes: 3
bloom_level: understand
skills_covered:
  - devoluciones
source_documents:
  - title: "Manual de Devoluciones v3"
    pages: "1-5"
---
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Lesson title. Maps to `lessons.title`. |
| `module` | string | Parent module name. Maps to `modules.title`. |
| `module_position` | int | Module position in course. Maps to `modules.position`. |
| `lesson_position` | int | Lesson position within module. Maps to `lessons.position`. |

**Optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `estimated_minutes` | int | Estimated completion time in minutes. |
| `bloom_level` | string | Target Bloom level: `remember`, `understand`, `apply`, `analyze`, `evaluate`, `create`. |
| `skills_covered` | string[] | Skill names this lesson teaches. Maps to `skills.name`. |
| `source_documents` | object[] | Source documents with page references. For citation traceability. |

### 2.2 Heading Hierarchy

Headings define the internal structure of the lesson:

```markdown
# Lesson Title

Body text goes here.

## Section within lesson

More content.

### Sub-section

Details.
```

**Rules:**

- `#` (H1) is the lesson title. Must match `title` in frontmatter. Exactly one per document.
- `##` (H2) sections are visual groupings within the lesson. Used for TOC within the lesson view.
- `###` (H3) and below are sub-sections. Optional.
- Component blocks (`:::`) can appear at any level.
- Exercises can appear at any point in the document, but typically appear after the related content.

### 2.3 Course-Level Metadata File

Each course has a single `_course.snml` file (not a lesson) that holds course-wide metadata:

```yaml
---
type: course
title: "Politica de Devoluciones"
description: "Curso completo sobre el proceso de devolucion en tienda"
outcome: "Gestionar devoluciones de principio a fin, incluyendo casos excepcionales y clientes dificiles"
estimated_minutes: 45
difficulty: basic
status: draft
created_by: "Juan Garcia"
source_document: "Manual de Devoluciones v3.pdf"
modules:
  - title: "Fundamentos de la Politica"
    position: 1
    summary: "Plazos, condiciones y documentacion necesaria"
  - title: "Casos Practicos"
    position: 2
    summary: "Escenarios reales del dia a dia en tienda"
  - title: "Evaluacion Final"
    position: 3
    summary: "Test final y caso integrador"
skills:
  - name: devoluciones
    category: Ventas
    checkpoints:
      - module: "Fundamentos de la Politica"
        target_level: low
      - module: "Casos Practicos"
        target_level: medium
      - module: "Evaluacion Final"
        target_level: high
---

# Politica de Devoluciones

Al terminar este curso, podras gestionar devoluciones de principio a fin, incluyendo casos excepcionales y clientes dificiles.
```

This file is only used for course assembly. It is NOT rendered as a lesson.

---

## 3. Component Block Syntax

All extended components use the triple-colon fenced block syntax (`:::`). This follows the [generic directives proposal](https://talk.commonmark.org/t/generic-directives-plugins-syntax/444) from CommonMark — the same syntax used by VuePress, Docusaurus, and MyST.

### 3.1 General Syntax

```
:::component_type{key=value key2=value2}
Content of the block.
Supports multiple lines.
Can contain **markdown** formatting.
:::
```

**Rules:**

1. Opening fence: `:::` followed by the component type name, optionally followed by `{attributes}`.
2. Content: everything between the opening and closing `:::`.
3. Closing fence: `:::` on its own line.
4. Attributes use `key=value` syntax. Values with spaces must be quoted: `key="multi word value"`.
5. Blocks cannot be nested (a `:::` block cannot contain another `:::` block). This keeps parsing simple.
6. Blank lines inside blocks are preserved.

### 3.2 Graceful Degradation

When rendered by a standard Markdown renderer that does not understand `:::` fences:

- **Best case** (renderers that support generic directives): The block renders as a styled `<div>` with a class matching the component type.
- **Typical case** (most renderers): The `:::` lines are treated as text. The content inside is rendered as normal Markdown.
- **Worst case**: The raw text is displayed. Since the content uses readable key: value pairs, it remains comprehensible.

Example of how a `:::test` block degrades:

```
In a :::test-aware renderer:
  [Interactive quiz widget]

In a standard Markdown renderer:
  :::test
  question: How many days for returns?
  - [ ] 14 days
  - [x] 30 days
  - [ ] 60 days
  - [ ] 90 days
  explanation: Manual de Devoluciones, pag. 3
  :::
```

The degraded output is readable: a question with options (checkboxes in Markdown syntax), the correct answer marked with `[x]`, and an explanation.

---

## 4. Visual Components

### 4.1 `:::metrics` — Key Metrics Display

Displays a row of metric cards with large numbers and labels. Used for course overview stats, module summaries, or business context.

**Syntax:**

```
:::metrics
30 dias | Plazo devolucion
3 documentos | Necesarios
85% | Tasa aceptacion
:::
```

**Format:** Each line is one metric card: `value | label`. The `|` separates the displayed value from its description.

**Attributes (optional):**

```
:::metrics{columns=4 style=highlight}
...
:::
```

| Attribute | Default | Values | Description |
|-----------|---------|--------|-------------|
| `columns` | `auto` | `2`, `3`, `4`, `auto` | Number of columns in the grid. `auto` fits to content count. |
| `style` | `default` | `default`, `highlight`, `minimal` | Visual style variant. |

**Graceful degradation (plain Markdown):**

```
30 dias | Plazo devolucion
3 documentos | Necesarios
85% | Tasa aceptacion
```

Renders as three lines of text. The pipe makes it look like a simple table row.

**Web rendering:** A responsive card grid. Each metric renders as a Card component (from the design system) with the value in large typography and the label below it in muted text.

**Parse output (JSON):**

```json
{
  "type": "metrics",
  "attrs": {"columns": "auto", "style": "default"},
  "items": [
    {"value": "30 dias", "label": "Plazo devolucion"},
    {"value": "3 documentos", "label": "Necesarios"},
    {"value": "85%", "label": "Tasa aceptacion"}
  ]
}
```

---

### 4.2 `:::cards` — Card Grid

Displays content in a grid of cards. Each card has a title, body, and optional icon.

**Syntax:**

```
:::cards

#### Con ticket
Devolucion directa. Verificar producto, escanear, reembolsar.
Plazo: 30 dias naturales.

#### Sin ticket (con extracto)
Aceptar extracto bancario como comprobante.
Verificar importe y fecha.

#### Producto defectuoso
Derivar a garantia del fabricante.
Plazo de garantia: 2 anhos.

:::
```

**Format:** Each card is a `####` heading followed by body text. The heading becomes the card title. Everything until the next `####` or `:::` is the card body (supports Markdown).

**Attributes (optional):**

```
:::cards{columns=3 icon=true}
...
:::
```

| Attribute | Default | Values | Description |
|-----------|---------|--------|-------------|
| `columns` | `auto` | `2`, `3`, `4`, `auto` | Grid columns. |
| `icon` | `false` | `true`, `false` | If true, the first emoji or image in the title is extracted as a card icon. |

**Graceful degradation:** Renders as a series of H4 headings with body paragraphs. Perfectly readable.

**Web rendering:** A responsive grid of Card components. Each card has a header with the title and body with the Markdown content rendered.

**Parse output (JSON):**

```json
{
  "type": "cards",
  "attrs": {"columns": "auto"},
  "items": [
    {
      "title": "Con ticket",
      "body": "Devolucion directa. Verificar producto, escanear, reembolsar.\nPlazo: 30 dias naturales."
    },
    {
      "title": "Sin ticket (con extracto)",
      "body": "Aceptar extracto bancario como comprobante.\nVerificar importe y fecha."
    },
    {
      "title": "Producto defectuoso",
      "body": "Derivar a garantia del fabricante.\nPlazo de garantia: 2 anhos."
    }
  ]
}
```

---

### 4.3 `:::table` — Styled Table

A Markdown table with optional styling attributes. This exists because plain Markdown tables cannot express styling hints (highlight rows, alignment, captions).

**Syntax:**

```
:::table{caption="Tipos de comprobante aceptados" highlight=1}
| Comprobante | Valido | Notas |
|---|---|---|
| Ticket original | Si | Preferido |
| Extracto bancario | Si | Verificar importe |
| Captura de email | No | No es comprobante oficial |
:::
```

**Format:** Standard Markdown table inside the block. The `:::table` wrapper adds attributes.

| Attribute | Default | Description |
|-----------|---------|-------------|
| `caption` | none | Table caption displayed above or below. |
| `highlight` | none | Comma-separated row indices (0-based, excluding header) to highlight. |
| `sortable` | `false` | If `true`, web mode renders sortable column headers. |
| `compact` | `false` | If `true`, reduces padding for dense tables. |

**Graceful degradation:** A standard Markdown table. The `:::table` lines and attributes are ignored. The table itself renders normally.

**Web rendering:** A styled HTML table with optional features: caption, highlighted rows, sortable columns.

**Parse output (JSON):**

```json
{
  "type": "table",
  "attrs": {"caption": "Tipos de comprobante aceptados", "highlight": "1"},
  "headers": ["Comprobante", "Valido", "Notas"],
  "rows": [
    ["Ticket original", "Si", "Preferido"],
    ["Extracto bancario", "Si", "Verificar importe"],
    ["Captura de email", "No", "No es comprobante oficial"]
  ]
}
```

---

### 4.4 `:::callout` — Important Info Callout

Highlights important information, warnings, tips, or references to source material.

**Syntax:**

```
:::callout{type=warning}
Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8.
:::
```

**Types:**

| Type | Use | Icon (web) | Color (web) |
|------|-----|------------|-------------|
| `info` (default) | General information | `i` circle | Blue (#3661A5) |
| `warning` | Important caveats | `!` triangle | Amber |
| `tip` | Helpful advice | Lightbulb | Green (#4BA862) |
| `danger` | Critical rules, errors | `x` circle | Red |
| `source` | Citation to source material | Document icon | Gray |

**Graceful degradation:**

```
> **Warning:** Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8.
```

A parser can optionally convert `:::callout{type=X}` to Markdown blockquotes with a bold label for doc mode. The raw form is also readable.

**Web rendering:** A styled callout box matching the SkillNet design system. Uses the brand color palette.

**Parse output (JSON):**

```json
{
  "type": "callout",
  "attrs": {"type": "warning"},
  "body": "Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8."
}
```

---

### 4.5 `:::progress` — Progress Indicator

Shows progress through the module or lesson. Typically auto-inserted by the renderer based on position, but can be explicitly placed for congratulatory milestones.

**Syntax:**

```
:::progress{value=66 label="Modulo 2 de 3 completado"}
Excelente! Ya manejas los casos basicos de devolucion.
:::
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `value` | int (0-100) | Progress percentage. |
| `label` | string | Progress label text. |

**Graceful degradation:**

```
---
**Progreso: 66%** — Modulo 2 de 3 completado
Excelente! Ya manejas los casos basicos de devolucion.
---
```

Appears as a text divider with progress info. Fully readable.

**Web rendering:** A ProgressBar component (from the design system) with the label above and the congratulatory text below.

---

## 5. Exercise Components

Exercises are the core interactive element. Each exercise block maps directly to a row in the `exercises` table (see [data-model.md](data-model.md)). The parser extracts the structured data needed for the `exercises.content` JSONB column.

### 5.1 `:::test` — Multiple Choice

**Syntax:**

```
:::test{id=ex_plazos bloom=remember}
question: Cuantos dias de plazo hay para devoluciones en nuestra tienda?

- [ ] 14 dias
- [x] 30 dias naturales
- [ ] 60 dias
- [ ] 90 dias

explanation: Manual de Devoluciones, pag. 3: "El plazo para devoluciones es de 30 dias naturales desde la fecha de compra."
:::
```

**Format rules:**

1. `question:` line followed by the question text. Can span multiple lines until the first blank line or option list.
2. Options use Markdown task list syntax:
   - `- [ ]` = incorrect option
   - `- [x]` = correct option (exactly one)
3. `explanation:` line with the explanation text. Can span multiple lines until `:::`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | string | Unique exercise identifier. Optional (auto-generated if absent). |
| `bloom` | string | Bloom taxonomy level. Optional. |
| `source` | string | Short source citation. Optional. |

**Graceful degradation (plain Markdown):**

```
**Pregunta:** Cuantos dias de plazo hay para devoluciones en nuestra tienda?

- [ ] 14 dias
- [x] 30 dias naturales
- [ ] 60 dias
- [ ] 90 dias

*Explicacion: Manual de Devoluciones, pag. 3: "El plazo para devoluciones es de 30 dias naturales desde la fecha de compra."*
```

Renders as a readable question with a checkbox list. The `[x]` reveals the correct answer. The explanation is in italics.

**Web rendering:** A quiz card with radio buttons. The correct answer is hidden until submission. After answering, shows green/red feedback and the explanation.

**Parse output (maps to `exercises.content` JSONB):**

```json
{
  "type": "test",
  "id": "ex_plazos",
  "content": {
    "question": "Cuantos dias de plazo hay para devoluciones en nuestra tienda?",
    "options": [
      "14 dias",
      "30 dias naturales",
      "60 dias",
      "90 dias"
    ],
    "correct": 1,
    "explanation": "Manual de Devoluciones, pag. 3: \"El plazo para devoluciones es de 30 dias naturales desde la fecha de compra.\""
  },
  "bloom": "remember"
}
```

---

### 5.2 `:::true_false` — True/False

**Syntax:**

```
:::true_false{id=ex_extracto bloom=remember}
statement: Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.

answer: true

explanation: Manual de Devoluciones, pag. 5: "El extracto bancario es valido como comprobante de compra."
:::
```

**Format rules:**

1. `statement:` line with the assertion to evaluate.
2. `answer:` line with `true` or `false`.
3. `explanation:` line with the explanation.

**Graceful degradation:**

```
**Verdadero o falso:** Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.

Respuesta: **Verdadero**

*Explicacion: Manual de Devoluciones, pag. 5: "El extracto bancario es valido como comprobante de compra."*
```

**Web rendering:** A statement displayed with two large buttons: "Verdadero" / "Falso". After answering, feedback and explanation are shown.

**Parse output:**

```json
{
  "type": "true_false",
  "id": "ex_extracto",
  "content": {
    "statement": "Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.",
    "correct": true,
    "explanation": "Manual de Devoluciones, pag. 5: \"El extracto bancario es valido como comprobante de compra.\""
  },
  "bloom": "remember"
}
```

---

### 5.3 `:::fill_blank` — Fill in the Blanks

**Syntax:**

```
:::fill_blank{id=ex_requisitos bloom=understand}
template: Para aceptar una devolucion, el producto debe estar ____(1) y con ____(2).

blanks:
1: sin usar
2: etiquetas

accept:
1: nuevo, sin estrenar
2: etiquetas originales, tags

explanation: Manual de Devoluciones, pag. 4: "Condiciones del producto para devolucion."
:::
```

**Format rules:**

1. `template:` line with the sentence containing `____(N)` placeholders. The number inside is the blank index.
2. `blanks:` section with numbered correct answers (one per line, `N: answer`).
3. `accept:` section (optional) with alternative accepted answers, comma-separated.
4. `explanation:` line with the explanation.

**Graceful degradation:**

```
**Completa:** Para aceptar una devolucion, el producto debe estar _____ y con _____.

Respuestas: (1) sin usar (2) etiquetas

*Explicacion: Manual de Devoluciones, pag. 4: "Condiciones del producto para devolucion."*
```

**Web rendering:** The sentence with inline text inputs replacing each blank. Auto-grading compares input against correct answers and accepted alternatives (case-insensitive, trimmed).

**Parse output:**

```json
{
  "type": "fill_blank",
  "id": "ex_requisitos",
  "content": {
    "template": "Para aceptar una devolucion, el producto debe estar ____(1) y con ____(2).",
    "blanks": ["sin usar", "etiquetas"],
    "accept": [
      ["nuevo", "sin estrenar"],
      ["etiquetas originales", "tags"]
    ],
    "explanation": "Manual de Devoluciones, pag. 4: \"Condiciones del producto para devolucion.\""
  },
  "bloom": "understand"
}
```

---

### 5.4 `:::order_steps` — Order Steps

**Syntax:**

```
:::order_steps{id=ex_proceso bloom=apply}
instruction: Ordena los pasos para procesar una devolucion estandar.

steps:
1. Verificar producto y comprobante
2. Escanear codigo de barras
3. Registrar en sistema
4. Reembolsar al cliente

explanation: Manual de Devoluciones, pag. 6: "Procedimiento paso a paso."
:::
```

**Format rules:**

1. `instruction:` line with the task description.
2. `steps:` section followed by numbered lines. The numbers represent the correct order. The web app shuffles them for display.
3. `explanation:` line with the explanation.

**Graceful degradation:**

```
**Ordena los pasos:** Ordena los pasos para procesar una devolucion estandar.

1. Verificar producto y comprobante
2. Escanear codigo de barras
3. Registrar en sistema
4. Reembolsar al cliente

*Explicacion: Manual de Devoluciones, pag. 6: "Procedimiento paso a paso."*
```

The correct order is visible in plain text, which is acceptable for doc mode (reference, not testing).

**Web rendering:** Draggable items in a random order. The user drags to reorder. On submission, checks against the correct order and shows feedback.

**Parse output:**

```json
{
  "type": "order_steps",
  "id": "ex_proceso",
  "content": {
    "instruction": "Ordena los pasos para procesar una devolucion estandar.",
    "steps": [
      "Verificar producto y comprobante",
      "Escanear codigo de barras",
      "Registrar en sistema",
      "Reembolsar al cliente"
    ],
    "correct_order": [0, 1, 2, 3],
    "explanation": "Manual de Devoluciones, pag. 6: \"Procedimiento paso a paso.\""
  },
  "bloom": "apply"
}
```

Note: `correct_order` is always `[0, 1, 2, 3, ...]` because the steps are written in the correct order in the source. The renderer shuffles for display.

---

### 5.5 `:::practical_case` — Scenario-Based Exercise

The most important exercise type (50%+ of exercises should be this or higher). Presents a realistic workplace scenario and asks the learner to decide or respond.

**Syntax:**

```
:::practical_case{id=ex_viernes bloom=apply}
context:
Viernes 18:45. Ultimos 15 minutos de tienda.
Un cliente viene con una cafetera comprada hace 45 dias.
Dice que "no funciona bien". Tiene ticket.
La caja del producto esta abierta y usada.

question: Que haces?

options:
- Aceptas la devolucion porque tiene ticket
- Explicas que han pasado mas de 30 dias pero ofreces contactar al fabricante por garantia
- Dices que no se puede hacer nada porque el producto esta usado
- Llamas al jefe para que decida

correct: 1

rubric:
- criteria: Menciona que el plazo de 30 dias no aplica
  required: true
- criteria: Ofrece alternativa de garantia del fabricante
  required: true
- criteria: Mantiene tono amable y profesional
  required: false

explanation: La politica de 30 dias no aplica (han pasado 45), pero el cliente tiene garantia del fabricante de 2 anhos. Siempre ofrecer alternativa, nunca decir "no se puede hacer nada".
[Fuente: Manual de Devoluciones, pag. 5, pag. 12]
:::
```

**Format rules:**

1. `context:` multiline block describing the scenario. Ends at the next keyword (`question:`, `options:`, etc.).
2. `question:` the question to answer.
3. `options:` list of choices (prefixed with `-`). Optional -- if absent, the exercise is open-response.
4. `correct:` zero-based index of the correct option. Required if `options:` is present.
5. `rubric:` list of evaluation criteria (for AI-graded open responses or for detailed feedback on multiple-choice). Each item has `criteria` and `required` (boolean).
6. `explanation:` multiline explanation with source citations in `[Fuente: ...]` format.

**Graceful degradation:**

```
**Caso practico:**

> Viernes 18:45. Ultimos 15 minutos de tienda.
> Un cliente viene con una cafetera comprada hace 45 dias.
> Dice que "no funciona bien". Tiene ticket.
> La caja del producto esta abierta y usada.

**Pregunta:** Que haces?

- Aceptas la devolucion porque tiene ticket
- **Explicas que han pasado mas de 30 dias pero ofreces contactar al fabricante por garantia** (correcta)
- Dices que no se puede hacer nada porque el producto esta usado
- Llamas al jefe para que decida

*Explicacion: La politica de 30 dias no aplica (han pasado 45), pero el cliente tiene garantia del fabricante de 2 anhos.*
```

The context appears as a blockquote, the correct answer is bolded, and the explanation is in italics.

**Web rendering:** A card with the scenario context in a highlighted box, the question prominently displayed, and the options as selectable buttons. On submission, shows the rubric checklist (green/red per criteria) and the full explanation.

**Parse output:**

```json
{
  "type": "practical_case",
  "id": "ex_viernes",
  "content": {
    "context": "Viernes 18:45. Ultimos 15 minutos de tienda.\nUn cliente viene con una cafetera comprada hace 45 dias.\nDice que \"no funciona bien\". Tiene ticket.\nLa caja del producto esta abierta y usada.",
    "question": "Que haces?",
    "options": [
      "Aceptas la devolucion porque tiene ticket",
      "Explicas que han pasado mas de 30 dias pero ofreces contactar al fabricante por garantia",
      "Dices que no se puede hacer nada porque el producto esta usado",
      "Llamas al jefe para que decida"
    ],
    "correct": 1,
    "rubric": [
      {"criteria": "Menciona que el plazo de 30 dias no aplica", "required": true},
      {"criteria": "Ofrece alternativa de garantia del fabricante", "required": true},
      {"criteria": "Mantiene tono amable y profesional", "required": false}
    ],
    "explanation": "La politica de 30 dias no aplica (han pasado 45), pero el cliente tiene garantia del fabricante de 2 anhos. Siempre ofrecer alternativa, nunca decir \"no se puede hacer nada\".\n[Fuente: Manual de Devoluciones, pag. 5, pag. 12]"
  },
  "bloom": "apply"
}
```

---

### 5.6 `:::dialogue` — Conversational Exercise

AI-driven conversational exercise where the learner interacts with a simulated character (angry customer, new employee, etc.). This is the most advanced exercise type.

**Syntax:**

```
:::dialogue{id=ex_enfadado bloom=apply max_turns=4}
context:
Viernes 19:00. Ultimo turno de la semana.
Un cliente viene muy enfadado. Dice que es la tercera vez
que viene y "siempre hay un problema". Quiere hablar con el jefe.

system_prompt:
Eres un cliente enfadado en una tienda de ropa. Es la tercera vez
que vienes esta semana por un problema con una devolucion. Estas
frustrado y quieres hablar con el encargado. Empiezas agresivo pero
te calmas si el empleado es amable y ofrece soluciones concretas.
Si el empleado es cortante o no ofrece alternativas, te enfadas mas.

opening: Esto es el colmo! Ya es la tercera vez que vengo y nadie me resuelve. Quiero hablar con tu jefe!

evaluation_criteria:
- Mantiene tono amable y profesional en todo momento
- Ofrece solucion concreta antes de derivar al encargado
- Muestra empatia con la frustracion del cliente
- No cede a presiones irrazonables

explanation: En situaciones de conflicto, lo prioritario es mantener la calma, mostrar empatia, y ofrecer una solucion concreta. Solo derivar al encargado cuando el caso lo requiera, no por presion del cliente.
:::
```

**Format rules:**

1. `context:` multiline scenario description (for the learner).
2. `system_prompt:` multiline prompt for the AI playing the character. This is NOT shown to the learner.
3. `opening:` the first message from the AI character. This starts the conversation.
4. `evaluation_criteria:` list of criteria (prefixed with `-`) used by the AI to evaluate the learner's performance after the conversation ends.
5. `explanation:` post-exercise explanation and learning points.
6. Attribute `max_turns` controls how many exchanges before the conversation ends.

**Graceful degradation:**

```
**Dialogo simulado:**

> Viernes 19:00. Ultimo turno de la semana.
> Un cliente viene muy enfadado. Es la tercera vez que viene.

**Cliente:** "Esto es el colmo! Ya es la tercera vez que vengo y nadie me resuelve. Quiero hablar con tu jefe!"

**Tu respuesta:** _(escribe tu respuesta)_

**Criterios de evaluacion:**
- Mantiene tono amable y profesional en todo momento
- Ofrece solucion concreta antes de derivar al encargado
- Muestra empatia con la frustracion del cliente
- No cede a presiones irrazonables
```

In doc mode, the exercise appears as a readable scenario with the evaluation criteria visible. The learner can self-assess.

**Web rendering:** A chat interface. The AI's opening message appears first. The learner types responses. After `max_turns` exchanges, the AI evaluates the conversation against the criteria and gives structured feedback.

**Parse output:**

```json
{
  "type": "dialogue",
  "id": "ex_enfadado",
  "content": {
    "context": "Viernes 19:00. Ultimo turno de la semana.\nUn cliente viene muy enfadado. Dice que es la tercera vez\nque viene y \"siempre hay un problema\". Quiere hablar con el jefe.",
    "system_prompt": "Eres un cliente enfadado en una tienda de ropa. Es la tercera vez\nque vienes esta semana por un problema con una devolucion. Estas\nfrustrado y quieres hablar con el encargado. Empiezas agresivo pero\nte calmas si el empleado es amable y ofrece soluciones concretas.\nSi el empleado es cortante o no ofrece alternativas, te enfadas mas.",
    "opening": "Esto es el colmo! Ya es la tercera vez que vengo y nadie me resuelve. Quiero hablar con tu jefe!",
    "max_turns": 4,
    "evaluation_criteria": [
      "Mantiene tono amable y profesional en todo momento",
      "Ofrece solucion concreta antes de derivar al encargado",
      "Muestra empatia con la frustracion del cliente",
      "No cede a presiones irrazonables"
    ],
    "explanation": "En situaciones de conflicto, lo prioritario es mantener la calma, mostrar empatia, y ofrecer una solucion concreta. Solo derivar al encargado cuando el caso lo requiera, no por presion del cliente."
  },
  "bloom": "apply"
}
```

---

## 6. Complete SNML Example

A full lesson document demonstrating all component types:

```markdown
---
title: "Plazos y condiciones de devolucion"
module: "Fundamentos de la Politica"
module_position: 1
lesson_position: 1
estimated_minutes: 5
bloom_level: understand
skills_covered:
  - devoluciones
source_documents:
  - title: "Manual de Devoluciones v3"
    pages: "1-8"
---

# Plazos y condiciones de devolucion

En esta leccion aprenderemos las reglas basicas de la politica de devoluciones de nuestra tienda: plazos, documentos necesarios y condiciones del producto.

:::metrics
30 dias | Plazo maximo
3 tipos | Comprobantes validos
100% estado | Producto sin usar
:::

## Plazo de devolucion

El cliente tiene **30 dias naturales** desde la fecha de compra para solicitar una devolucion. Este plazo es inamovible: no importa si el cliente es habitual, si tiene excusa, o si el producto es caro.

:::callout{type=warning}
El plazo de 30 dias se cuenta desde la fecha del ticket, no desde el dia que el cliente "dice" que compro. Siempre verificar fecha en el comprobante.
[Fuente: Manual de Devoluciones, pag. 3]
:::

## Documentos necesarios

Para aceptar una devolucion, necesitamos al menos uno de estos comprobantes:

:::table{caption="Comprobantes aceptados para devoluciones"}
| Comprobante | Valido | Notas |
|---|---|---|
| Ticket original | Si | Preferido. Contiene fecha, producto e importe. |
| Extracto bancario | Si | Verificar que el importe y fecha coinciden. |
| Email de confirmacion | Solo online | Solo para compras por la web. |
| Captura de pantalla | No | No es documento oficial. |
:::

:::callout{type=source}
Manual de Devoluciones, pag. 5: "Se aceptan como comprobante valido: ticket de compra, extracto bancario del pago, o email de confirmacion de pedido online."
:::

## Condiciones del producto

El producto debe cumplir estas condiciones para aceptar la devolucion:

:::cards

#### Sin usar
El producto no puede haber sido utilizado. En ropa, significa sin lavar, sin planchar, sin manchas. En electronica, sin marcas de uso.

#### Con etiquetas
Todas las etiquetas originales deben estar intactas. Si faltan etiquetas, no se acepta.

#### Embalaje original
Preferible pero no obligatorio. Si el producto viene sin caja pero cumple las demas condiciones, se puede aceptar.

:::

## Ejercicios

Comprueba que has entendido las reglas basicas.

:::test{id=ex_plazo bloom=remember}
question: Cuantos dias de plazo hay para devoluciones en nuestra tienda?

- [ ] 14 dias
- [x] 30 dias naturales
- [ ] 60 dias
- [ ] 90 dias

explanation: Manual de Devoluciones, pag. 3: "El plazo para devoluciones es de 30 dias naturales desde la fecha de compra."
:::

:::true_false{id=ex_extracto bloom=remember}
statement: Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.

answer: true

explanation: Manual de Devoluciones, pag. 5: "El extracto bancario es valido como comprobante de compra."
:::

:::fill_blank{id=ex_condiciones bloom=understand}
template: Para aceptar una devolucion, el producto debe estar ____(1) y con ____(2).

blanks:
1: sin usar
2: etiquetas

accept:
1: nuevo, sin estrenar, sin utilizar
2: etiquetas originales, tags, las etiquetas

explanation: Manual de Devoluciones, pag. 4: "El producto debe estar sin usar y con todas las etiquetas originales intactas."
:::

:::progress{value=33 label="Leccion 1 de 3 completada"}
Buen trabajo! Ahora conoces las reglas basicas de devoluciones. En la siguiente leccion veremos los casos especiales.
:::
```

---

## 7. Rendering Modes

### 7.1 Doc Mode (Static Reference)

For generating printable documents, PDF exports, or rendering in environments without JavaScript.

**Rules:**

1. Render all standard Markdown normally.
2. Convert `:::callout` blocks to blockquotes with bold type prefix.
3. Convert `:::metrics` to a simple table or bulleted list.
4. Convert `:::cards` to a series of H4 headings with body text.
5. Convert `:::table` to a standard Markdown table (drop attributes).
6. Convert `:::progress` to a horizontal rule with label text.
7. For exercises:
   - Show the question text.
   - Show options with the correct answer marked.
   - Show the explanation.
   - For `:::dialogue`, show context, opening, and evaluation criteria.
8. Strip all `{attributes}` from the output.

**Doc mode transform (pseudo-code):**

```python
def to_doc_mode(snml: str) -> str:
    """Convert SNML to clean Markdown for static rendering."""
    result = []
    for block in parse_blocks(snml):
        if block.type == "markdown":
            result.append(block.content)
        elif block.type == "callout":
            label = block.attrs.get("type", "info").capitalize()
            result.append(f"> **{label}:** {block.body}")
        elif block.type == "metrics":
            for item in block.items:
                result.append(f"- **{item.value}** — {item.label}")
        elif block.type == "cards":
            for card in block.items:
                result.append(f"#### {card.title}\n\n{card.body}")
        elif block.type == "table":
            result.append(block.raw_table)  # pass through
        elif block.type == "progress":
            result.append(f"---\n**Progreso: {block.attrs['value']}%** — {block.attrs['label']}\n{block.body}\n---")
        elif block.type in EXERCISE_TYPES:
            result.append(render_exercise_doc_mode(block))
    return "\n\n".join(result)
```

### 7.2 Web Mode (Interactive)

For the SkillNet web app (React frontend).

**Rules:**

1. Parse SNML into a list of content blocks.
2. Render standard Markdown blocks with a Markdown renderer (e.g., `react-markdown`).
3. Render `:::` blocks with dedicated React components:
   - `MetricsGrid` for `:::metrics`
   - `CardGrid` for `:::cards`
   - `StyledTable` for `:::table`
   - `Callout` for `:::callout`
   - `ProgressBar` for `:::progress`
   - `TestExercise` for `:::test`
   - `TrueFalseExercise` for `:::true_false`
   - `FillBlankExercise` for `:::fill_blank`
   - `OrderStepsExercise` for `:::order_steps`
   - `PracticalCaseExercise` for `:::practical_case`
   - `DialogueExercise` for `:::dialogue`
4. Exercise components handle user interaction, answer submission, and feedback display.
5. On answer submission, the component sends `POST /api/v1/exercises/{id}/attempt` with the answer data.

**React rendering (pseudo-code):**

```tsx
function LessonRenderer({ snml }: { snml: string }) {
  const blocks = parseSNML(snml);

  return (
    <article className="lesson-content">
      {blocks.map((block, i) => {
        switch (block.type) {
          case "markdown":
            return <Markdown key={i}>{block.content}</Markdown>;
          case "metrics":
            return <MetricsGrid key={i} items={block.items} {...block.attrs} />;
          case "cards":
            return <CardGrid key={i} items={block.items} {...block.attrs} />;
          case "table":
            return <StyledTable key={i} headers={block.headers} rows={block.rows} {...block.attrs} />;
          case "callout":
            return <Callout key={i} type={block.attrs.type}>{block.body}</Callout>;
          case "progress":
            return <ProgressIndicator key={i} value={block.attrs.value} label={block.attrs.label}>{block.body}</ProgressIndicator>;
          case "test":
            return <TestExercise key={i} data={block.content} id={block.id} />;
          case "true_false":
            return <TrueFalseExercise key={i} data={block.content} id={block.id} />;
          case "fill_blank":
            return <FillBlankExercise key={i} data={block.content} id={block.id} />;
          case "order_steps":
            return <OrderStepsExercise key={i} data={block.content} id={block.id} />;
          case "practical_case":
            return <PracticalCaseExercise key={i} data={block.content} id={block.id} />;
          case "dialogue":
            return <DialogueExercise key={i} data={block.content} id={block.id} />;
          default:
            return null;
        }
      })}
    </article>
  );
}
```

---

## 8. Parsing Strategy

### 8.1 Parser Architecture

The parser is a single-pass, line-oriented state machine. No AST is needed. It processes the document line by line and emits a flat list of typed blocks.

```
Input: SNML string
Output: Block[]

Block = {
  type: "markdown" | "metrics" | "cards" | "table" | "callout" |
        "progress" | "test" | "true_false" | "fill_blank" |
        "order_steps" | "practical_case" | "dialogue",
  content: string,          // raw content (for markdown blocks)
  attrs: Record<string, string>,  // parsed {key=value} attributes
  items?: any[],            // parsed structured data (for components)
  id?: string,              // exercise ID
  position: number,         // block order in document
  line_start: number,       // source line number (for error reporting)
  line_end: number,
}
```

### 8.2 Parsing Algorithm

```python
import re
from dataclasses import dataclass, field
from typing import Optional

# Regex patterns
FENCE_OPEN = re.compile(r'^:::(\w+)(?:\{(.+?)\})?$')
FENCE_CLOSE = re.compile(r'^:::$')
FRONTMATTER_FENCE = re.compile(r'^---$')
HEADING = re.compile(r'^(#{1,6})\s+(.+)$')

COMPONENT_TYPES = {
    "metrics", "cards", "table", "callout", "progress",
    "test", "true_false", "fill_blank", "order_steps",
    "practical_case", "dialogue",
}

EXERCISE_TYPES = {
    "test", "true_false", "fill_blank", "order_steps",
    "practical_case", "dialogue",
}

@dataclass
class Block:
    type: str
    content: str
    attrs: dict = field(default_factory=dict)
    line_start: int = 0
    line_end: int = 0
    position: int = 0

@dataclass
class ParseResult:
    frontmatter: dict          # Parsed YAML frontmatter
    blocks: list[Block]        # Ordered content blocks
    headings: list[dict]       # [{level, text, line}] for TOC
    exercises: list[dict]      # Extracted exercise data for grading
    errors: list[str]          # Parse warnings/errors


def parse_snml(source: str) -> ParseResult:
    """Parse an SNML document into structured blocks."""

    lines = source.split('\n')
    result = ParseResult(
        frontmatter={},
        blocks=[],
        headings=[],
        exercises=[],
        errors=[],
    )

    i = 0
    position = 0

    # --- Phase 1: Extract frontmatter ---
    if i < len(lines) and FRONTMATTER_FENCE.match(lines[i]):
        i += 1
        fm_lines = []
        while i < len(lines) and not FRONTMATTER_FENCE.match(lines[i]):
            fm_lines.append(lines[i])
            i += 1
        if i < len(lines):
            i += 1  # skip closing ---
        result.frontmatter = parse_yaml('\n'.join(fm_lines))

    # --- Phase 2: Process body ---
    markdown_buffer = []
    md_start_line = i

    while i < len(lines):
        line = lines[i]

        # Check for heading (extract for TOC regardless of context)
        heading_match = HEADING.match(line)
        if heading_match:
            result.headings.append({
                "level": len(heading_match.group(1)),
                "text": heading_match.group(2),
                "line": i + 1,
            })

        # Check for component fence opening
        fence_match = FENCE_OPEN.match(line)
        if fence_match:
            component_type = fence_match.group(1)
            attrs_str = fence_match.group(2)

            if component_type in COMPONENT_TYPES:
                # Flush markdown buffer
                if markdown_buffer:
                    result.blocks.append(Block(
                        type="markdown",
                        content='\n'.join(markdown_buffer),
                        line_start=md_start_line + 1,
                        line_end=i,
                        position=position,
                    ))
                    position += 1
                    markdown_buffer = []

                # Collect component content
                attrs = parse_attrs(attrs_str) if attrs_str else {}
                comp_start = i + 1
                comp_lines = []
                i += 1

                while i < len(lines) and not FENCE_CLOSE.match(lines[i]):
                    comp_lines.append(lines[i])
                    i += 1

                comp_content = '\n'.join(comp_lines)

                block = Block(
                    type=component_type,
                    content=comp_content,
                    attrs=attrs,
                    line_start=comp_start,
                    line_end=i + 1,
                    position=position,
                )
                result.blocks.append(block)
                position += 1

                # Extract exercise data if applicable
                if component_type in EXERCISE_TYPES:
                    exercise_data = parse_exercise(component_type, comp_content, attrs)
                    if exercise_data:
                        result.exercises.append(exercise_data)
                    else:
                        result.errors.append(
                            f"Line {comp_start}: Failed to parse {component_type} exercise"
                        )

                md_start_line = i + 1
                i += 1
                continue

        # Regular line: add to markdown buffer
        markdown_buffer.append(line)
        i += 1

    # Flush remaining markdown
    if markdown_buffer:
        content = '\n'.join(markdown_buffer)
        if content.strip():  # Don't emit empty blocks
            result.blocks.append(Block(
                type="markdown",
                content=content,
                line_start=md_start_line + 1,
                line_end=len(lines),
                position=position,
            ))

    return result


def parse_attrs(attrs_str: str) -> dict:
    """Parse {key=value key2="multi word"} attribute string."""
    attrs = {}
    # Match key=value or key="value with spaces"
    pattern = re.compile(r'(\w+)=(?:"([^"]+)"|(\S+))')
    for match in pattern.finditer(attrs_str):
        key = match.group(1)
        value = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[key] = value
    return attrs
```

### 8.3 Exercise Parsers

Each exercise type has a dedicated parser that extracts structured data from the block content.

```python
def parse_exercise(ex_type: str, content: str, attrs: dict) -> dict | None:
    """Dispatch to type-specific parser."""
    parsers = {
        "test": parse_test_exercise,
        "true_false": parse_true_false_exercise,
        "fill_blank": parse_fill_blank_exercise,
        "order_steps": parse_order_steps_exercise,
        "practical_case": parse_practical_case_exercise,
        "dialogue": parse_dialogue_exercise,
    }
    parser = parsers.get(ex_type)
    if not parser:
        return None
    return parser(content, attrs)


def parse_test_exercise(content: str, attrs: dict) -> dict:
    """Parse :::test block content."""
    lines = content.strip().split('\n')

    question = ""
    options = []
    correct = -1
    explanation = ""

    section = None  # "question", "options", "explanation"

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("question:"):
            section = "question"
            question = stripped[len("question:"):].strip()
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        # Option line
        option_match = re.match(r'^-\s+\[([ x])\]\s+(.+)$', stripped)
        if option_match:
            section = "options"
            is_correct = option_match.group(1) == 'x'
            option_text = option_match.group(2)
            if is_correct:
                correct = len(options)
            options.append(option_text)
            continue

        # Continuation of current section
        if section == "question" and stripped:
            question += " " + stripped
        elif section == "explanation" and stripped:
            explanation += " " + stripped

    return {
        "type": "test",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "question": question,
            "options": options,
            "correct": correct,
            "explanation": explanation,
        },
    }


def parse_true_false_exercise(content: str, attrs: dict) -> dict:
    """Parse :::true_false block content."""
    lines = content.strip().split('\n')

    statement = ""
    answer = None
    explanation = ""
    section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("statement:"):
            section = "statement"
            statement = stripped[len("statement:"):].strip()
            continue

        if stripped.startswith("answer:"):
            section = "answer"
            answer = stripped[len("answer:"):].strip().lower() == "true"
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        if section == "statement" and stripped:
            statement += " " + stripped
        elif section == "explanation" and stripped:
            explanation += " " + stripped

    return {
        "type": "true_false",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "statement": statement,
            "correct": answer,
            "explanation": explanation,
        },
    }


def parse_fill_blank_exercise(content: str, attrs: dict) -> dict:
    """Parse :::fill_blank block content."""
    lines = content.strip().split('\n')

    template = ""
    blanks = {}
    accept = {}
    explanation = ""
    section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("template:"):
            section = "template"
            template = stripped[len("template:"):].strip()
            continue

        if stripped == "blanks:":
            section = "blanks"
            continue

        if stripped == "accept:":
            section = "accept"
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        if section == "template" and stripped:
            template += " " + stripped
            continue

        if section == "blanks":
            match = re.match(r'^(\d+):\s*(.+)$', stripped)
            if match:
                blanks[int(match.group(1))] = match.group(2).strip()
            continue

        if section == "accept":
            match = re.match(r'^(\d+):\s*(.+)$', stripped)
            if match:
                alts = [a.strip() for a in match.group(2).split(',')]
                accept[int(match.group(1))] = alts
            continue

        if section == "explanation" and stripped:
            explanation += " " + stripped

    # Convert to ordered lists
    max_blank = max(blanks.keys()) if blanks else 0
    blanks_list = [blanks.get(i, "") for i in range(1, max_blank + 1)]
    accept_list = [accept.get(i, []) for i in range(1, max_blank + 1)]

    return {
        "type": "fill_blank",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "template": template,
            "blanks": blanks_list,
            "accept": accept_list,
            "explanation": explanation,
        },
    }


def parse_order_steps_exercise(content: str, attrs: dict) -> dict:
    """Parse :::order_steps block content."""
    lines = content.strip().split('\n')

    instruction = ""
    steps = []
    explanation = ""
    section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("instruction:"):
            section = "instruction"
            instruction = stripped[len("instruction:"):].strip()
            continue

        if stripped == "steps:":
            section = "steps"
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        if section == "instruction" and stripped:
            instruction += " " + stripped
            continue

        if section == "steps":
            match = re.match(r'^\d+\.\s+(.+)$', stripped)
            if match:
                steps.append(match.group(1))
            continue

        if section == "explanation" and stripped:
            explanation += " " + stripped

    return {
        "type": "order_steps",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "instruction": instruction,
            "steps": steps,
            "correct_order": list(range(len(steps))),
            "explanation": explanation,
        },
    }


def parse_practical_case_exercise(content: str, attrs: dict) -> dict:
    """Parse :::practical_case block content."""
    lines = content.strip().split('\n')

    context = ""
    question = ""
    options = []
    correct = -1
    rubric = []
    explanation = ""
    section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("context:"):
            section = "context"
            rest = stripped[len("context:"):].strip()
            if rest:
                context = rest
            continue

        if stripped.startswith("question:"):
            section = "question"
            question = stripped[len("question:"):].strip()
            continue

        if stripped == "options:":
            section = "options"
            continue

        if stripped.startswith("correct:"):
            section = "correct"
            correct = int(stripped[len("correct:"):].strip())
            continue

        if stripped == "rubric:":
            section = "rubric"
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        if section == "context" and stripped:
            context += "\n" + stripped
            continue

        if section == "question" and stripped:
            question += " " + stripped
            continue

        if section == "options":
            match = re.match(r'^-\s+(.+)$', stripped)
            if match:
                options.append(match.group(1))
            continue

        if section == "rubric":
            match = re.match(r'^-\s+criteria:\s+(.+)$', stripped)
            if match:
                rubric.append({"criteria": match.group(1), "required": True})
                continue
            # Check for required: false on indented line
            req_match = re.match(r'^\s+required:\s+(true|false)$', stripped)
            if req_match and rubric:
                rubric[-1]["required"] = req_match.group(1) == "true"
            continue

        if section == "explanation" and stripped:
            explanation += "\n" + stripped

    result = {
        "type": "practical_case",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "context": context.strip(),
            "question": question,
            "rubric": rubric,
            "explanation": explanation.strip(),
        },
    }

    if options:
        result["content"]["options"] = options
        result["content"]["correct"] = correct

    return result


def parse_dialogue_exercise(content: str, attrs: dict) -> dict:
    """Parse :::dialogue block content."""
    lines = content.strip().split('\n')

    context = ""
    system_prompt = ""
    opening = ""
    evaluation_criteria = []
    explanation = ""
    section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("context:"):
            section = "context"
            rest = stripped[len("context:"):].strip()
            if rest:
                context = rest
            continue

        if stripped.startswith("system_prompt:"):
            section = "system_prompt"
            rest = stripped[len("system_prompt:"):].strip()
            if rest:
                system_prompt = rest
            continue

        if stripped.startswith("opening:"):
            section = "opening"
            opening = stripped[len("opening:"):].strip()
            continue

        if stripped == "evaluation_criteria:":
            section = "evaluation_criteria"
            continue

        if stripped.startswith("explanation:"):
            section = "explanation"
            explanation = stripped[len("explanation:"):].strip()
            continue

        if section == "context" and stripped:
            context += "\n" + stripped
            continue

        if section == "system_prompt" and stripped:
            system_prompt += "\n" + stripped
            continue

        if section == "opening" and stripped:
            opening += " " + stripped
            continue

        if section == "evaluation_criteria":
            match = re.match(r'^-\s+(.+)$', stripped)
            if match:
                evaluation_criteria.append(match.group(1))
            continue

        if section == "explanation" and stripped:
            explanation += "\n" + stripped

    return {
        "type": "dialogue",
        "id": attrs.get("id"),
        "bloom": attrs.get("bloom"),
        "content": {
            "context": context.strip(),
            "system_prompt": system_prompt.strip(),
            "opening": opening,
            "max_turns": int(attrs.get("max_turns", 4)),
            "evaluation_criteria": evaluation_criteria,
            "explanation": explanation.strip(),
        },
    }
```

### 8.4 Extraction Functions

High-level functions for common extraction tasks:

```python
def extract_heading_tree(result: ParseResult) -> list[dict]:
    """Build a hierarchical heading tree for TOC/navigation.

    Returns a nested structure:
    [
      {"level": 1, "text": "Lesson Title", "children": [
        {"level": 2, "text": "Section", "children": [
          {"level": 3, "text": "Sub-section", "children": []}
        ]}
      ]}
    ]
    """
    tree = []
    stack = [{"level": 0, "children": tree}]

    for heading in result.headings:
        node = {
            "level": heading["level"],
            "text": heading["text"],
            "line": heading["line"],
            "children": [],
        }

        # Pop stack until parent level is found
        while stack[-1]["level"] >= heading["level"]:
            stack.pop()

        stack[-1]["children"].append(node)
        stack.append(node)

    return tree


def extract_exercises(result: ParseResult) -> list[dict]:
    """Extract all exercises with their grading data.

    Returns the list of exercise dicts ready for insertion
    into the exercises.content JSONB column.
    """
    return result.exercises


def extract_visual_components(result: ParseResult) -> list[dict]:
    """Extract non-exercise components for rich rendering."""
    visual_types = {"metrics", "cards", "table", "callout", "progress"}
    return [
        block.__dict__
        for block in result.blocks
        if block.type in visual_types
    ]


def extract_plain_markdown(result: ParseResult) -> str:
    """Extract only the Markdown content blocks, joined.

    Useful for full-text search indexing or doc mode without
    any component rendering.
    """
    md_blocks = [
        block.content
        for block in result.blocks
        if block.type == "markdown"
    ]
    return "\n\n".join(md_blocks)
```

### 8.5 SNML-to-Database Pipeline

How SNML content flows from generation to database storage:

```
LLM generates SNML string
    |
    v
parse_snml(snml_string) --> ParseResult
    |
    +--> result.frontmatter     --> lessons.title, modules.title, position, etc.
    +--> result.blocks          --> lessons.content (full SNML stored as text)
    +--> result.exercises       --> exercises rows (type + content JSONB)
    +--> result.headings        --> Used for TOC rendering, not stored separately
    |
    v
INSERT INTO lessons (title, content, position)
    VALUES (frontmatter.title, full_snml_string, frontmatter.lesson_position);

FOR EACH exercise IN result.exercises:
    INSERT INTO exercises (lesson_id, type, content, position)
        VALUES (lesson.id, exercise.type, exercise.content, exercise.position);
```

**Key decision:** The full SNML string is stored in `lessons.content`. The exercises are ALSO extracted and stored as separate rows in the `exercises` table. This means:

- **Rendering:** Load lesson content (SNML), parse it, render blocks with React components.
- **Grading:** Load exercise rows directly. No need to parse SNML for grading.
- **Editing:** Update the SNML string. Re-parse to update exercise rows.

This is denormalized by design. The SNML is the source of truth for display. The exercise rows are a derived index for grading and progress tracking.

---

## 9. AI Generation Prompt

This is the system prompt for the Module Generator agent (see [content-generation.md](content-generation.md), section 3.4) when generating SNML output.

### 9.1 System Prompt

```
You are a training content writer creating workplace learning materials in
SNML (SkillNet Markup Language) format. SNML is Markdown with embedded
interactive components using ::: fenced blocks.

## Output Format

Your output must be a complete SNML document with:
1. YAML frontmatter (title, module, positions, estimated_minutes, bloom_level, skills_covered)
2. An H1 heading matching the title
3. Body content mixing Markdown text with SNML components
4. At least one exercise per lesson

## Available Components

### Visual components
- :::metrics — Key stats (format: "value | label" per line)
- :::cards — Card grid (#### heading per card, body text below)
- :::table{caption="..."} — Styled table (standard Markdown table inside)
- :::callout{type=info|warning|tip|danger|source} — Important info box
- :::progress{value=N label="..."} — Progress indicator with message

### Exercise components
- :::test{id=ID bloom=LEVEL} — Multiple choice (question:, - [ ] / - [x], explanation:)
- :::true_false{id=ID bloom=LEVEL} — True/false (statement:, answer:, explanation:)
- :::fill_blank{id=ID bloom=LEVEL} — Fill blanks (template: with ____(N), blanks:, accept:, explanation:)
- :::order_steps{id=ID bloom=LEVEL} — Order steps (instruction:, steps: numbered, explanation:)
- :::practical_case{id=ID bloom=LEVEL} — Scenario (context:, question:, options:, correct:, rubric:, explanation:)
- :::dialogue{id=ID bloom=LEVEL max_turns=N} — AI conversation (context:, system_prompt:, opening:, evaluation_criteria:, explanation:)

## Content Rules

1. Write in the SAME LANGUAGE as the source material.
2. Every factual claim must have a citation: [Fuente: document_title, pag. N]
3. Use :::callout{type=source} for direct quotes from source material.
4. Exercise IDs must be unique and descriptive: ex_[topic]_[number]
5. At least 50% of exercises must be "apply" level or higher (practical_case, dialogue, order_steps).
6. Maximum 2 minutes of reading before an exercise. If a section is long, break it up with exercises.
7. Use :::metrics at the start of the lesson for key stats.
8. Use :::cards for comparing categories or listing related items.
9. Use :::callout{type=warning} for critical rules the employee must not forget.
10. End the lesson with a :::progress block if it is not the last lesson in the module.
11. Do NOT invent information. Every fact must come from the source material.
12. Do NOT nest ::: blocks inside other ::: blocks.
13. Keep language simple and direct. The audience is employees, not academics.
14. Use the company's own terminology and product names from the source material.

## Exercise Distribution by Bloom Level

- remember (10%): :::test, :::true_false — for definitions, basic facts
- understand (20%): :::fill_blank, :::true_false — for explaining concepts
- apply (50%): :::practical_case, :::dialogue, :::order_steps — for real scenarios
- analyze (15%): :::practical_case — for diagnosing problems
- evaluate (5%): :::practical_case — for choosing best approach

## Structure Rules

- Start with a brief intro paragraph (2-3 sentences)
- Use ## for sections within the lesson
- Each section: explanation + example/visual + exercise
- End with a summary or progress indicator
```

### 9.2 Example Input and Output

**Input (source material excerpt from PDF):**

```
El jefe pasa este texto al sistema:

---
MANUAL DE DEVOLUCIONES - TiendaRopa S.L.
Version 3.0 - Mayo 2026

1. PLAZO DE DEVOLUCION
El plazo para devoluciones es de 30 dias naturales desde la fecha de compra.
No se admiten excepciones al plazo, salvo defectos de fabricacion (ver seccion 4).

2. COMPROBANTES ACEPTADOS
Se aceptan como comprobante valido:
- Ticket de compra (preferido)
- Extracto bancario del pago (verificar importe y fecha)
- Email de confirmacion de pedido online

No se acepta: capturas de pantalla, fotos del ticket, recibos de otro establecimiento.

3. CONDICIONES DEL PRODUCTO
El producto debe estar:
- Sin usar (ropa sin lavar, electronica sin marcas de uso)
- Con todas las etiquetas originales intactas
- Con embalaje original (preferible pero no obligatorio)

EXCEPCION: Los productos de higiene personal no admiten devolucion bajo
ninguna circunstancia, incluso si estan sin abrir.
---
```

**Output (SNML generated by LLM):**

```markdown
---
title: "Reglas basicas de devolucion"
module: "Fundamentos de la Politica"
module_position: 1
lesson_position: 1
estimated_minutes: 5
bloom_level: understand
skills_covered:
  - devoluciones
source_documents:
  - title: "Manual de Devoluciones v3"
    pages: "1-3"
---

# Reglas basicas de devolucion

En esta leccion aprenderemos las tres reglas fundamentales para gestionar devoluciones: el plazo, los comprobantes necesarios, y el estado del producto. Estas reglas se aplican a todas las devoluciones sin excepcion.

:::metrics
30 dias | Plazo maximo de devolucion
3 tipos | Comprobantes validos
0 excepciones | Productos de higiene
:::

## Plazo de devolucion

El cliente tiene **30 dias naturales** desde la fecha de compra para solicitar una devolucion. Este plazo es inamovible: no importa si el cliente es habitual, si tiene excusa, o si el producto es caro.

:::callout{type=warning}
El plazo de 30 dias se cuenta desde la fecha del ticket, no desde el dia que el cliente diga. Siempre verificar la fecha en el comprobante.
[Fuente: Manual de Devoluciones v3, pag. 1]
:::

La unica excepcion al plazo son los **defectos de fabricacion**, que se gestionan por otra via (garantia del fabricante).

:::test{id=ex_plazo_01 bloom=remember}
question: Cuantos dias de plazo tiene un cliente para devolver un producto?

- [ ] 14 dias
- [x] 30 dias naturales
- [ ] 60 dias
- [ ] No hay plazo, depende del producto

explanation: Manual de Devoluciones v3, pag. 1: "El plazo para devoluciones es de 30 dias naturales desde la fecha de compra."
:::

## Comprobantes aceptados

No basta con que el cliente diga que compro aqui. Necesitamos un comprobante valido:

:::table{caption="Comprobantes para devoluciones en TiendaRopa S.L."}
| Comprobante | Valido | Cuando usarlo |
|---|---|---|
| Ticket de compra | Si | Siempre preferido. Tiene fecha, producto e importe. |
| Extracto bancario | Si | Si perdio el ticket. Verificar importe y fecha. |
| Email de confirmacion | Si (solo online) | Solo para compras hechas por la web. |
| Captura de pantalla | No | No es documento oficial. Rechazar educadamente. |
| Foto del ticket | No | No se acepta. Pedir el ticket original. |
:::

:::callout{type=source}
"Se aceptan como comprobante valido: ticket de compra, extracto bancario del pago, o email de confirmacion de pedido online."
[Fuente: Manual de Devoluciones v3, pag. 2]
:::

:::true_false{id=ex_extracto_01 bloom=remember}
statement: El extracto bancario del cliente es un comprobante valido para procesar una devolucion.

answer: true

explanation: Manual de Devoluciones v3, pag. 2: El extracto bancario se acepta siempre que se verifique que el importe y la fecha coinciden con la compra.
:::

## Condiciones del producto

Ademas del plazo y el comprobante, el producto debe cumplir condiciones:

:::cards

#### Sin usar
El producto no puede haber sido utilizado. En ropa: sin lavar, sin planchar, sin manchas. En electronica: sin marcas de uso.

#### Con etiquetas
Todas las etiquetas originales deben estar intactas. Si faltan etiquetas, no se acepta la devolucion.

#### Embalaje original
Preferible pero no obligatorio. Si el producto viene sin caja pero cumple las demas condiciones, se puede aceptar.

:::

:::callout{type=danger}
Los productos de **higiene personal** NO admiten devolucion bajo ninguna circunstancia, incluso si estan sin abrir. Esta regla no tiene excepciones.
[Fuente: Manual de Devoluciones v3, pag. 3]
:::

:::fill_blank{id=ex_condiciones_01 bloom=understand}
template: Para aceptar una devolucion, el producto debe estar ____(1) y con ____(2) originales intactas.

blanks:
1: sin usar
2: etiquetas

accept:
1: nuevo, sin estrenar, sin utilizar
2: las etiquetas, etiquetas originales, tags

explanation: Manual de Devoluciones v3, pag. 3: "El producto debe estar sin usar y con todas las etiquetas originales intactas."
:::

## Caso practico

Apliquemos lo aprendido a una situacion real:

:::practical_case{id=ex_caso_basico_01 bloom=apply}
context:
Martes 11:00. Poca gente en la tienda.
Una clienta viene con un vestido comprado hace 15 dias.
Tiene el ticket de compra. El vestido tiene todas las etiquetas
pero se nota un poco de olor a perfume.

question: Aceptas la devolucion?

options:
- Si, porque tiene ticket y esta dentro del plazo de 30 dias
- Si, pero advirtiendo que la proxima vez el producto debe estar completamente sin usar
- No, porque el olor a perfume indica que se ha usado
- Llamas al encargado para que decida

correct: 2

rubric:
- criteria: Identifica que el olor a perfume indica uso del producto
  required: true
- criteria: Aplica la regla de "producto sin usar" correctamente
  required: true
- criteria: Comunica el rechazo de forma educada
  required: false

explanation: El vestido tiene olor a perfume, lo que indica que se ha usado (se lo probo con perfume puesto). La regla dice "sin usar: ropa sin lavar, sin planchar, sin manchas" y el olor a perfume es equivalente a una mancha (senal de uso). Se rechaza la devolucion educadamente y se explica el motivo.
[Fuente: Manual de Devoluciones v3, pag. 3]
:::

:::progress{value=33 label="Leccion 1 de 3 completada"}
Buen trabajo! Ya conoces las reglas basicas de devoluciones. En la siguiente leccion veremos los casos especiales y excepciones.
:::
```

---

## 10. File Organization

### 10.1 Course Directory Structure

When a course is exported or managed as files (catalog, Git repo, admin export):

```
politica-devoluciones/
  _course.snml                    # Course metadata
  01-fundamentos/
    _module.yaml                  # Module metadata (position, summary)
    01-reglas-basicas.snml        # Lesson 1
    02-casos-especiales.snml      # Lesson 2
    03-excepciones.snml           # Lesson 3
  02-casos-practicos/
    _module.yaml
    01-cliente-con-ticket.snml
    02-sin-ticket.snml
    03-producto-defectuoso.snml
    04-cliente-enfadado.snml
  03-evaluacion/
    _module.yaml
    01-test-final.snml
```

### 10.2 Module Metadata (`_module.yaml`)

```yaml
title: "Fundamentos de la Politica"
position: 1
summary: "Plazos, condiciones y documentacion necesaria"
```

This is minimal because lesson-level metadata carries the detail. The module file exists so the directory structure is self-describing without parsing every lesson.

---

## 11. SNML-to-JSON Conversion

For API responses and database storage, SNML can be converted to a JSON representation. This is what the frontend receives from `GET /api/v1/lessons/{id}`.

```json
{
  "id": "uuid",
  "title": "Reglas basicas de devolucion",
  "module_id": "uuid",
  "position": 1,
  "estimated_minutes": 5,
  "blocks": [
    {
      "type": "markdown",
      "content": "En esta leccion aprenderemos las tres reglas fundamentales...",
      "position": 0
    },
    {
      "type": "metrics",
      "attrs": {},
      "items": [
        {"value": "30 dias", "label": "Plazo maximo de devolucion"},
        {"value": "3 tipos", "label": "Comprobantes validos"},
        {"value": "0 excepciones", "label": "Productos de higiene"}
      ],
      "position": 1
    },
    {
      "type": "markdown",
      "content": "## Plazo de devolucion\n\nEl cliente tiene **30 dias naturales**...",
      "position": 2
    },
    {
      "type": "callout",
      "attrs": {"type": "warning"},
      "body": "El plazo de 30 dias se cuenta desde la fecha del ticket...",
      "position": 3
    },
    {
      "type": "markdown",
      "content": "La unica excepcion al plazo son los **defectos de fabricacion**...",
      "position": 4
    },
    {
      "type": "test",
      "id": "ex_plazo_01",
      "exercise_id": "uuid",
      "content": {
        "question": "Cuantos dias de plazo tiene un cliente para devolver un producto?",
        "options": ["14 dias", "30 dias naturales", "60 dias", "No hay plazo, depende del producto"],
        "option_count": 4
      },
      "position": 5
    }
  ],
  "exercise_count": 5,
  "heading_tree": [
    {
      "level": 1, "text": "Reglas basicas de devolucion", "children": [
        {"level": 2, "text": "Plazo de devolucion", "children": []},
        {"level": 2, "text": "Comprobantes aceptados", "children": []},
        {"level": 2, "text": "Condiciones del producto", "children": []},
        {"level": 2, "text": "Caso practico", "children": []}
      ]
    }
  ]
}
```

**Important:** In the API response, exercise blocks do NOT include `correct`, `explanation`, `rubric`, or `system_prompt` fields. These are server-side only — they are used for grading when the learner submits an answer. This prevents the learner from inspecting the page source to find answers.

The grading fields are only returned AFTER the learner submits an attempt, in the response to `POST /api/v1/exercises/{id}/attempt`.

---

## 12. Format Versioning

The SNML format includes a version in the frontmatter for forward compatibility:

```yaml
---
snml: "1.0"
title: "..."
---
```

If `snml` is absent, the parser assumes `"1.0"`. Future versions may add new component types or modify existing ones. The parser handles unknown `:::` blocks gracefully by rendering them as plain text (markdown block).

**Version policy:**

- Minor versions (1.1, 1.2) add new component types or optional attributes. Old parsers ignore unknown types.
- Major versions (2.0) may change existing component syntax. Old parsers may not render correctly.

---

## 13. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **`:::` fenced blocks over custom syntax** | CommonMark generic directives proposal. Used by VuePress, Docusaurus, MyST. Familiar, widely understood, degrades gracefully. |
| **No nesting** | Keeps parsing trivial. A line-by-line state machine is sufficient. No recursive descent needed. |
| **Markdown task lists for test options** | `- [x]` and `- [ ]` are universally understood. Render as checkboxes in most Markdown renderers. The correct answer is visible in doc mode. |
| **Key: value inside blocks** | Simpler than YAML (no indentation sensitivity) and simpler than JSON (no escaping). Each line is self-describing. |
| **Exercise IDs as attributes** | Keeps them out of the visible content. Parser extracts them for database mapping. |
| **Full SNML stored in lessons.content** | The SNML string is the source of truth for rendering. Exercise rows in the `exercises` table are a derived index. This avoids having to reconstruct the lesson layout from exercise rows. |
| **Exercises extracted into separate rows** | Grading, progress tracking, spaced repetition, and analytics all need to query exercises independently. Parsing SNML on every query is too expensive. |
| **No variables or templating** | SNML is a content format, not a programming language. Personalization happens at render time (learning profiles, accessibility adaptations), not in the format itself. |
| **Multiline fields use continuation** | Lines after a `key:` are appended to the value until the next keyword or block end. This avoids needing quotes or escape characters for long text. |
| **Bloom level as exercise attribute** | The content generation pipeline needs this for distribution enforcement (50% apply+). Stored as metadata, not displayed to learners. |

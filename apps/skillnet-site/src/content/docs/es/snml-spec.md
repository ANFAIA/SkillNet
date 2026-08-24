---
title: "Especificación SNML"
order: 32
section: "core"
---

# SNML: Especificación del Lenguaje de Marcado de SkillNet

> **Estado: v1.** Especificación completa del formato para el contenido de formación de SkillNet. Define un formato de autoría compatible con Markdown con componentes interactivos y ejercicios embebidos.

Depende de: [data-model.md](data-model.md), [content-generation.md](content-generation.md), [screens.md](screens.md).

---

## 1. Visión general

SNML es un formato de contenido para los materiales de formación de SkillNet. En su núcleo es Markdown válido, extendido con bloques delimitados (`:::`) para componentes interactivos. Cualquier renderizador de Markdown estándar muestra SNML como texto legible y bien estructurado. La aplicación web de SkillNet lo renderiza con widgets interactivos, lógica de cuestionarios y componentes visuales.

**Objetivos de diseño:**

1. **Markdown válido.** Todo documento SNML es CommonMark válido. Los bloques extendidos usan delimitadores `:::` que los renderizadores de Markdown tratan como contenedores no reconocidos (se ignoran o se renderizan como `<div>` en la mayoría de las implementaciones). Sin símbolos personalizados, sin sintaxis inventada.
2. **Generable por IA.** El formato está orientado a líneas, usa pares `clave: valor` familiares y evita estructuras profundamente anidadas. Un LLM puede producirlo en una sola pasada.
3. **Legible y editable por humanos.** Un administrador no técnico puede leer y modificar SNML en cualquier editor de texto. Sin JSON que escapar, sin trampas de indentación de YAML.
4. **Analizable (parseable).** Un analizador basado en expresiones regulares o línea a línea puede extraer todos los componentes. No hace falta un AST para la extracción básica.
5. **Estructura basada en encabezados.** El árbol de encabezados (`# > ## > ###`) define el índice (TOC), la navegación y los límites de fragmentación. Esto coincide con la jerarquía `Curso > Módulo > Lección`.
6. **Dos modos de renderizado.** Modo Doc (referencia estática) y modo Web (ejercicios interactivos, componentes visuales).

**Lo que SNML NO es:**

- No es un formato de documento de propósito general. Está construido específicamente para el contenido de formación de SkillNet.
- No sustituye a la base de datos. SNML es un formato de transporte/autoría. El contenido se almacena en PostgreSQL como datos estructurados (ver [data-model.md](data-model.md)). SNML es la forma en que el contenido entra y sale del sistema.
- No es un lenguaje de plantillas. Sin variables, bucles ni condicionales.

---

## 2. Estructura del documento

Cada documento SNML representa una **lección**. Un curso es una colección de ficheros SNML organizados por módulo. La jerarquía de encabezados se corresponde directamente con el modelo de datos:

```
---
(frontmatter YAML: metadatos de la lección)
---

# Título de la lección          --> lessons.title
## Encabezado de sección        --> estructura visual dentro de la lección
### Sub-sección                 --> estructura más profunda (opcional)

:::componente                   --> bloque interactivo
...
:::

Texto markdown normal           --> lessons.content
```

### 2.1 Frontmatter (metadatos de la lección)

Todo documento SNML empieza con frontmatter YAML. Se corresponde directamente con campos de la base de datos.

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

**Campos obligatorios:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `title` | string | Título de la lección. Se mapea a `lessons.title`. |
| `module` | string | Nombre del módulo padre. Se mapea a `modules.title`. |
| `module_position` | int | Posición del módulo en el curso. Se mapea a `modules.position`. |
| `lesson_position` | int | Posición de la lección dentro del módulo. Se mapea a `lessons.position`. |

**Campos opcionales:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `estimated_minutes` | int | Tiempo estimado de finalización en minutos. |
| `bloom_level` | string | Nivel de Bloom objetivo: `remember`, `understand`, `apply`, `analyze`, `evaluate`, `create`. |
| `skills_covered` | string[] | Nombres de las habilidades que enseña esta lección. Se mapea a `skills.name`. |
| `source_documents` | object[] | Documentos fuente con referencias de página. Para trazabilidad de citas. |

### 2.2 Jerarquía de encabezados

Los encabezados definen la estructura interna de la lección:

```markdown
# Título de la lección

Aquí va el texto del cuerpo.

## Sección dentro de la lección

Más contenido.

### Sub-sección

Detalles.
```

**Reglas:**

- `#` (H1) es el título de la lección. Debe coincidir con `title` en el frontmatter. Exactamente uno por documento.
- Las secciones `##` (H2) son agrupaciones visuales dentro de la lección. Se usan para el índice dentro de la vista de la lección.
- `###` (H3) y por debajo son sub-secciones. Opcionales.
- Los bloques de componente (`:::`) pueden aparecer en cualquier nivel.
- Los ejercicios pueden aparecer en cualquier punto del documento, pero típicamente aparecen después del contenido relacionado.

### 2.3 Fichero de metadatos a nivel de curso

Cada curso tiene un único fichero `_course.snml` (que no es una lección) que contiene los metadatos de todo el curso:

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

Este fichero solo se usa para el ensamblado del curso. NO se renderiza como una lección.

---

## 3. Sintaxis de los bloques de componente

Todos los componentes extendidos usan la sintaxis de bloque delimitado por tres puntos (`:::`). Esto sigue la [propuesta de directivas genéricas](https://talk.commonmark.org/t/generic-directives-plugins-syntax/444) de CommonMark — la misma sintaxis usada por VuePress, Docusaurus y MyST.

### 3.1 Sintaxis general

```
:::tipo_componente{clave=valor clave2=valor2}
Contenido del bloque.
Admite varias líneas.
Puede contener formato **markdown**.
:::
```

**Reglas:**

1. Delimitador de apertura: `:::` seguido del nombre del tipo de componente, opcionalmente seguido de `{atributos}`.
2. Contenido: todo lo que hay entre la apertura y el cierre de `:::`.
3. Delimitador de cierre: `:::` en su propia línea.
4. Los atributos usan la sintaxis `clave=valor`. Los valores con espacios deben ir entre comillas: `clave="valor con varias palabras"`.
5. Los bloques no pueden anidarse (un bloque `:::` no puede contener otro bloque `:::`). Esto mantiene el análisis simple.
6. Las líneas en blanco dentro de los bloques se preservan.

### 3.2 Degradación elegante

Cuando lo renderiza un renderizador de Markdown estándar que no entiende los delimitadores `:::`:

- **Mejor caso** (renderizadores que soportan directivas genéricas): El bloque se renderiza como un `<div>` con estilo y una clase que coincide con el tipo de componente.
- **Caso típico** (la mayoría de renderizadores): Las líneas `:::` se tratan como texto. El contenido interior se renderiza como Markdown normal.
- **Peor caso**: Se muestra el texto en bruto. Como el contenido usa pares `clave: valor` legibles, sigue siendo comprensible.

Ejemplo de cómo se degrada un bloque `:::test`:

```
En un renderizador que entiende :::test:
  [Widget de cuestionario interactivo]

En un renderizador Markdown estándar:
  :::test
  question: How many days for returns?
  - [ ] 14 days
  - [x] 30 days
  - [ ] 60 days
  - [ ] 90 days
  explanation: Manual de Devoluciones, pag. 3
  :::
```

El resultado degradado es legible: una pregunta con opciones (casillas en sintaxis Markdown), la respuesta correcta marcada con `[x]`, y una explicación.

---

## 4. Componentes visuales

### 4.1 `:::metrics` — Visualización de métricas clave

Muestra una fila de tarjetas de métricas con números grandes y etiquetas. Se usa para estadísticas generales del curso, resúmenes de módulo o contexto de negocio.

**Sintaxis:**

```
:::metrics
30 dias | Plazo devolucion
3 documentos | Necesarios
85% | Tasa aceptacion
:::
```

**Formato:** Cada línea es una tarjeta de métrica: `valor | etiqueta`. El `|` separa el valor mostrado de su descripción.

**Atributos (opcionales):**

```
:::metrics{columns=4 style=highlight}
...
:::
```

| Atributo | Por defecto | Valores | Descripción |
|-----------|---------|--------|-------------|
| `columns` | `auto` | `2`, `3`, `4`, `auto` | Número de columnas en la cuadrícula. `auto` se ajusta al número de elementos. |
| `style` | `default` | `default`, `highlight`, `minimal` | Variante de estilo visual. |

**Degradación elegante (Markdown plano):**

```
30 dias | Plazo devolucion
3 documentos | Necesarios
85% | Tasa aceptacion
```

Se renderiza como tres líneas de texto. La barra vertical hace que parezca una fila de tabla sencilla.

**Renderizado web:** Una cuadrícula de tarjetas responsiva. Cada métrica se renderiza como un componente Card (del sistema de diseño) con el valor en tipografía grande y la etiqueta debajo en texto atenuado.

**Salida del análisis (JSON):**

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

### 4.2 `:::cards` — Cuadrícula de tarjetas

Muestra contenido en una cuadrícula de tarjetas. Cada tarjeta tiene un título, un cuerpo y un icono opcional.

**Sintaxis:**

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

**Formato:** Cada tarjeta es un encabezado `####` seguido de texto de cuerpo. El encabezado se convierte en el título de la tarjeta. Todo hasta el siguiente `####` o `:::` es el cuerpo de la tarjeta (admite Markdown).

**Atributos (opcionales):**

```
:::cards{columns=3 icon=true}
...
:::
```

| Atributo | Por defecto | Valores | Descripción |
|-----------|---------|--------|-------------|
| `columns` | `auto` | `2`, `3`, `4`, `auto` | Columnas de la cuadrícula. |
| `icon` | `false` | `true`, `false` | Si es true, el primer emoji o imagen del título se extrae como icono de la tarjeta. |

**Degradación elegante:** Se renderiza como una serie de encabezados H4 con párrafos de cuerpo. Perfectamente legible.

**Renderizado web:** Una cuadrícula responsiva de componentes Card. Cada tarjeta tiene una cabecera con el título y un cuerpo con el contenido Markdown renderizado.

**Salida del análisis (JSON):**

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

### 4.3 `:::table` — Tabla con estilo

Una tabla Markdown con atributos de estilo opcionales. Esto existe porque las tablas Markdown planas no pueden expresar indicaciones de estilo (filas resaltadas, alineación, títulos de tabla).

**Sintaxis:**

```
:::table{caption="Tipos de comprobante aceptados" highlight=1}
| Comprobante | Valido | Notas |
|---|---|---|
| Ticket original | Si | Preferido |
| Extracto bancario | Si | Verificar importe |
| Captura de email | No | No es comprobante oficial |
:::
```

**Formato:** Tabla Markdown estándar dentro del bloque. El envoltorio `:::table` añade atributos.

| Atributo | Por defecto | Descripción |
|-----------|---------|-------------|
| `caption` | ninguno | Título de la tabla mostrado arriba o abajo. |
| `highlight` | ninguno | Índices de fila separados por comas (base 0, sin contar la cabecera) a resaltar. |
| `sortable` | `false` | Si es `true`, el modo web renderiza encabezados de columna ordenables. |
| `compact` | `false` | Si es `true`, reduce el relleno para tablas densas. |

**Degradación elegante:** Una tabla Markdown estándar. Las líneas `:::table` y sus atributos se ignoran. La tabla en sí se renderiza normalmente.

**Renderizado web:** Una tabla HTML con estilo y funciones opcionales: título, filas resaltadas, columnas ordenables.

**Salida del análisis (JSON):**

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

### 4.4 `:::callout` — Aviso de información importante

Resalta información importante, avisos, consejos o referencias al material fuente.

**Sintaxis:**

```
:::callout{type=warning}
Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8.
:::
```

**Tipos:**

| Tipo | Uso | Icono (web) | Color (web) |
|------|-----|------------|-------------|
| `info` (por defecto) | Información general | círculo `i` | Azul (#3661A5) |
| `warning` | Advertencias importantes | triángulo `!` | Ámbar |
| `tip` | Consejos útiles | Bombilla | Verde (#4BA862) |
| `danger` | Reglas críticas, errores | círculo `x` | Rojo |
| `source` | Cita al material fuente | Icono de documento | Gris |

**Degradación elegante:**

```
> **Aviso:** Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8.
```

Un analizador puede opcionalmente convertir `:::callout{type=X}` en citas en bloque de Markdown con una etiqueta en negrita para el modo doc. La forma en bruto también es legible.

**Renderizado web:** Un cuadro de aviso con estilo acorde al sistema de diseño de SkillNet. Usa la paleta de colores de marca.

**Salida del análisis (JSON):**

```json
{
  "type": "callout",
  "attrs": {"type": "warning"},
  "body": "Los productos de higiene personal NO se aceptan para devolucion, independientemente del plazo. Ver Manual de Devoluciones, pag. 8."
}
```

---

### 4.5 `:::progress` — Indicador de progreso

Muestra el progreso a través del módulo o la lección. Normalmente lo inserta automáticamente el renderizador según la posición, pero puede colocarse explícitamente para hitos de felicitación.

**Sintaxis:**

```
:::progress{value=66 label="Modulo 2 de 3 completado"}
Excelente! Ya manejas los casos basicos de devolucion.
:::
```

| Atributo | Tipo | Descripción |
|-----------|------|-------------|
| `value` | int (0-100) | Porcentaje de progreso. |
| `label` | string | Texto de la etiqueta de progreso. |

**Degradación elegante:**

```
---
**Progreso: 66%** — Modulo 2 de 3 completado
Excelente! Ya manejas los casos basicos de devolucion.
---
```

Aparece como un separador de texto con la información de progreso. Totalmente legible.

**Renderizado web:** Un componente ProgressBar (del sistema de diseño) con la etiqueta arriba y el texto de felicitación debajo.

---

## 5. Componentes de ejercicio

Los ejercicios son el elemento interactivo central. Cada bloque de ejercicio se corresponde directamente con una fila de la tabla `exercises` (ver [data-model.md](data-model.md)). El analizador extrae los datos estructurados necesarios para la columna JSONB `exercises.content`.

### 5.1 `:::test` — Opción múltiple

**Sintaxis:**

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

**Reglas de formato:**

1. Línea `question:` seguida del texto de la pregunta. Puede extenderse varias líneas hasta la primera línea en blanco o la lista de opciones.
2. Las opciones usan la sintaxis de lista de tareas de Markdown:
   - `- [ ]` = opción incorrecta
   - `- [x]` = opción correcta (exactamente una)
3. Línea `explanation:` con el texto de la explicación. Puede extenderse varias líneas hasta `:::`.

**Atributos:**

| Atributo | Tipo | Descripción |
|-----------|------|-------------|
| `id` | string | Identificador único del ejercicio. Opcional (se genera automáticamente si falta). |
| `bloom` | string | Nivel de la taxonomía de Bloom. Opcional. |
| `source` | string | Cita breve de la fuente. Opcional. |

**Degradación elegante (Markdown plano):**

```
**Pregunta:** Cuantos dias de plazo hay para devoluciones en nuestra tienda?

- [ ] 14 dias
- [x] 30 dias naturales
- [ ] 60 dias
- [ ] 90 dias

*Explicacion: Manual de Devoluciones, pag. 3: "El plazo para devoluciones es de 30 dias naturales desde la fecha de compra."*
```

Se renderiza como una pregunta legible con una lista de casillas. El `[x]` revela la respuesta correcta. La explicación va en cursiva.

**Renderizado web:** Una tarjeta de cuestionario con botones de radio. La respuesta correcta está oculta hasta el envío. Tras responder, muestra retroalimentación verde/roja y la explicación.

**Salida del análisis (se mapea a `exercises.content` JSONB):**

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

### 5.2 `:::true_false` — Verdadero/falso

**Sintaxis:**

```
:::true_false{id=ex_extracto bloom=remember}
statement: Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.

answer: true

explanation: Manual de Devoluciones, pag. 5: "El extracto bancario es valido como comprobante de compra."
:::
```

**Reglas de formato:**

1. Línea `statement:` con la afirmación a evaluar.
2. Línea `answer:` con `true` o `false`.
3. Línea `explanation:` con la explicación.

**Degradación elegante:**

```
**Verdadero o falso:** Se aceptan devoluciones sin ticket si el cliente tiene extracto bancario.

Respuesta: **Verdadero**

*Explicacion: Manual de Devoluciones, pag. 5: "El extracto bancario es valido como comprobante de compra."*
```

**Renderizado web:** Una afirmación mostrada con dos botones grandes: "Verdadero" / "Falso". Tras responder, se muestran la retroalimentación y la explicación.

**Salida del análisis:**

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

### 5.3 `:::fill_blank` — Rellenar los huecos

**Sintaxis:**

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

**Reglas de formato:**

1. Línea `template:` con la frase que contiene los marcadores `____(N)`. El número interior es el índice del hueco.
2. Sección `blanks:` con las respuestas correctas numeradas (una por línea, `N: respuesta`).
3. Sección `accept:` (opcional) con respuestas alternativas aceptadas, separadas por comas.
4. Línea `explanation:` con la explicación.

**Degradación elegante:**

```
**Completa:** Para aceptar una devolucion, el producto debe estar _____ y con _____.

Respuestas: (1) sin usar (2) etiquetas

*Explicacion: Manual de Devoluciones, pag. 4: "Condiciones del producto para devolucion."*
```

**Renderizado web:** La frase con campos de texto en línea que sustituyen cada hueco. La corrección automática compara la entrada con las respuestas correctas y las alternativas aceptadas (sin distinguir mayúsculas, sin espacios sobrantes).

**Salida del análisis:**

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

### 5.4 `:::order_steps` — Ordenar pasos

**Sintaxis:**

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

**Reglas de formato:**

1. Línea `instruction:` con la descripción de la tarea.
2. Sección `steps:` seguida de líneas numeradas. Los números representan el orden correcto. La aplicación web los baraja para mostrarlos.
3. Línea `explanation:` con la explicación.

**Degradación elegante:**

```
**Ordena los pasos:** Ordena los pasos para procesar una devolucion estandar.

1. Verificar producto y comprobante
2. Escanear codigo de barras
3. Registrar en sistema
4. Reembolsar al cliente

*Explicacion: Manual de Devoluciones, pag. 6: "Procedimiento paso a paso."*
```

El orden correcto es visible en texto plano, lo cual es aceptable para el modo doc (referencia, no evaluación).

**Renderizado web:** Elementos arrastrables en orden aleatorio. El usuario arrastra para reordenar. Al enviar, comprueba contra el orden correcto y muestra retroalimentación.

**Salida del análisis:**

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

Nota: `correct_order` es siempre `[0, 1, 2, 3, ...]` porque los pasos se escriben en el orden correcto en la fuente. El renderizador los baraja para mostrarlos.

---

### 5.5 `:::practical_case` — Ejercicio basado en escenario

El tipo de ejercicio más importante (el 50% o más de los ejercicios deberían ser de este tipo o superior). Presenta un escenario laboral realista y pide al aprendiz que decida o responda.

**Sintaxis:**

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

**Reglas de formato:**

1. Bloque `context:` multilínea que describe el escenario. Termina en la siguiente palabra clave (`question:`, `options:`, etc.).
2. `question:` la pregunta a responder.
3. `options:` lista de opciones (con prefijo `-`). Opcional: si no está presente, el ejercicio es de respuesta abierta.
4. `correct:` índice base 0 de la opción correcta. Obligatorio si `options:` está presente.
5. `rubric:` lista de criterios de evaluación (para respuestas abiertas evaluadas por IA o para retroalimentación detallada en opción múltiple). Cada elemento tiene `criteria` y `required` (booleano).
6. `explanation:` explicación multilínea con citas de fuente en formato `[Fuente: ...]`.

**Degradación elegante:**

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

El contexto aparece como una cita en bloque, la respuesta correcta va en negrita y la explicación en cursiva.

**Renderizado web:** Una tarjeta con el contexto del escenario en un recuadro resaltado, la pregunta destacada de forma prominente y las opciones como botones seleccionables. Al enviar, muestra la lista de comprobación de la rúbrica (verde/rojo por criterio) y la explicación completa.

**Salida del análisis:**

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

### 5.6 `:::dialogue` — Ejercicio conversacional

Ejercicio conversacional impulsado por IA donde el aprendiz interactúa con un personaje simulado (cliente enfadado, empleado nuevo, etc.). Este es el tipo de ejercicio más avanzado.

**Sintaxis:**

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

**Reglas de formato:**

1. `context:` descripción multilínea del escenario (para el aprendiz).
2. `system_prompt:` prompt multilínea para la IA que interpreta al personaje. Esto NO se muestra al aprendiz.
3. `opening:` el primer mensaje del personaje de IA. Con esto empieza la conversación.
4. `evaluation_criteria:` lista de criterios (con prefijo `-`) que usa la IA para evaluar el desempeño del aprendiz tras finalizar la conversación.
5. `explanation:` explicación posterior al ejercicio y puntos de aprendizaje.
6. El atributo `max_turns` controla cuántos intercambios ocurren antes de que la conversación termine.

**Degradación elegante:**

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

En modo doc, el ejercicio aparece como un escenario legible con los criterios de evaluación visibles. El aprendiz puede autoevaluarse.

**Renderizado web:** Una interfaz de chat. El mensaje inicial de la IA aparece primero. El aprendiz escribe respuestas. Tras `max_turns` intercambios, la IA evalúa la conversación contra los criterios y da retroalimentación estructurada.

**Salida del análisis:**

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

## 6. Ejemplo completo de SNML

Un documento de lección completo que demuestra todos los tipos de componente:

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

## 7. Modos de renderizado

### 7.1 Modo Doc (referencia estática)

Para generar documentos imprimibles, exportaciones a PDF, o renderizar en entornos sin JavaScript.

**Reglas:**

1. Renderizar todo el Markdown estándar con normalidad.
2. Convertir los bloques `:::callout` en citas en bloque con un prefijo de tipo en negrita.
3. Convertir `:::metrics` en una tabla simple o una lista con viñetas.
4. Convertir `:::cards` en una serie de encabezados H4 con texto de cuerpo.
5. Convertir `:::table` en una tabla Markdown estándar (descartando los atributos).
6. Convertir `:::progress` en un separador horizontal con el texto de la etiqueta.
7. Para los ejercicios:
   - Mostrar el texto de la pregunta.
   - Mostrar las opciones con la respuesta correcta marcada.
   - Mostrar la explicación.
   - Para `:::dialogue`, mostrar el contexto, el mensaje inicial y los criterios de evaluación.
8. Eliminar todos los `{atributos}` de la salida.

**Transformación al modo doc (pseudocódigo):**

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

### 7.2 Modo Web (interactivo)

Para la aplicación web de SkillNet (frontend React).

**Reglas:**

1. Analizar SNML en una lista de bloques de contenido.
2. Renderizar los bloques de Markdown estándar con un renderizador de Markdown (p. ej., `react-markdown`).
3. Renderizar los bloques `:::` con componentes React dedicados:
   - `MetricsGrid` para `:::metrics`
   - `CardGrid` para `:::cards`
   - `StyledTable` para `:::table`
   - `Callout` para `:::callout`
   - `ProgressBar` para `:::progress`
   - `TestExercise` para `:::test`
   - `TrueFalseExercise` para `:::true_false`
   - `FillBlankExercise` para `:::fill_blank`
   - `OrderStepsExercise` para `:::order_steps`
   - `PracticalCaseExercise` para `:::practical_case`
   - `DialogueExercise` para `:::dialogue`
4. Los componentes de ejercicio gestionan la interacción del usuario, el envío de respuestas y la muestra de retroalimentación.
5. Al enviar una respuesta, el componente envía `POST /api/v1/exercises/{id}/attempt` con los datos de la respuesta.

**Renderizado en React (pseudocódigo):**

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

## 8. Estrategia de análisis (parsing)

### 8.1 Arquitectura del analizador

El analizador es una máquina de estados de una sola pasada, orientada a líneas. No hace falta un AST. Procesa el documento línea a línea y emite una lista plana de bloques tipados.

```
Entrada: cadena SNML
Salida: Block[]

Block = {
  type: "markdown" | "metrics" | "cards" | "table" | "callout" |
        "progress" | "test" | "true_false" | "fill_blank" |
        "order_steps" | "practical_case" | "dialogue",
  content: string,          // contenido en bruto (para bloques markdown)
  attrs: Record<string, string>,  // atributos {clave=valor} analizados
  items?: any[],            // datos estructurados analizados (para componentes)
  id?: string,              // ID del ejercicio
  position: number,         // orden del bloque en el documento
  line_start: number,       // número de línea de origen (para reportar errores)
  line_end: number,
}
```

### 8.2 Algoritmo de análisis

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

### 8.3 Analizadores de ejercicio

Cada tipo de ejercicio tiene un analizador dedicado que extrae los datos estructurados del contenido del bloque.

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

### 8.4 Funciones de extracción

Funciones de alto nivel para tareas de extracción comunes:

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

### 8.5 Pipeline de SNML a base de datos

Cómo fluye el contenido SNML desde la generación hasta el almacenamiento en base de datos:

```
El LLM genera una cadena SNML
    |
    v
parse_snml(cadena_snml) --> ParseResult
    |
    +--> result.frontmatter     --> lessons.title, modules.title, position, etc.
    +--> result.blocks          --> lessons.content (SNML completo almacenado como texto)
    +--> result.exercises       --> filas de exercises (type + content JSONB)
    +--> result.headings        --> Se usa para renderizar el TOC, no se almacena por separado
    |
    v
INSERT INTO lessons (title, content, position)
    VALUES (frontmatter.title, full_snml_string, frontmatter.lesson_position);

FOR EACH exercise IN result.exercises:
    INSERT INTO exercises (lesson_id, type, content, position)
        VALUES (lesson.id, exercise.type, exercise.content, exercise.position);
```

**Decisión clave:** La cadena SNML completa se almacena en `lessons.content`. Los ejercicios TAMBIÉN se extraen y se almacenan como filas separadas en la tabla `exercises`. Esto significa:

- **Renderizado:** Cargar el contenido de la lección (SNML), analizarlo, renderizar los bloques con componentes React.
- **Evaluación:** Cargar las filas de ejercicio directamente. No hace falta analizar el SNML para evaluar.
- **Edición:** Actualizar la cadena SNML. Volver a analizarla para actualizar las filas de ejercicio.

Esto está desnormalizado por diseño. El SNML es la fuente de verdad para la visualización. Las filas de ejercicio son un índice derivado para la evaluación y el seguimiento del progreso.

---

## 9. Prompt de generación por IA

Este es el prompt de sistema para el agente Generador de Módulos (ver [content-generation.md](content-generation.md), sección 3.4) al generar salida SNML.

### 9.1 Prompt de sistema

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

### 9.2 Ejemplo de entrada y salida

**Entrada (extracto del material fuente de un PDF):**

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

**Salida (SNML generado por el LLM):**

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

## 10. Organización de ficheros

### 10.1 Estructura del directorio del curso

Cuando un curso se exporta o se gestiona como ficheros (catálogo, repositorio Git, exportación desde admin):

```
politica-devoluciones/
  _course.snml                    # Metadatos del curso
  01-fundamentos/
    _module.yaml                  # Metadatos del módulo (position, summary)
    01-reglas-basicas.snml        # Lección 1
    02-casos-especiales.snml      # Lección 2
    03-excepciones.snml           # Lección 3
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

### 10.2 Metadatos del módulo (`_module.yaml`)

```yaml
title: "Fundamentos de la Politica"
position: 1
summary: "Plazos, condiciones y documentacion necesaria"
```

Esto es mínimo porque los metadatos a nivel de lección llevan el detalle. El fichero de módulo existe para que la estructura de directorios se autodescriba sin necesidad de analizar cada lección.

---

## 11. Conversión de SNML a JSON

Para las respuestas de la API y el almacenamiento en base de datos, SNML puede convertirse a una representación JSON. Esto es lo que recibe el frontend de `GET /api/v1/lessons/{id}`.

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

**Importante:** En la respuesta de la API, los bloques de ejercicio NO incluyen los campos `correct`, `explanation`, `rubric` ni `system_prompt`. Estos son solo del lado del servidor — se usan para evaluar cuando el aprendiz envía una respuesta. Esto evita que el aprendiz inspeccione el código fuente de la página para encontrar las respuestas.

Los campos de evaluación solo se devuelven DESPUÉS de que el aprendiz envía un intento, en la respuesta a `POST /api/v1/exercises/{id}/attempt`.

---

## 12. Versionado del formato

El formato SNML incluye una versión en el frontmatter para compatibilidad futura:

```yaml
---
snml: "1.0"
title: "..."
---
```

Si `snml` está ausente, el analizador asume `"1.0"`. Las versiones futuras pueden añadir nuevos tipos de componente o modificar los existentes. El analizador gestiona los bloques `:::` desconocidos con elegancia, renderizándolos como texto plano (bloque markdown).

**Política de versiones:**

- Las versiones menores (1.1, 1.2) añaden nuevos tipos de componente o atributos opcionales. Los analizadores antiguos ignoran los tipos desconocidos.
- Las versiones mayores (2.0) pueden cambiar la sintaxis de componentes existentes. Los analizadores antiguos pueden no renderizar correctamente.

---

## 13. Decisiones clave de diseño

| Decisión | Justificación |
|----------|-----------|
| **Bloques delimitados por `:::` en vez de sintaxis propia** | Propuesta de directivas genéricas de CommonMark. Usada por VuePress, Docusaurus, MyST. Familiar, ampliamente entendida, se degrada con elegancia. |
| **Sin anidamiento** | Mantiene el análisis trivial. Basta una máquina de estados línea a línea. No hace falta descenso recursivo. |
| **Listas de tareas de Markdown para las opciones de test** | `- [x]` y `- [ ]` se entienden universalmente. Se renderizan como casillas en la mayoría de renderizadores de Markdown. La respuesta correcta es visible en modo doc. |
| **Clave: valor dentro de los bloques** | Más simple que YAML (sin sensibilidad a la indentación) y más simple que JSON (sin necesidad de escapar). Cada línea se autodescribe. |
| **IDs de ejercicio como atributos** | Los mantiene fuera del contenido visible. El analizador los extrae para el mapeo a base de datos. |
| **SNML completo almacenado en lessons.content** | La cadena SNML es la fuente de verdad para el renderizado. Las filas de ejercicio en la tabla exercises son un índice derivado. Esto evita tener que reconstruir el diseño de la lección a partir de las filas de ejercicio. |
| **Ejercicios extraídos en filas separadas** | La evaluación, el seguimiento del progreso, la repetición espaciada y la analítica necesitan consultar los ejercicios de forma independiente. Analizar el SNML en cada consulta es demasiado costoso. |
| **Sin variables ni plantillas** | SNML es un formato de contenido, no un lenguaje de programación. La personalización ocurre en tiempo de renderizado (perfiles de aprendizaje, adaptaciones de accesibilidad), no en el formato en sí. |
| **Los campos multilínea usan continuación** | Las líneas posteriores a una `clave:` se añaden al valor hasta la siguiente palabra clave o el fin del bloque. Esto evita necesitar comillas o caracteres de escape para textos largos. |
| **Nivel de Bloom como atributo del ejercicio** | El pipeline de generación de contenido necesita esto para forzar la distribución (50% apply o superior). Se almacena como metadato, no se muestra a los aprendices. |

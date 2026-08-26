---
title: "Generative UI (investigación)"
order: 55
section: "research"
group: "generative-ui"
---

# Generative UI

Cómo los agentes de IA producen interfaces de usuario, y por qué eso lo cambia todo para plataformas como SkillNet.

## Tres niveles

| Nivel | Nombre | Cómo funciona | Tokens | Latencia |
|-------|------|-------------|--------|---------|
| **1** | Estático | El agente envía datos a componentes preconstruidos | ~300 | <2s |
| **2** | Declarativo | El agente emite una especificación compacta; un renderizador la expande a HTML | ~458 | <0.1s |
| **3** | Generativo | El agente escribe HTML/CSS/JS en bruto desde cero | ~3.343 | 23s |

El Nivel 2 es **7,3 veces más eficiente en tokens** que el Nivel 3 para la misma información. El Nivel 3 produce una calidad casi humana (ELO 1736 frente a un experto en 1800 en [la evaluación de Google](https://arxiv.org/abs/2604.09577)) pero es demasiado lento y caro para uso interactivo.

## El problema real

Generar una página HTML completa cuesta entre 2.000 y 8.000 tokens de salida. A escala, eso son entre 30 y 120 $/día solo en UI. La latencia de generación es de 20 a 30 segundos por página. Y entre el 12% y el 65% del código generado contiene vulnerabilidades de seguridad.

La pregunta no es si los agentes *pueden* generar UI. Pueden. La pregunta es si es práctico, y la respuesta es: **no en el Nivel 3, no para todo.**

## ¿Cuándo tiene sentido la generative UI?

Tres variables determinan qué nivel se necesita. Cuando las tres son altas, el Nivel 3 es la única opción. Cuando cualquiera es baja, el Nivel 2 basta.

| Variable | Baja | Alta |
|----------|-----|------|
| **Variabilidad del contenido** | Una landing page, un blog, una tienda con 20 productos. Todos ven lo mismo. | Formación personalizada, historiales médicos, soporte técnico. Cada persona ve algo distinto. |
| **Variabilidad del contexto** | Un panel de analítica que se actualiza a diario. El formato es predecible. | Emergencias, logística, eventos en directo. Lo que necesitas cambia cada minuto. |
| **Variabilidad del usuario** | Todos los administradores hacen las mismas tareas. Una pantalla sirve para todos. | Un camarero nuevo frente a uno veterano, un gerente, un cocinero. Cada rol necesita vistas completamente distintas. |

La matriz:

```
Content   Context   User   → Level
───────   ───────   ────   ──────────────────
LOW       LOW       LOW    → Level 1 (static). Fixed screens. No AI needed.
HIGH      LOW       LOW    → Level 2 (declarative). Fixed components, variable data.
HIGH      HIGH      LOW    → Level 2–3. Fixed components, generated content.
HIGH      HIGH      HIGH   → Level 3 (generative). You cannot pre-design screens.
```

### Dónde encaja el Nivel 3 en SkillNet

SkillNet no es una plataforma de Nivel 3. Es una plataforma en la que el Nivel 3 **puede integrarse** en los escenarios donde las tres variables son altas:

- **Contenido:** cada empresa tiene sus propios cursos, cada curso es único, cada lección se adapta al alumno
- **Contexto:** un empleado nuevo necesita una cosa, alguien con un examen mañana necesita otra, alguien de pie frente a una freidora necesita algo completamente distinto
- **Usuario:** personal nuevo, veteranos, gerentes, cocineros, seguridad. Cada rol necesita vistas completamente distintas

Cuando la combinación de variables produce millones de pantallas posibles (50 empresas × 200 cursos × 1.000 empleados × nivel de habilidad × hora del día), las pantallas prediseñadas dejan de ser viables. Ahí es donde la generative UI se convierte en el único enfoque práctico.

Pero la mayor parte de la plataforma no la necesita. Las pantallas de inicio de sesión, ajustes y perfil son Nivel 1. Los paneles y los listados de cursos son Nivel 2. El Nivel 3 se aplica específicamente a lecciones personalizadas, tutoría adaptativa y respuestas del agente: los momentos en los que el contenido realmente debe generarse para esa persona en ese contexto.

## Lo que construimos: A2TL-Web

El hallazgo central: se puede obtener **el 76% del ahorro de tokens** haciendo que el agente describa *qué* mostrar en lugar de *cómo* renderizarlo. Construimos **A2TL-Web (Agent to Transformation Language — Web)**, un formato compacto donde el agente escribe una especificación y un renderizador determinista la expande a HTML completo.

```
UIDL/1
theme dark
layout stack

h1 "Training Dashboard"
text "Week 2 progress for the kitchen team" dim

metrics 3
  "Completed" "12/20" green "On track"
  "Avg Score" "87%" blue "+5% vs last week"
  "Time Spent" "4.2h" orange "Below target"

chart bar "Scores by Module"
  x "Safety" "Prep" "Service" "Cleanup"
  y 92 85 78 91

table "Pending Exercises"
  cols Module Exercise Due
  row "Safety" "Fire extinguisher drill" "Tomorrow"
  row "Service" "Customer complaint handling" "Friday"
```

Esta especificación tiene ~360 tokens. El renderizador la expande a una página HTML completa e independiente con gráficos de Chart.js, tablas con estilo, tarjetas de métricas y diseño responsive (~2.400 tokens de HTML). El agente nunca genera HTML; nunca trata con CSS ni JavaScript.

**Implementación:** [github.com/JoseEstevez520/a2tl-web](https://github.com/JoseEstevez520/a2tl-web), un servidor MCP y una herramienta de línea de comandos. Disponible como herramienta para cualquier agente compatible con MCP. La v1.2.0 añade un sistema de marca/tema: un preset JSON (~8 propiedades: colores, fuente, logo, radio, pie de página) que el renderizador aplica sin cambiar la especificación. El LLM escribe el mismo formato compacto; la marca de la organización se aplica en el momento del renderizado.

| Métrica | A2TL-Web | HTML en bruto equivalente |
|--------|----------|---------------------|
| Tokens | ~360 | ~1.471 |
| Bytes | 1.327 | 9.992 |
| Líneas | 40 | 180+ |
| **Ahorro** | **76%** menos tokens | |

A2TL-Web opera en el Nivel 2: el agente escribe una especificación compacta, y un renderizador local la expande de forma determinista. Esto significa que no hay ningún LLM implicado en el paso de renderizado. El Nivel 3 (donde el agente genera el HTML completo) es un enfoque distinto con otras contrapartidas que aún queremos explorar.

### Lo que A2TL-Web no resuelve

Ninguna interactividad compleja (filtros, formularios, gestión de estado). Sin layouts anidados. Limitado a los tipos de gráfico de Chart.js. Salida HTML estática, sin actualizaciones en tiempo real. Para eso hace falta un registro de componentes (Nivel 1) o generación completa (Nivel 3).

Sin embargo, el renderizador es extensible. Las organizaciones pueden registrar componentes personalizados en su renderizador sin cambiar el formato de la especificación. Esto significa que la especificación se mantiene compacta y estable mientras cada despliegue puede soportar elementos específicos de su dominio. Ver [extending the renderer](https://github.com/JoseEstevez520/a2tl-web/blob/main/docs/extending.md) para más detalles.

### Experimental: aplicando la misma idea al vídeo (A2TL-Video)

El mismo principio — el agente describe *qué*, el renderizador decide *cómo* — se aplicó experimentalmente a vídeos explicativos. [A2TL-Video (Agent to Transformation Language — Video)](https://github.com/JoseEstevez520/a2tl-video) es un formato compacto inspirado en Remotion donde 98 líneas / 1.173 tokens producen un vídeo de 74 segundos — un 48% menos de tokens que el JSX equivalente de Remotion (2.257 tokens) y un 94% menos que la salida del reproductor HTML (21.305 tokens). Medido con tiktoken.

```
VDSL/1
theme dark-tech
canvas 1920x1080

scene "The Problem" 6s crossfade
  text "Your data has no walls." hero center word-stagger 0-4s

scene "The Solution" 8s blur-crossfade
  viz 0.5-8s build-up
    type: flow-diagram
    steps:
      - label: "Label" desc: "tag your data" icon: tag color: blue
      - label: "Check" desc: "verify at the gate" icon: shield color: green
```

El pipeline compila `.vdsl` a un reproductor HTML autocontenido (reproducción instantánea, sin dependencias) o a MP4 vía Remotion. Incluye 17 componentes integrados, 4 temas, un componente web `<vdsl-player>` para embeber, y overrides de paleta/fuente en línea. La idea es simple: los agentes no deberían necesitar conocer HTML, CSS, librerías de animación ni frameworks de vídeo. Describen *qué* mostrar, y el renderizador se encarga de todo lo demás.

## Cinco prototipos comparados

Construimos cinco prototipos en distintos niveles y los medimos frente a frente sobre el mismo dataset. Los hallazgos clave:

1. **El Nivel 2 (A2TL-Web) es 7,3 veces más eficiente en tokens que el Nivel 3** para el mismo contenido
2. **La latencia del Nivel 3 (23s) es prohibitiva** para uso interactivo
3. **Un pipeline vault-to-page (sin LLM) es el más eficiente**: 0 tokens, 310ms, HTML funcional
4. **Un bucle bidireccional funciona** (el agente genera → el usuario interactúa → el agente regenera) pero cuesta ~3.500 tokens por ciclo
5. **La calidad visual del Nivel 3 es inconsistente.** Cada página se ve distinta. El Nivel 2 usa un sistema de diseño, así que la salida siempre es consistente.

Datos completos: [experiments/prototype-benchmarks.md](/docs/generative-ui-benchmarks)

## Quién está trabajando en esto

La generative UI todavía es incipiente. Los principales actores que la están llevando a producción (julio de 2026):

- **Google.** Generative UI completa en [Gemini](https://gemini.google.com) y Search AI Mode. También creó [A2UI](https://github.com/google/a2ui), un protocolo de código abierto donde los agentes emiten JSON describiendo la intención de la UI y el cliente renderiza componentes nativos.
- **Anthropic.** [Claude Artifacts](https://support.anthropic.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) y [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) renderizan UI interactiva en iframes en sandbox.
- **Vercel.** [v0](https://v0.dev) genera React + Tailwind a partir de prompts. El [AI SDK](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces) transmite React Server Components en streaming.
- **CopilotKit.** [AG-UI](https://docs.ag-ui.com/) es un protocolo basado en eventos para comunicación bidireccional agente-frontend. Complementa a A2UI (AG-UI transporta payloads de A2UI).

Todos ellos trabajan en el Nivel 3 (generación completa de HTML/CSS/JS) o en el Nivel 1 (registros de componentes). A2TL-Web es una herramienta de Nivel 2 que construimos para resolver un problema específico: generar contenido estructurado (paneles, informes, resúmenes) sin el coste y la latencia de la generación completa. No es una alternativa al Nivel 3. Todavía queremos explorar el Nivel 3 para los escenarios donde se necesita generación libre.

## Una idea clave

Nuestro propio proceso de desarrollo ya es generative UI. En cada sesión de trabajo, la IA lee datos de la base de conocimiento, decide qué investigar o construir, y genera documentos, páginas web, paneles y especificaciones adaptados al contexto actual. El patrón es el mismo: un sistema que genera contenido personalizado en el momento según quién pregunta y qué necesita.

Esa experiencia directa (saber qué funciona, qué falla, qué frustra, qué ahorra tiempo) es la base para diseñar la generative UI de SkillNet.

## Dónde está ahora la investigación

El principal problema abierto es **la latencia de generación**. El Nivel 3 tarda de 20 a 30 segundos por página. Eso está bien para un informe que se genera una vez, pero es inaceptable para uso interactivo. La pregunta que estamos investigando: ¿cómo se hace que la espera no se sienta como una espera?

La web ya lidia con esto. Pantallas esqueleto, loaders, renderizado progresivo. Estos patrones reducen la latencia percibida, y la investigación muestra que los esqueletos en particular hacen que los usuarios perciban los tiempos de carga como más cortos. La pregunta es cómo adaptar estos patrones a la generative UI, donde el contenido todavía no existe.

Dos enfoques que estamos explorando:

**1. Generación con dos agentes.** Un agente rápido genera el esqueleto (layout, placeholders, estructura) mientras un segundo agente genera el contenido real en segundo plano. El usuario ve algo de inmediato, y el contenido real se va rellenando a medida que está listo. Esto optimiza el tiempo percibido porque el usuario nunca está mirando una pantalla en blanco.

**2. Experiencias de espera preconstruidas.** En lugar de un spinner genérico, usar pantallas interactivas prediseñadas para la espera. Por ejemplo, la animación de un personaje o un elemento visual que siempre está listo, combinado con un texto breve generado por un agente rápido y ligero. El usuario obtiene algo atractivo y contextual (no solo "cargando...") mientras la generación completa ocurre en segundo plano. Para cuando el contenido real está listo, el usuario ya ha tenido unos segundos de interacción, y la generación ha tenido tiempo de completarse.

Ambos enfoques comparten la misma idea: usar el tiempo de espera de forma productiva en lugar de intentar eliminarlo. Dar al usuario algo significativo mientras la generación pesada corre entre bastidores.

Está surgiendo una dirección separada para el propio A2TL-Web: posicionarlo como un estándar de consumo en lugar de un DSL en crecimiento. La idea sigue la tesis post-Markdown: no cambies el formato, haz al lector más inteligente. La especificación se mantiene mínima y estable; el renderizador es el punto de extensión, no la especificación. Cada organización extiende su propio renderizador para soportar los componentes que necesite (gráficos específicos de dominio, widgets interactivos, tarjetas personalizadas) mientras el agente sigue escribiendo el mismo formato compacto. Esto mantiene pequeña y predecible la superficie de cara al LLM, y empuja la complejidad hacia el lado determinista del sistema, donde es más fácil de controlar.

## Preguntas abiertas

- Si no hay pantallas prediseñadas, ¿qué hay? ¿Un flujo continuo?
- Si cada usuario ve algo distinto, ¿cómo se mantiene la identidad de marca?
- Si el LLM lo genera todo, ¿qué hace el desarrollador? ¿Reglas de diseño? ¿Entrenar modelos? ¿Definir límites?
- ¿Qué es SkillNet si nace con generative UI nativa? No es un LMS con un chatbot. Es... ¿qué?

## Actualización — 24 de julio de 2026: escaneo del panorama, decisiones y nueva arquitectura

Una sesión de investigación profunda produjo un escaneo exhaustivo del panorama de la generative UI: 21 artículos académicos, 3 frameworks, 2 protocolos y 1 estándar listo para producción. Los hallazgos y decisiones clave están documentados en el vault; esta sección resume lo que cambió.

### Artículos que validaron nuestra dirección

| Artículo | Por qué importa |
|-------|----------------|
| **[MAIC-UI](https://arxiv.org/abs/2604.25806)** (Tsinghua) | Gemelo académico de SkillNet. Misma fuente (PDFs → cursos interactivos), pipeline similar. +9,21 puntos en STEM en 53 estudiantes durante 3 meses. **Valida todo nuestro enfoque.** |
| **[The Keyhole Effect](https://arxiv.org/abs/2602.00947)** (Reddy) | Base neurocientífica de por qué las interfaces solo-chat fallan en aprendizaje/análisis. El chat destruye la memoria espacial, fuerza la verbalización (que degrada la memoria visual), bloquea la descarga cognitiva. **El tutor de SkillNet no puede ser solo-chat.** |
| **[Stanford SALT GenUI](https://arxiv.org/abs/2508.19227)** | Pipeline: requisito → DSL → generar → refinar. 72% de preferencia humana frente al chat. Función de recompensa adaptativa. **Valida nuestro pipeline de 7 etapas.** |
| **[Software as Content](https://arxiv.org/abs/2603.21334)** (Xie & Xie) | Apps generadas como capa de interacción persistente, no chat desechable. **Exactamente hacia donde SkillNet necesita ir.** |
| **[The Missing Layer](https://arxiv.org/abs/2606.15902)** | La GenUI en educación debería ser en tiempo de diseño (autoría), no solo en tiempo de ejecución. **Valida nuestra separación de esquema/contenido.** |
| **[Macaron-A2UI](https://arxiv.org/abs/2605.24830)** | LoRA + GRPO sobre DSL declarativo supera a GPT-5.4 con prompting. **Inspiración directa para hacer fine-tuning de un modelo pequeño que genere UI DSL de forma nativa.** |
| **[Google GenUI](https://arxiv.org/abs/2604.09577)** — Leviathan et al. | Artículo fundacional. Los LLM generan UI comparable a expertos humanos (ELO 1736 vs 1800). |

Lista completa de los 21 artículos: `docs/research/generative-ui/papers/awesome_generative_ui.md` (o referencia en el vault).

### Frameworks y protocolos evaluados

| Recurso | Tipo | Qué ofrece |
|----------|------|----------------|
| **[A2UI](https://a2ui.org/)** (Google) | Protocolo abierto | Estándar de UI dirigida por agentes. JSON declarativo, agnóstico de framework, seguro por diseño (catálogo de componentes preaprobados). v0.9.1 en producción, v1.0 candidata. Multi-cliente (React, Angular, Flutter, Lit). |
| **[OpenUI Lang](https://www.openui.com/)** (Thesys) | DSL + Runtime | DSL orientado a líneas, 52-67% menos tokens que JSON, parser en streaming con validación, `<Renderer />` de React, generador de system prompt (`library.prompt()`). 7K ⭐, uso en producción. |
| **[OpenGenerativeUI](https://github.com/CopilotKit/OpenGenerativeUI)** (CopilotKit) | Framework | HTML/SVG en sandbox dentro de iframes, skills progresivas, matriz visual de decisión. El framework más completo. |
| **A2TL-Web** (nuestro) | DSL | 76% de ahorro de tokens frente a HTML, sistema de marca, cobertura de vídeo. Sin runtime, parser ni validación. |

### Decisiones tomadas

#### 1. Adoptar OpenUI Lang como runtime (sustituye a A2TL-Web en producción)

A2TL-Web logra mayor compresión (76% frente a 52-67%), pero OpenUI Lang tiene:
- Parser con AST + validación de JSON Schema
- Renderizador de React probado en producción
- Generación automática de system prompt a partir de los esquemas de componentes
- Ecosistema (7K ⭐, benchmarks, OpenUI Cloud)
- Soporte multi-framework

A2TL sigue como experimento y referencia de diseño. OpenUI Lang es el runtime de producción.

#### 2. Nueva arquitectura: esquema en tiempo de diseño → generación en tiempo de ejecución

**Antes (v1):** el admin sube documentos → el pipeline genera todo el curso como Markdown → todos los empleados ven el mismo contenido.

**Después (v2):**
```
Admin defines schema (nodes, prerequisites, criticality)
    ↓
Employee opens course → pre-assessment per node
    ↓
For each node NOT mastered:
    ├── decide_formato (8B LLM) → optimal UI type
    ├── genera_ui (8B or 120B) → OpenUI Lang
    └── render (OpenUI <Renderer />)
    ↓
Feedback → next node
```

Esto permite una personalización real sin regenerar todo el curso.

#### 3. Enrutamiento paralelo de LLM (8B / 120B)

~90% de las UI de SkillNet son de Nivel 2 (componentes estándar). Un modelo pequeño es suficiente.

| Modelo | Velocidad | Coste entrada/1M | Caso de uso |
|-------|-------|---------------|----------|
| Llama 3.1 8B (Groq) | 560 t/s | $0,05 | Esqueleto + componentes estándar (~90% de las UI) |
| GPT-OSS 120B (Groq) | 500 t/s | $0,15 | SandboxHTML, simulaciones, diagramas (~10%) |

Enrutador: si la UI necesita SandboxHTML → 120B, si no → 8B.

#### 4. Stack (actual)

```
Frontend:     React + OpenUI <Renderer /> + SkillNet UI Kit
Backend:      FastAPI + LangGraph (per-node pipeline)
Fast LLM:     Llama 3.1 8B (Groq) — 90% of UIs
Heavy LLM:    GPT-OSS 120B (Groq) — simulations/diagrams
Format:       OpenUI Lang
Protocol ref: A2UI (for future multi-client)
```

#### 5. Fine-tuning con QLoRA (backlog)

Inspirado en Macaron-A2UI (LoRA + GRPO sobre A2UI supera a GPT-5.4). Hacer fine-tuning de Qwen3-30B o Llama-3.1-8B con QLoRA para generar OpenUI Lang de forma nativa. Inferencia más barata, menos errores de formato, sin prompting pesado.

### Qué significa esto para el pipeline existente

| Hoy (v1) | Mañana (v2) |
|------------|---------------|
| El admin sube documentos → se genera el curso completo | El admin define el esquema → sin contenido hasta el tiempo de ejecución |
| Todos los empleados ven el mismo contenido | Cada empleado recibe UI generada a partir de su perfil + pre-evaluación |
| Un único LLM para todo | Enrutador: 8B para el 90%, 120B para el 10% |
| Contenido en Markdown + JSON fijos | UI en OpenUI Lang, renderizada vía `<Renderer />` |
| Sin métricas de efectividad | Bucle de feedback → el sistema se adapta por nodo |

### Hoja de ruta inmediata

1. Definir el SkillNet UI Kit — esquemas Zod para componentes educativos (TextContent, Card, Simulation, Quiz, StepSequence, Chart, Table, CodeBlock)
2. Integrar OpenUI en skillnet-web — `npm install openui`, montar `<Renderer />` con el UI Kit
3. Nuevos nodos del pipeline: `decide_formato → genera_ui` en LangGraph con enrutamiento de LLM
4. Conectar con el esquema de admin existente
5. Pre-evaluación por nodo (2-3 preguntas antes de la generación)
6. Bucle de feedback — la interacción del usuario hace que el sistema adapte el siguiente nodo

### Documentación completa

Cada hallazgo tiene su documento detallado en el vault (`07_ANFAIA/investigacion/ui_innovadora/`). El documento de síntesis y decisiones está en `_sintesis_para_repo.md`.

## Referencias

- Leviathan et al., "Generative UI: LLMs are Effective UI Generators" ([arXiv 2604.09577](https://arxiv.org/abs/2604.09577), Google Research, 2025)
- [A2UI Protocol](https://github.com/google/a2ui) (Google, Apache 2.0)
- [AG-UI Protocol](https://docs.ag-ui.com/) (CopilotKit)
- [Vercel AI SDK: Generative UI](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)
- [PAGEN benchmark](https://generativeui.github.io/)
- [TOON format](https://github.com/toon-format/toon), alternativa a JSON para LLM (30-60% de ahorro, pero frágil en multi-turno)
- [TypeFox: Semiformal DSL for web apps](https://www.typefox.io/blog/turn-ai-prompts-into-web-apps-using-a-semiformal-dsl/) (70-85% de ahorro)

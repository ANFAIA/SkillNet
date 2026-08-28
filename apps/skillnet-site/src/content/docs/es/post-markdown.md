---
title: "Post-Markdown"
order: 59
section: "research"
group: "post-markdown"
---

# Post-Markdown: qué viene después de Markdown para los agentes de IA

## El contexto

Markdown es el formato habitual para dar contexto a los agentes de IA. AGENTS.md, CLAUDE.md, SKILL.md y llms.txt son algunos ejemplos. Todos los agentes, frameworks y herramientas usan ficheros `.md` con este fin; la industria ha convergido en este formato.

Eso plantea una pregunta: **¿qué viene después de Markdown?**

A veces parece que nos adaptamos a lo que ya existe en lugar de crear herramientas para las necesidades actuales. Markdown se diseñó en 2004 para que las personas escribieran contenido web, no para que los agentes navegaran, consultaran y cargaran conocimiento de forma selectiva. La pregunta es si conviene sustituirlo o adaptar su consumo.

## La exploración

### Formatos nuevos

El punto de partida fue [ObjectGraph](https://arxiv.org/abs/2604.27820) (.og), un paper que propone divulgación progresiva integrada en el propio formato de fichero. Se puede cargar solo el índice y luego expandir nodos bajo demanda. Trata los documentos como estructuras navegables en lugar de texto plano.

De ahí surgió la idea: ¿y si tuviéramos un `.md` mejorado con frontmatter que incluya relaciones, tipos y estructura que una herramienta pudiera consumir de forma nativa para IA? Algo como un formato de fichero que ya lleve su propio índice, sus conexiones con otros ficheros y metadatos que un agente pueda usar sin analizar el contenido completo. Piénsese en ello como llevar parte de lo que hacen las bases de datos vectoriales, pero incrustado directamente en el fichero.

Se diseñaron tres variantes de formato en esta línea: Markdown extendido con índices incrustados vía comentarios HTML. Resultados: 78-86% de ahorro de tokens, pero requiere modificar todos los ficheros existentes.

Este camino no está cerrado. Probablemente llegue algo después de Markdown en algún momento. Pero por ahora decidimos centrarnos en optimizar cómo los agentes consumen lo que ya existe.

### El problema de tokens con HTML

En paralelo, surgió una tendencia: la gente empezó a usar HTML para visualizar sus ideas, porque es más expresivo que Markdown. Dashboards, gráficos, páginas interactivas. Pero generar HTML mediante un agente de IA es caro. Una sola página cuesta 2.000-8.000 tokens de salida y tarda 20-30 segundos en generarse. Este es el problema explorado en [generative-ui](/docs/generative-ui-research), donde construimos A2TL-Web como alternativa compacta.

### Lectores más inteligentes

La conclusión provisional es mantener el formato y cambiar cómo se consume. Los encabezados de Markdown ya forman un árbol de navegación. El problema no está en el fichero, sino en que los agentes lo leen como texto plano. Hace falta un estándar de consumo que aproveche esa estructura, no otro formato.

Esto sigue un patrón general en computación: mantener sencillo el formato y mejorar el lector. HTML no tuvo que cambiar para que existiera el DOM, ni PDF para que el OCR extrajera tablas, ni JPEG para admitir detección facial. Del mismo modo, un lector puede navegar Markdown por secciones sin cambiar Markdown.

De 6 agentes de IA principales probados (Claude Code, Cursor, Copilot, Codex, Aider, Windsurf), **ninguno** expone los encabezados de Markdown como un árbol navegable. Ese fue el hueco que decidimos llenar.

## El panorama: memoria de agentes

Hay un ecosistema creciente de proyectos que intentan dar a los agentes memoria persistente: [Mem0](https://github.com/mem0ai/mem0), [Letta](https://github.com/letta-ai/letta) (antes MemGPT), [Cognee](https://github.com/topoteretes/cognee), [Zep](https://github.com/getzep/zep), entre otros. Cada uno construye un sistema complejo (grafos de conocimiento, almacenes vectoriales, cadenas de resumen, pipelines de recuperación) sobre datos fundamentalmente simples.

La complejidad de estos sistemas tiene un coste. Cada capa puede fallar, requiere mantenimiento y acopla los datos a una herramienta concreta. La historia de la computación ofrece varios movimientos hacia formatos más simples: los ficheros reemplazaron a las bases de datos para configuración, Markdown reemplazó al texto enriquecido para documentación y JSON reemplazó a XML para intercambio de datos. La evolución apunta a formatos más simples con lectores más capaces, no a infraestructuras cada vez mayores.

Mem0 y Cognee resuelven problemas reales con una estrategia distinta. La apuesta a largo plazo aquí es mejorar la capa de consumo y mantener más sencilla la infraestructura que la rodea.

## El panorama: grafos de código apuntando a documentación

Una ola paralela promete "convertir tu repo —o cualquier carpeta— en un grafo de conocimiento que se puede consultar": [Graphify](https://github.com/Graphify-Labs/graphify), [Microsoft GraphRAG](https://github.com/microsoft/graphrag), grafos de propiedades de código ([Joern](https://github.com/joernio/joern)), [Sourcegraph SCIP](https://sourcegraph.com/blog/announcing-scip). El discurso es general —apúntalo a cualquier cosa— y cada vez más gente lo apunta a documentación.

Pero mírese sobre qué están construidos: tree-sitter, ASTs, grafos de llamadas, resolución de imports. Son **motores de análisis de código.** Su poder viene de una estructura que solo el código tiene —una función *llama* a otra, un fichero *importa* otro: relaciones explícitas, inequívocas, extraíbles mecánicamente. La prosa no tiene nada de eso. Así que cuando estas herramientas ingieren documentación no pueden analizar relaciones, las **infieren** con un LLM. Mismo nombre, herramienta distinta: en código es determinista, local y gratis; en documentación es inferencia por LLM —de pago por fichero, no determinista entre ejecuciones, y tiende a aplanar todo un documento en un único nodo, perdiendo sus secciones.

Cuando una herramienta de análisis de código se aplica a documentación, parte del proceso deja de ser determinista. La promesa de procesar "cualquier carpeta" oculta que el tratamiento de la documentación es un añadido. La documentación ya contiene estructura en sus encabezados, enlaces y frontmatter. Navegarla directamente evita usar un LLM para inferir relaciones que el formato no expresa.

## Qué se construyó

Un servidor MCP (`@anfaia/md-reader-mcp`, v1.4.1) que analiza los encabezados de Markdown en un árbol y sirve secciones bajo demanda:

- `md_find`: puerta de entrada guiada por consultas —empareja encabezados, etiquetas y nombres de fichero en todo el vault, devuelve secciones ordenadas por relevancia. Determinista (sin embeddings, sin LLM). Navegación estructural, complemento de la búsqueda de texto completo.
- `md_tree`: árbol de encabezados con recuento de tokens (~50 tokens para un fichero de 3.000 tokens)
- `md_section`: una sección por nombre (coincidencia difusa)
- `md_frontmatter`: solo el frontmatter YAML
- `md_vault_index`: grafo completo del vault con recorrido BFS

**Flujo de trabajo:** primero `md_find` con lo que se busca → devuelve las secciones que coinciden ordenadas. Después `md_section` para leer la que se ha elegido. `md_tree` cuando se necesita la estructura completa de un fichero, `md_vault_index` para explorar enlaces entre notas.

Fuente: [`packages/mcp-md-reader/`](https://github.com/ANFAIA/SkillNet/tree/main/packages/mcp-md-reader)

## Cifras clave

| Métrica | Valor |
|--------|-------|
| Ahorro de tokens con md_tree (solo árbol) | **93%** de media en 14 ficheros |
| Ahorro de tokens árbol + 1 sección | **91%** de media |
| Prototipo de carga perezosa (patrón PageIndex) | **78,5%** de media en 9 consultas |
| ObjectGraph solo índice vs Markdown | **85%** de ahorro |
| ObjectGraph .og completo vs Markdown | **44% más pesado** |
| Agentes que exponen encabezados .md como árbol | **0 / 6** |

## El mapa

```
REPRESENTACIÓN (formato de fichero)
  Hoy: Markdown plano + convenciones (AGENTS.md, SKILL.md, llms.txt)
  Emergente: ObjectGraph (.og), solo paper, sin adopción

PROTOCOLO (cómo se conectan los agentes)
  MCP (Anthropic), dominante
  A2A (Google), en crecimiento

MEMORIA (cómo almacenan estado los agentes)
  Mem0, Letta, Cognee, Zep (todos propietarios, sin formato compartido)

CONSUMO (cómo LEEN los agentes los ficheros) <-- EL HUECO QUE LLENAMOS
  0/6 agentes exponen la estructura de encabezados
  NUESTRA CONTRIBUCIÓN: mcp-md-reader (v1.4.1, 5 herramientas)
```

## Referencias

### Papers
- [ObjectGraph (arXiv 2604.27820)](https://arxiv.org/abs/2604.27820)
- [PageIndex / Don't Retrieve, Navigate (arXiv 2604.14572)](https://arxiv.org/pdf/2604.14572)
- [memorywire/AMP (arXiv 2606.01138)](https://arxiv.org/abs/2606.01138)

### Artículos clave
- [Context Format Decision (TianPan.co)](https://tianpan.co/blog/2026-05-07-context-format-decision-agent-reasoning-json-markdown-plain-text). El mismo contenido en formatos distintos cambia la precisión del LLM hasta en un 40%.
- [Markdown for Agents (Cloudflare)](https://blog.cloudflare.com/markdown-for-agents/). Conversión de HTML a Markdown para agentes, hasta un 80% de reducción de tokens.
- [Documentation is your AI interface (Mintlify)](https://www.mintlify.com/blog/docs-as-ai-interface)

### Trabajo previo (servidores MCP que implementan parcialmente la visión)
- [mcp-server-markdown](https://github.com/ofershap/mcp-server-markdown): list_headings + extract_section
- [mq: jq for Markdown](https://mqlang.org/): lenguaje de consulta para Markdown, en Rust
- [library-mcp](https://lethain.com/library-mcp/): navegación de una base de conocimiento en Markdown

### Herramientas de grafos de código (construidas para código, a menudo apuntadas a documentación)
- [Graphify](https://github.com/Graphify-Labs/graphify): grafo de código con tree-sitter; la documentación pasa por la API del modelo
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag): extracción de entidades/relaciones por LLM sobre un corpus
- [Joern](https://github.com/joernio/joern): grafos de propiedades de código (flujo de datos/control)
- [Sourcegraph SCIP](https://sourcegraph.com/blog/announcing-scip): navegación de código precisa y exacta a nivel de compilador
</content>

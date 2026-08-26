---
title: "Arquitectura"
order: 2
section: "core"
---

# Arquitectura

> **Estado: v1 completa.** Todas las secciones tienen documentos de especificación detallados enlazados abajo.

## Índice de documentos

| Documento | Qué cubre |
|----------|----------------|
| [vision.md](/docs/vision) | Fundamento filosófico — por qué SkillNet está construido así |
| [architecture.md](/docs/architecture) | Visión general del sistema, capas, aspectos transversales, decidido vs diferido |
| [data-model.md](/docs/data-model) | Esquema de PostgreSQL — 15+ tablas, índices, consultas clave |
| [screens.md](/docs/screens) | 20 especificaciones de pantalla con rutas, secciones, datos, estados, acciones |
| [design-system.md](/docs/design-system) | Tokens visuales, patrones de componentes, anti-patrones |
| [product.md](/docs/product) | Qué es SkillNet, roles, tipos de contenido, adaptación, bucle de aprendizaje |
| [content-generation.md](/docs/content-generation) | Pipeline de generación con LangGraph, 7 roles de agente, integración RAG |
| [chat-agents.md](/docs/chat-agents) | Agentes de chat de tutor y admin, patrón PageIndex, árbol de decisión RAG |
| [rag-retrieval.md](/docs/rag-retrieval) | Ingesta de documentos, chunking, búsqueda híbrida, reranking, embeddings |
| [backend-api.md](/docs/backend-api) | Estructura del proyecto FastAPI, 73 endpoints, inyección de dependencias |
| [llm-integration.md](/docs/llm-integration) | Abstracción de proveedor, streaming, gestión de prompts, seguimiento de coste |
| [background-processing.md](/docs/background-processing) | Persistencia de LangGraph + runner de trabajos en PostgreSQL, flujos de ciclo de vida |
| [docker-deployment.md](/docs/docker-deployment) | Servicios de Docker Compose, Dockerfiles, dev/prod, primer arranque |
| [security.md](/docs/security) | Autenticación, compartimentos de agentes, RGPD, seguridad de API, secretos |
| [mcp-external-api.md](/docs/mcp-external-api) | Servidor MCP, API REST externa, webhooks, integraciones |
| [frontend-backend-integration.md](/docs/frontend-backend-integration) | TanStack Query, SSE, UI de Nivel 2/3, subida de ficheros |
| [snml-spec.md](/docs/snml-spec) | SNML, sustituido: por qué el contenido viaja como `ui_spec` en JSON y no como marcado |
| [ai-course-design.md](/docs/ai-course-design) | Endpoints de IA sin estado, commit-on-create, enrutamiento multimodelo para el diseño de cursos |
| [adaptive-learning.md](/docs/adaptive-learning) | Preferencias explícitas, estrategia pedagógica, medición y contrato con la librería de componentes |
| [personalization-architecture.md](/docs/personalization-architecture) | Separación objetivo, misión, representación, componente, apoyo y planificador en sombra |
| [learning-experience-architecture.md](/docs/learning-experience-architecture) | Contrato pedagógico neutral, variantes, proveedores, generación multiagente y evidencia común hacia mastery |
| [audience-modes.md](/docs/audience-modes) | Un núcleo de producto con modos `organization` e `individual`, sin separar clases ni verticales |
| [conversational-modalities.md](/docs/conversational-modalities) | Frontera entre audio en chat, Realtime, mascota y podcasts; propósito y alcance por audiencia |
| [podcast-studio-plan.md](/docs/podcast-studio-plan) | Plan de Podcast Studio tipo NotebookLM, modular, configurable y agnóstico de proveedor |
| [future-product-directions.md](/docs/future-product-directions) | Índice de las direcciones futuras de producto acordadas y su estado |
| `Cuaderno de experimentos` | Hipótesis, resultados, reversiones y aprendizajes reproducibles de personalización |

---

## Visión general del sistema

SkillNet toma el conocimiento interno de una organización (manuales, procesos, documentación) y lo convierte en un sistema de aprendizaje vivo. El flujo central:

```
Documentos internos ──→ Ingesta ──→ Capa de conocimiento ──→ Equipos de agentes ──→ Interfaz ──→ Aprendiz
                                      ↑                                            │
                                      └────────────── progreso ────────────────────┘
```

El conocimiento fluye en una sola dirección: desde la documentación en bruto, pasando por conocimiento estructurado, hasta experiencias de aprendizaje generadas. El progreso del aprendiz retroalimenta la capa de conocimiento para impulsar la adaptación.

---

## Capas

### 1. Ingesta

Toma la documentación interna en bruto de la empresa y la transforma en conocimiento estructurado sobre el que el sistema puede razonar.

- **Entrada:** Markdown, PDFs, wikis internas, documentos de proceso
- **Salida:** Unidades de conocimiento estructuradas e indexadas para su recuperación

**(diferido)** Estrategia de chunking. El enfoque condicional de RAG está documentado (los documentos pequeños van enteros, los grandes se trocean). El método concreto de chunking (semántico por secciones con reserva de tamaño fijo) se decidirá cuando se construya el pipeline de ingesta.

**(diferido)** Flujo de actualización. Cuando cambian los documentos fuente, ¿cómo se mantiene al día la capa de conocimiento? Reingesta completa frente a actualizaciones incrementales.

### 2. Capa de conocimiento

La memoria del sistema. Almacena conocimiento estructurado y lo pone a disposición de los agentes a través de la recuperación.

| Componente | Rol |
|-----------|------|
| **PostgreSQL + pgvector** | Una única base de datos para todos los datos: relacionales (usuarios, cursos, progreso) y vectoriales (embeddings). Una sola copia de seguridad, una sola conexión, joins transaccionales entre contenido y vectores. |
| **Control de acceso** | Determina qué conocimiento es visible para quién |

**Lo que sabemos por la investigación:**

- La clasificación de niveles de acceso basada en contenido se limita a un 78% de precisión ([investigación sobre fronteras semánticas](/docs/semantic-boundaries)). La privacidad es una decisión humana, no una propiedad del contenido. El sistema debe hacer cumplir las decisiones de acceso de la organización, no adivinarlas.
- El acceso basado en compartimentos (necesidad de conocer) es el modelo más prometedor. Un agente arranca solo con los compartimentos que su tarea requiere. El control ocurre en el arranque (qué puede ver) y en la frontera (qué puede emitir), no dentro del agente.

**Almacén vectorial: pgvector.** Los embeddings viven dentro de PostgreSQL como una columna `vector`. Una sola base de datos para todo — consultas relacionales y búsqueda semántica en la misma transacción. A escala de MVP (decenas de documentos, cientos de empleados), pgvector es más que suficiente. Si el sistema alguna vez necesita manejar millones de vectores a miles de QPS, los embeddings pueden migrar a un almacén dedicado sin tocar el esquema relacional.

**(abierto)** Grafo de conocimiento. Si las relaciones entre unidades de conocimiento necesitan una estructura de grafo explícita o si la proximidad vectorial + metadatos es suficiente. El paper de G-SPEC sugiere que el 68% de las ganancias de seguridad provienen de la estructura de grafo.

### 3. Equipos de agentes

Agentes de IA especializados orquestados con LangGraph. Cada tipo de agente tiene un rol distinto:

| Agente | Responsabilidad |
|-------|---------------|
| **Agentes de ingesta** | Procesan documentos en bruto en conocimiento estructurado |
| **Agentes de contenido** | Generan cursos, ejercicios, evaluaciones a partir del conocimiento |
| **Agentes de tutoría** | Guían a los aprendices por el contenido, adaptan el ritmo y responden preguntas bajo demanda — recuperan de la capa de conocimiento (RAG) contextualizado con el progreso del aprendiz |

**Lo que sabemos por la investigación:**

- La autoridad entre agentes sigue un modelo de mandato, no de propiedad ([investigación sobre coordinación multiagente](/docs/multi-agent-coordination)). Un agente actúa en nombre de alguien, con un propósito específico, con límites definidos. Cuando sirve a varios usuarios, sus permisos son la intersección de todos los mandatos activos.
- El aislamiento entre agentes permite una verificación fiable. Si el revisor y el autor no comparten contexto, las tasas de error se multiplican (verificación independiente).

**Orquestación:** LangGraph gestiona las máquinas de estados y transiciones de los agentes. Cada tipo de agente es un grafo con nodos y aristas definidos.

**(abierto)** Comunicación entre agentes. Cómo se pasan los resultados entre sí los agentes — traspaso de estado directo, memoria compartida, cola de mensajes.

**(abierto)** Implementación de mandatos. El concepto de mandato está claro (principal, agente, objetivo, permisos, límites) pero la representación en tiempo de ejecución y el mecanismo de cumplimiento todavía no están definidos.

### 4. Capa de interfaz

Cómo llega el contenido al aprendiz. Tres niveles de generación, usados donde corresponde:

| Nivel | Cómo | Cuándo usarlo |
|-------|-----|-------------|
| **1 — Estático** | Componentes React preconstruidos, el agente envía datos | Login, ajustes, navegación, pantallas de admin |
| **2 — Declarativo** | El agente emite una especificación compacta (A2TL-Web), el renderizador la expande a HTML | Dashboards, listados de cursos, informes, vistas de progreso |
| **3 — Generativo** | El agente escribe HTML/CSS/JS completo | Lecciones personalizadas, tutoría adaptativa, respuestas de agente |

La mayor parte de SkillNet es de Nivel 1 y 2. El Nivel 3 se aplica solo donde el contenido, el contexto y la variabilidad del usuario son todos altos — los momentos en que las pantallas prediseñadas no son viables.

**Lo que existe:**

- [Renderizador A2TL-Web](https://github.com/ANFAIA/SkillNet/tree/main/packages/a2tl-web) — implementación de Nivel 2. Ahorro del 76% de tokens frente a HTML equivalente.

**Latencia del Nivel 3: ya no está diferida, y es menor de lo que se asumía.** v2 (cursos dinámicos) es la implementación de Nivel 3, y su latencia de generación se ha medido contra Groq real (2026-07-27): **de menos de un segundo a ~3 s por render, ~0.0008 USD por render**. El problema de "generación de 20-30 segundos" que esta sección se escribió para preocuparse **no existe en esta pila** — las cifras de 60-150 s de la investigación provenían de un modelo de 7B en CPU local.

El enfoque implementado combina esqueleto + streaming SSE con generación anticipatoria acotada. Al abrir
el curso se preparan las dos primeras lecciones disponibles; una vez que empieza el aprendizaje, el cliente mantiene
una ventana móvil de tres lecciones por delante. Son renders en tiempo de ejecución creados con el contexto actual
del aprendiz y cacheados de forma idempotente, no artefactos de presentación horneados en el curso publicado. Ver
[`learning-experience-architecture.md`](/docs/learning-experience-architecture) §2.1 y
[`v2-dynamic-courses.md`](/docs/dynamic-courses) §9 para el modelo de latencia.

Nótese también que el Nivel 3 tal como está construido **no** inyecta HTML generado por el agente: el modelo emite un dialecto tipado que se parsea a un `UISpec`, se reserializa, y se renderiza mediante componentes React nativos. Nunca HTML, así que el aislamiento shadow-DOM/iframe contemplado abajo no es necesario.

**Arquitectura de frontend: una sola SPA.** Una aplicación React con React Router. El Nivel 1 (estático) son componentes React normales. El Nivel 2 (declarativo) usa un componente renderizador que toma una especificación compacta y la pinta — el formato concreto (A2TL-Web u otro) no está fijado. El Nivel 3 (generativo) inyecta HTML generado por el agente en un contenedor aislado (shadow DOM o iframe) para evitar conflictos de CSS. El usuario no sabe qué nivel está viendo — la navegación es igual en todas partes.

**Enrutamiento: rutas fijas con contenido dinámico.** Cada pantalla tiene una URL predecible. Las rutas están en español, siguiendo el código (`apps/skillnet-web/src/App.tsx`): `/empleado`, `/empleado/curso/:id`, `/empleado/curso/:id/nodo/:nodeId`, `/admin/empleados`, `/admin/curso/:id/esquema`. La lista completa está en [`screens.md`](/docs/screens). Las URLs son compartibles y el avance/retroceso del navegador funciona. Cuando el Nivel 3 genera contenido, se renderiza dentro de la ruta fija — la URL no cambia, solo lo que hay dentro.

**Gestión de estado: React Query (TanStack Query).** El estado del servidor (cursos, progreso, skills, ejercicios) se obtiene y cachea con React Query — el backend es la única fuente de verdad. El estado local de UI (barra lateral abierta, filtro activo, modal visible) usa `useState` normal. No se necesita un store global. Si surge un caso más adelante, Zustand puede añadirse en minutos.

### 5. API

FastAPI sirve como la interfaz entre el frontend y el backend.

**Estilo de API: REST pragmático.** CRUD estándar para recursos de datos (`GET/POST/PUT/DELETE /api/v1/courses`) más endpoints de acción explícitos para operaciones (`POST /courses/{id}/generate`, `POST /courses/{id}/publish`, `POST /exercises/{id}/attempt`). Ni GraphQL, ni REST puro. Las rutas dicen lo que hacen.

**(abierto)** Detalles del contrato de la API. Endpoints concretos, esquemas de petición/respuesta, versionado.

**Autenticación: cookies de sesión vía fastapi-users.** El login envía email + contraseña, el backend crea una sesión en PostgreSQL y devuelve una cookie `httpOnly` (caducidad de 7 días). El navegador envía la cookie automáticamente en cada petición — sin gestión de tokens en el código de frontend. Cada dispositivo obtiene su propia sesión independiente. La creación de cuentas es solo para admins por defecto (el admin crea empleados desde el panel); el autorregistro puede habilitarse por despliegue como un flag de configuración. Construido sobre `CookieTransport` de fastapi-users.

**Tiempo real: SSE (Server-Sent Events).** Las respuestas del agente se transmiten token a token vía `StreamingResponse` en FastAPI. Unidireccional (servidor → cliente). El usuario envía una pregunta como un POST normal, luego abre una conexión SSE para recibir la respuesta en streaming. Estándar para streaming de LLM (ChatGPT, Claude). No se necesita infraestructura WebSocket.

**Multi-tenancy: no aplicable.** SkillNet es autoalojado — una instancia por empresa, una base de datos, un Docker Compose. La tabla `organizations` existe para el ámbito de los datos pero tiene una sola fila por despliegue. Si el SaaS llega a ser una necesidad futura (post-beca), el esquema ya delimita por `org_id`, así que la seguridad a nivel de fila puede añadirse sin reestructurar.

### 6. Infraestructura

| Decisión | Dirección actual |
|----------|------------------|
| **Despliegue** | Docker, autoalojable |
| **Base de datos** | PostgreSQL |
| **Sin dependencia de proveedor** | La funcionalidad principal debe funcionar sin ningún proveedor de nube específico |

**Proveedor de LLM: elección del usuario.** SkillNet no se ata a ningún proveedor. El usuario configura su propia clave de API y endpoint. Cualquier API compatible con OpenAI funciona directamente (OpenAI, DeepSeek, Groq, Together, local vía Ollama/LM Studio, etc.). El backend habla con una única interfaz — URL base + clave de API + nombre de modelo — definida en variables de entorno. Sin código específico de proveedor en la lógica de negocio.

**Procesamiento en segundo plano: híbrido.** Persistencia de LangGraph para el pipeline de generación (ya es un grafo, con checkpointing integrado, interrupt/resume) + un runner de trabajos respaldado por PostgreSQL para todo lo demás (cero dependencias nuevas, `SELECT FOR UPDATE SKIP LOCKED`). No se necesita Redis para el MVP. Diseño completo en [background-processing.md](/docs/background-processing).

---

## Aspectos transversales

### Modelo de control de acceso

Basado en la investigación de [fronteras semánticas](/docs/semantic-boundaries) y [coordinación multiagente](/docs/multi-agent-coordination):

```
Arranque ──→ Agente (contexto compartimentado) ──→ Frontera ──→ Salida
  │                                           │
  │  "qué puede ver"                        │  "qué puede emitir"
  │  Filtro determinista por etiquetas           │  Capa dura (escáner) + capa blanda (agente de aduanas)
```

El control nunca está dentro del agente. El agente opera libremente dentro de su contexto compartimentado. El cumplimiento es estructural.

### Bucle de adaptación

El sistema se adapta a cada aprendiz:

```
El aprendiz completa un ejercicio ──→ Se registra el progreso
                                     │
                        ┌────────────┴────────────┐
                        │                         │
              La dificultad del contenido    El formato del contenido
              se ajusta al nivel              se ajusta al aprendiz
```

**(diferido)** Señales de adaptación. Qué datos impulsan la personalización (solo puntuaciones, puntuaciones + tiempo, patrones de comportamiento completos). El modelo de datos ya captura puntuaciones y timestamps en `exercise_attempts`, así que cualquier enfoque puede implementarse más adelante sin cambios de esquema. Se decidirá cuando haya datos reales de usuarios que analizar.

---

## Qué está decidido y qué está diferido

| Decidido | Diferido |
|---------|----------|
| PostgreSQL + pgvector (una sola BD) | Estructura del grafo de conocimiento |
| FastAPI, REST pragmático | Señales de adaptación |
| Cookies de sesión + fastapi-users | |
| SSE para streaming en tiempo real | |
| SPA React, React Router, rutas fijas | |
| React Query para gestión de estado | |
| LangGraph para orquestación de agentes | |
| Control de acceso basado en compartimentos | |
| Modelo de mandato para la autoridad del agente | |
| Autoalojado, una instancia por empresa | |
| Proveedor de LLM agnóstico (API compatible con OpenAI) | |
| Modelo de datos definido ([data-model.md](/docs/data-model)) | |
| Patrones de comunicación entre agentes (ver [content-generation.md](/docs/content-generation), [chat-agents.md](/docs/chat-agents)) | |
| Procesamiento en segundo plano (ver [background-processing.md](/docs/background-processing)) | |
| Implementación de mandatos (ver [security.md](/docs/security)) | |
| Estrategia de chunking (ver [rag-retrieval.md](/docs/rag-retrieval)) | |
| Latencia de Nivel 3 (ver [frontend-backend-integration.md](/docs/frontend-backend-integration)) | |

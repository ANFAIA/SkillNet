---
title: "Diseño de curso asistido por IA"
order: 17
section: "extensibility"
---

# Diseno asistido por IA del esquema de curso

> **Estado: decisiones arquitectonicas cerradas.** Este documento cubre el flujo de
> creacion de cursos con asistencia de IA: como el admin construye un esquema antes de
> que exista nada en base de datos, y por que cada pieza esta donde esta.
>
> Complementa a `v2-dynamic-courses.md` (que cubre el ciclo completo design-time/runtime)
> y a `content-generation.md` (pipeline v1). Donde este documento contradice al otro,
> gana el mas reciente para la fase de diseno; el runtime no se toca aqui.

Depende de: [v2-dynamic-courses.md](v2-dynamic-courses.md),
[architecture.md](architecture.md), [llm-integration.md](llm-integration.md).

---

## 1. Endpoints de IA sin estado para el diseno

La fase de diseno usa endpoints de IA **sin estado**. El frontend es el espacio de
trabajo: todo el estado vive en React (`useState`) hasta que el admin confirma. Los
endpoints del backend reciben el contexto completo y devuelven resultados sin persistir
nada.

### 1.1 Superficie actual

| Endpoint | Entrada | Salida |
|----------|---------|--------|
| `POST /ai/schema-propose` | `{ title, description, intent_density }` | `{ nodes }` |

### 1.2 Superficie prevista (backlog)

| Endpoint | Proposito |
|----------|-----------|
| `POST /ai/schema-refine` | Refinar un esquema existente a partir de feedback del admin |
| `POST /ai/node-suggest` | Sugerir un nodo nuevo dado el esquema actual |
| `POST /ai/autocomplete` | Completar campos de un nodo (summary, outcome) |

### 1.3 Patron

Cada endpoint es independiente y testeable en aislamiento. No hay sesiones compartidas
ni estado del lado del servidor entre llamadas. El contexto se envia en cada peticion:
un esquema son 5-15 nodos, unos pocos KB, un payload trivial.

### 1.4 Por que sin estado

| Alternativa descartada | Problema |
|------------------------|----------|
| Sesion de workspace en servidor | Cursos huerfanos de sesiones abandonadas; necesita limpieza |
| Redis para estado intermedio | Infraestructura nueva para un dato que cabe en el body |
| Entidad "borrador" en BD | Basura de borradores sin terminar; la lista de cursos se contamina |

Ventajas del enfoque elegido:

- **Sin datos huerfanos.** Una sesion de diseno abandonada no deja rastro en el servidor.
- **Resiliente.** Un recarga del navegador pierde solo el borrador local, no una sesion
  de servidor. El admin puede copiar su borrador antes de cerrar si quiere (es JSON
  plano en React state).
- **Extensible.** Cada nueva funcionalidad de IA es un endpoint nuevo, sin acoplamiento
  a una entidad "workspace". Anadir `POST /ai/schema-refine` no toca ningun endpoint
  existente.
- **Sin infraestructura extra.** No necesita Redis, ni tablas de sesiones, ni cron de
  limpieza.

---

## 2. El curso se crea solo al confirmar

El curso **no** se crea en base de datos cuando el admin empieza a disenar. Se crea solo
cuando el admin acepta el esquema y pulsa "Crear". En ese momento:

```
POST /courses                        → crea el curso (titulo, descripcion, delivery_mode)
PUT  /courses/{id}/schema            → escribe los nodos del esquema
POST /courses/{id}/schema/validate   → gate bloqueante (si el admin valida en el acto)
```

### 2.1 Consecuencias

- La tabla `courses` solo contiene cursos reales, nunca borradores.
- No hacen falta jobs de limpieza de borradores abandonados.
- La lista de "Contenido" del panel de admin refleja exactamente lo que existe.
- El flujo de la SPA es una transicion limpia: React state → POST → la entidad existe.

### 2.2 Contraste con v1

En v1, el curso se crea primero y despues se genera el contenido (`POST /courses/{id}/generate`).
La diferencia es que en v1 el admin no puede disenar nada antes de crear: el curso es un
contenedor vacio hasta que el pipeline termina. En el flujo nuevo, toda la fase creativa
ocurre **antes** de que el curso exista.

---

## 3. Enrutamiento multi-modelo para tareas de diseno

Distintas tareas de IA en la fase de diseno pueden usar modelos distintos. La
infraestructura de `resolve_llm_config(org_settings, purpose=...)` ya soporta seleccion
por proposito.

### 3.1 Asignacion actual

| Tarea | Tipo de modelo | Latencia tipica | Purpose |
|-------|---------------|-----------------|---------|
| Propuesta de esquema | Rapido (8B, GPT-4o-mini) | 2-5 s | `"schema_design"` |
| Generacion de contenido por nodo (runtime) | Pesado | 1-3 s | `"runtime_heavy"` |

La propuesta de esquema solo genera estructura: titulos, resumenes, prerrequisitos. No
genera contenido de aprendizaje. Eso la hace viable para modelos rapidos y baratos.

### 3.2 Asignacion prevista (backlog)

| Tarea | Tipo de modelo | Purpose |
|-------|---------------|---------|
| Sugerencias/autocompletado | Rapido | `"schema_assist"` |
| Modelos fine-tuned por dominio | Especializado | `"schema_design_ft"` |

El router no necesita cambios: anadir un purpose nuevo es declararlo en la configuracion
de la organizacion y pasarlo a `resolve_llm_config`.

---

## 4. Editor interactivo en tiempo real

El editor de esquema separa dos tipos de operaciones por su latencia:

### 4.1 Operaciones locales (instantaneas, sin IA)

- Editar titulo o resumen de un nodo.
- Borrar un nodo.
- Reordenar nodos (drag & drop).
- Anadir un nodo manualmente.
- Cambiar prerrequisitos.

Estas operaciones mutan el estado de React directamente. No generan llamadas al
servidor.

### 4.2 Operaciones de IA (rapidas, 2-5 s)

- Propuesta inicial a partir de un tema.
- Re-propuesta al cambiar la densidad (`intent_density`).
- Sugerencia de nodo nuevo (backlog).
- Autocompletado de campos (backlog).

Patron en la UI:

1. El admin acciona (clic, slider).
2. Indicador de carga sutil (nunca modal bloqueante, nunca spinner de pagina completa).
3. La UI sigue siendo interactiva — el admin puede editar otros nodos mientras la IA
   trabaja.
4. El resultado aparece inline, como el clic-para-explicar (Curio) del runtime: clic →
   llamada rapida → el resultado aparece en el sitio.

---

## 5. Flujo unificado para cursos desde documento y desde tema

Ambos caminos convergen en la misma propuesta de esquema:

```
Desde documento:                        Desde tema:
  subir PDF                               titulo + descripcion
    → parse a Markdown                       |
    → extraer temas                          → extraer temas
        |                                        |
        └──────────────┬─────────────────────────┘
                       ▼
              proponer esquema (misma llamada)
                       ▼
              editor de esquema (misma UI)
```

### 5.1 Diferencias

| Aspecto | Desde documento | Desde tema |
|---------|----------------|------------|
| Entrada a la propuesta | Temas extraidos del Markdown | Temas extraidos del titulo/descripcion |
| Documento fuente | Se asocia al curso para RAG en runtime | No hay documento; el contenido se genera sin RAG |
| Calidad de la propuesta | Mas precisa (temas concretos del material) | Mas generica (depende de la calidad de la descripcion) |

### 5.2 Invariante

El endpoint de propuesta de esquema trabaja a partir de temas extraidos, **no** de
documentos crudos. La extraccion de temas es un paso previo (ya implementado en
`build_schema_graph()` como el nodo `extract_themes_schema`). El documento original, si
existe, se usa mas adelante para RAG cuando se genera contenido de nodo en runtime.

---

## 6. Backlog: fine-tuning para cursos grandes

Para organizaciones con grandes bases documentales o necesidades de dominio especificas.
Nada de esto esta implementado ni planificado a corto plazo.

| Linea | Descripcion |
|-------|-------------|
| Fine-tune de embeddings | Mejorar RAG en dominios especificos (medicina, legal, ingenieria) |
| Fine-tune del modelo de diseno | Aprender de esquemas que los admins aceptan vs rechazan |
| Fine-tune del modelo de generacion | Aprender de renders validados (OpenUI Lang) |
| Chunking adaptativo | Para documentos muy grandes (>100 paginas), estrategia de chunking por estructura |
| Generacion paralela de nodos | Para cursos con 20+ nodos, generar contenido en paralelo en vez de secuencial |

Prerequisito comun: volumen de datos suficiente. Una organizacion con 5 cursos no tiene
datos para fine-tuning. Esto es relevante cuando haya decenas de organizaciones con
cientos de cursos validados.
</content>

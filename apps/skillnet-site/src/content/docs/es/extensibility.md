---
title: "Extensibilidad (MCP/A2A)"
order: 15
section: "extensibility"
---

# Extensibilidad: cómo añadir un componente Didact

**Estado:** guía de referencia (puntos de contacto reales en el código)
**Relacionado:** [`didact-components.md`](/docs/didact-components),
[`didact-integration.md`](/docs/didact-integration), [`design-system.md`](/docs/design-system)

> Un componente de aprendizaje no vive en un solo sitio: cruza el registro de disponibilidad,
> el UI Kit del validador, el kit del frontend (de donde sale el prompt) y —si evalúa— la
> política de evidencia. Esta guía enumera los puntos de contacto **reales** con file:line, para
> que añadir un componente sea una edición local y no una cacería.

## Panorama: las cuatro capas que toca un componente

```
1. Registro de disponibilidad   didact_component_registry.v1.json   (¿instalado? ¿puertos? ¿emisión?)
2. UI Kit (validador)           src/render/kit.py + src/render/spec.py   (props, enums, orden posicional)
3. Kit del frontend + prompt    apps/skillnet-web/.../kit/  →  drift digest   (lo que ve el LLM)
4. Política de evidencia        src/services/evidence_contract_policy.py   (¿certifica? ¿support_only?)
```

## 1. Entrada en el registro de disponibilidad

`apps/skillnet-api/src/personalization/didact_component_registry.v1.json`. Añade un objeto a
`components` con:

- `id` — el `didact.*` del snapshot autoritativo (`didact_snapshot.json`, `available_types`).
- `renderer_mode` — `direct` (render propio de SkillNet), `activity_definition` (vía
  `DidactActivity` cargando una `ActivityDefinition` revisada) o `blocked`.
- `renderer_symbol` — el símbolo del renderer, o `null` si `blocked`.
- `emission` — `enabled` / `disabled` (permiso explícito para OpenUI, independiente de la
  disponibilidad del renderer).
- `required_ports` — subconjunto de los puertos de host. Si pides un puerto fuera de
  `available_host_ports` (`assets`, `clock`, `evaluation`, `persistence`, `progress`), el
  componente queda **degradado/bloqueado** aunque esté instalado. Los puertos posibles están en
  `didact_catalog.py` (`HostPort`: además `events`, `execution`, `media`, `scheduler`,
  `simulation`).
- `authoring_strategy` — `inline`, `server_activity` o `unsupported`.

El catálogo se proyecta en `didact_catalog.py` (`DidactComponentAvailability`,
`AvailabilityStatus` = `READY` / `DEGRADED` / `BLOCKED`). La exposición al prompt es una
segunda operación más estricta en `didact_descriptors.py`: solo un tipo con renderer habilitado
y puertos satisfechos cruza la frontera OpenUI.

## 2. Decláralo en el kit del frontend — `kit.py` se deriva solo

Desde el refactor del catálogo, `apps/skillnet-api/src/render/kit.py` ya no declara
`UI_KIT` a mano: lo *construye* a partir de `openui_catalog.json`, el artefacto generado
desde el kit del frontend. Así que el primer paso es en el frontend, en
`apps/skillnet-web/src/components/courses/kit/`:

- `kit/schemas.ts` — añade el schema zod de las props, y registra el nombre en
  `KIT_COMPONENT_NAMES` (el orden es el orden posicional del dialecto OpenUI, §5.4),
  `KIT_DESCRIPTIONS` y `KIT_PROP_SCHEMAS`.
- Un bloque `.tsx` que lo renderice, exportado desde `blocks/index.ts`.
- `kit/library.tsx` — `defineComponent(...)` y añádelo a `createLibrary`.
- Corre `node scripts/generate-openui-prompt.mjs` (en `apps/skillnet-web`) para
  regenerar `openui_prompt.txt` / `openui_catalog.json`.

`kit.py::_build_ui_kit()` recoge el nombre nuevo de ese artefacto automáticamente —
**no hace falta tocar `kit.py`** para un componente sencillo (props, sin rol de
contenedor, sin reclamar una función de contenido).

Solo toca `kit.py` cuando el componente necesita metadata que solo existe en el
backend y el artefacto no puede expresar — añade una entrada a `_BACKEND_METADATA` para:

- `is_container=True` (puede tener hijos y valer como `root`),
- `functions=(FunctionFit(ContentFunction.X, rank),)` si quieres que la capa de
  funciones lo proponga,
- o, si el componente no viene del catálogo del frontend en absoluto (server-only,
  legacy, o `broker_scoped=True` como `PodcastPlayer`/`InfographicImage`), añádelo a
  `_BACKEND_ONLY_COMPONENTS` en su lugar.

Un componente que quede fuera de `_BACKEND_METADATA` recibe defaults seguros
(`is_container=False`, sin funciones) en vez de descartarse — solo que no puede usarse
como `root` hasta que alguien lo declare explícitamente. `PropKind` (`STRING`,
`NUMBER`, `ENUM`, `STRING_LIST`, `STRING_MATRIX`, `NUMBER_LIST`, `REFS`) se infiere del
schema zod; los `REFS` mapean a `Component.children`, nunca a `props`.

Las reglas de estructura las hace cumplir `src/render/spec.py`: el `root` debe ser contenedor
(regla 1), máximo `MAX_ROOT_CHILDREN = 5` hijos de raíz (regla 4), etc. `spec.py` es la única
capa que valida props/enums/aridad; el parser OpenUI solo comprueba presencia y aridad.

## 3. Los tests de la lista congelada son la revisión real

Ya no hay un digest de drift para mantener honestos dos catálogos escritos a mano —
solo queda uno (el kit del frontend), y `kit.py` se deriva de él. Lo que queda es una
guardarraíl deliberada: `tests/test_render_kit.py::test_catalogue_is_the_frozen_list` y
sus vecinos **fallan a propósito** cuando aparece un componente nuevo que nadie ha
revisado, para que no se pueda desplegar uno en silencio. Actualiza la lista congelada
en ese test junto con tu decisión de `_BACKEND_METADATA` (¿contenedor? ¿función de
contenido? ¿broker-scoped?) — ese es el paso de revisión real, no papeleo que rodear.

Un componente `broker_scoped` (`PodcastPlayer`, `InfographicImage`) está deliberadamente
ausente del catálogo del frontend (`KIT_COMPONENT_NAMES`) y lo inyecta el media broker
por nodo en su lugar — ver `schemas.ts` para el porqué.

## 4. La familia de certificación (si el componente evalúa)

Si el componente comprueba conocimiento y quieres que **certifique dominio**, debe entrar en la
política de evidencia: `apps/skillnet-api/src/services/evidence_contract_policy.py`.

- La familia certificable es `_FACT_RECOGNITION_COMPONENTS`, respaldada por un **scorer
  determinista real** (hay un guard de import-time `_UNSCORABLE`: un componente sin scorer no
  puede certificar).
- Se acepta (`EvidencePolicyAccepted`, `evidence_type="grounded_fact_recognition"`, con un
  `oracle_ref`) solo una misión `RECOGNIZE` cuyos átomos de evidencia estén todos en
  `_RECOGNIZABLE_ATOM_KINDS = {FACT, PROCEDURE_STEP, CRITERION}`.
- En cualquier otro caso el nodo **declina a `support_only`** con un motivo tipado
  (`CRITICAL_ORACLE_UNAVAILABLE`, `EXECUTION_ORACLE_UNAVAILABLE`, `RUBRIC_ORACLE_UNAVAILABLE`,
  `REQUIRED_EVIDENCE_UNSUPPORTED`). Un componente nuevo que evalúe sin un oráculo fiable **no
  debe** certificar: se sirve como práctica no evaluativa. El scorer de las actividades vive en
  `src/services/didact_evidence.py`.

Regla de honestidad reflejada en el prompt (`llm/prompts/runtime.py`): un nodo de
conocimiento/recall certifica con una evaluación real y variada; solo cuando no existe un check
fiable la pantalla se queda en práctica y **no** certifica.

## 5. Checklist para un componente nuevo

1. ¿Está el `didact.*` en `didact_snapshot.json` (`available_types`)? Si no, no es un tipo
   Didact instalado.
2. Registro: añade la entrada en `didact_component_registry.v1.json` con `renderer_mode`,
   `emission`, `required_ports`, `authoring_strategy`. Si pide un puerto no disponible, quedará
   bloqueado (documenta el hueco en [`didact-components.md`](/docs/didact-components)).
3. Kit del frontend: schema + bloque + entrada en `library.tsx`, luego regenera el
   artefacto (`generate-openui-prompt.mjs`). `kit.py` se deriva solo — solo añade una
   entrada en `_BACKEND_METADATA` si es contenedor o reclama una función de contenido.
4. Actualiza la lista congelada en `tests/test_render_kit.py` (o marca `broker_scoped`
   si va por el broker en vez del prompt).
5. Certificación: si evalúa, dale un scorer determinista y decláralo en
   `evidence_contract_policy.py`; si no hay oráculo fiable, que declive a `support_only`.
6. Verifica con el banco de calidad: `uv run python scripts/lesson_quality_bench.py --self-test`
   y, contra renders reales, `--db`.
</content>

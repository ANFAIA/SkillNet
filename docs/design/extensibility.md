# Extensibilidad: cómo añadir un componente Didact

**Estado:** guía de referencia (puntos de contacto reales en el código)
**Relacionado:** [`didact-components.md`](didact-components.md),
[`didact-integration.md`](didact-integration.md), [`design-system.md`](design-system.md)

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

## 2. Entrada en el UI Kit (la capa del validador)

`apps/skillnet-api/src/render/kit.py`. Añade un `ComponentSpec` a la tupla `UI_KIT.components`
(el orden **es** el orden posicional del dialecto OpenUI, §5.4). Define:

- `name`, `purpose`.
- `props` — tupla de `PropSpec(name, kind, description, choices)`. `PropKind` admite
  `STRING`, `NUMBER`, `ENUM`, `STRING_LIST`, `STRING_MATRIX`, `NUMBER_LIST`, `REFS`
  (los `REFS` mapean a `Component.children`, nunca a `props`).
- Banderas según el caso: `is_container`, `llm_emittable=False` (solo fallback/legacy),
  `broker_scoped=True` (solo cuando el media broker lo inyecta por nodo, se excluye del digest
  de drift — ver `PodcastPlayer`/`InfographicImage`), `legacy_parseable=True` (playback de
  programas históricos), y `functions=(FunctionFit(ContentFunction.X, rank),)` si quieres que la
  capa de funciones lo proponga.

Las reglas de estructura las hace cumplir `src/render/spec.py`: el `root` debe ser contenedor
(regla 1), máximo `MAX_ROOT_CHILDREN = 5` hijos de raíz (regla 4), etc. `spec.py` es la única
capa que valida props/enums/aridad; el parser OpenUI solo comprueba presencia y aridad.

## 3. Sincronizar el kit del frontend y el prompt

Desde 2026-07-26 **el prompt no sale de `kit.py`**: lo genera `library.prompt()` desde el kit
del frontend (`apps/skillnet-web/src/components/courses/kit/`) hacia los artefactos que
`src/render/prompt.py` lee. Los dos catálogos se mantienen honestos por un **hash**, no por
disciplina:

- `prompt.catalog_digest_from_kit()` recalcula el catálogo normalizado desde `kit.py`.
- `tests/test_render_prompt_artifact.py` **falla** cuando el digest deja de coincidir con el
  artefacto del frontend.

Flujo práctico: si cambias el componente en `kit.py`, el test de drift te dice que regeneres el
artefacto del frontend; si lo cambias en el frontend, te dice que actualices `kit.py`. Un
componente `broker_scoped` se excluye a propósito del digest (`llm_components`), por eso puede
llevar firma en `kit.py` sin regenerar el artefacto.

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
   bloqueado (documenta el hueco en [`didact-components.md`](didact-components.md)).
3. Validador: añade el `ComponentSpec` en `render/kit.py`; deja que `render/spec.py` valide.
4. Prompt: regenera el artefacto del frontend hasta que
   `tests/test_render_prompt_artifact.py` pase (o marca `broker_scoped` si va por el broker).
5. Certificación: si evalúa, dale un scorer determinista y decláralo en
   `evidence_contract_policy.py`; si no hay oráculo fiable, que declive a `support_only`.
6. Verifica con el banco de calidad: `uv run python scripts/lesson_quality_bench.py --self-test`
   y, contra renders reales, `--db`.

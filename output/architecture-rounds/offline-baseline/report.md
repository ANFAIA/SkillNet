# Rondas de arquitectura de experiencias

- Modo: `offline`
- Resultado global: **PASS**
- Rondas: 8

| Ronda | Hipotesis | Gate |
|---|---|---|
| R1 | Contrato neutral | PASS |
| R2 | Evidencia normalizada a mastery | PASS |
| R3 | Registro de adaptadores y fallback | PASS |
| R4 | Generacion multiagente en design-time | PASS |
| R5 | Ritmos flexibles y personalizacion | PASS |
| R6 | Runtime rapido sin LLM | PASS |
| R7 | Segundo proveedor stub | PASS |
| R8 | Migracion y regresion v1/v2 | PASS |

## R1 - Contrato neutral

- `provider_leaks`: 0.0
- `resolved_bindings`: 1.0

Evidencia:

- intent={"goal": "explain", "requirements": ["explain"]}
- binding=('didact', 'step-sequence')

## R2 - Evidencia normalizada a mastery

- `accepted_attempts`: 2.0
- `duplicate_updates`: 0.0
- `mastery`: 0.4

Evidencia:

- correct=+0.30
- duplicate=+0.00
- partial=+0.10

## R3 - Registro de adaptadores y fallback

- `known_resolved`: 1.0
- `fallback_resolved`: 1.0
- `unknown_safe`: 1.0
- `central_component_switches`: 0.0

Evidencia:

- known=('didact', 'quiz')
- fallback=('legacy-read', 'text')
- unknown=None

## R4 - Generacion multiagente en design-time

- `specialists`: 4.0
- `coverage`: 1.0
- `parallel_speedup`: 2.385
- `runtime_authoring_calls`: 0.0

Evidencia:

- simulated_sequential_s=31.0
- simulated_parallel_s=13.0

## R5 - Ritmos flexibles y personalizacion

- `unique_rhythms`: 4.0
- `maximum_step_repeat`: 2.0
- `brief_first_rate`: 0.75

Evidencia:

- novice=brief > worked-example > guided-practice > transfer
- expert=brief > challenge > contrast > transfer
- refresh=retrieval > brief > scenario > retrieval
- procedural=brief > steps > simulation > transfer

## R6 - Runtime rapido sin LLM

- `llm_calls`: 0.0
- `simulated_latency_ms`: 4.0
- `deterministic_selection`: 1.0
- `baseline_available`: 1.0

Evidencia:

- selected=baseline
- selection_digest=8ba8496a2525

## R7 - Segundo proveedor stub

- `before_uses_didact`: 1.0
- `after_uses_video`: 1.0
- `intent_schema_changes`: 0.0
- `resolver_changes`: 0.0

Evidencia:

- before=('didact', 'step-sequence')
- after=('video-stub', 'micro-explainer')

## R8 - Migracion y regresion v1/v2

- `delivery_matches`: 1.0
- `legacy_new_writes`: 0.0
- `historical_read_path`: 1.0

Evidencia:

- delivery=v1,v1,v2
- new_legacy_blocks=0

## Alcance

Este informe es un oracle offline de arquitectura. No demuestra la integracion productiva; cada ronda debe volver a ejecutarse contra adaptadores, persistencia y rutas reales al implementarlos.

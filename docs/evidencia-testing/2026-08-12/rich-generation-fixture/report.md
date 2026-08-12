# Generación rica con Didact — experimento fixture

Fecha: 2026-08-12  
Banco: `rich-generation/1`  
Modelo: `fixture-small/1` (proxy determinista, sin red)  
Matriz: 13 temas × 2 perfiles × 5 semillas × 5 brazos = 650 ejecuciones

## Pregunta

¿Qué límite de información ayuda a un modelo pequeño a producir experiencias variadas,
personalizadas y adecuadas al tema sin perder validez ni grounding?

Todos los brazos reciben los mismos hechos fuente, perfiles y semillas. El catálogo se
lee del snapshot Didact fijado en el repositorio (34 tipos). El coste es 0 USD porque no se
usa un proveedor. La latencia medida es solo la selección local, no generación LLM.

## Brazos

- `legacy`: una actividad central entre `QuizItem`, `Table` y `StepSequence`.
- `full-catalog`: el decoder ve los 34 contratos a la vez.
- `shortlist`: primero se reducen a cinco candidatos mediante facetas.
- `intent-activity`: intención tipada, pero autoría genérica (`title/description/steps`).
- `intent-schema-activity`: intención tipada y contrato de autoría específico del componente.

El ruido sembrado de `full-catalog` representa una capacidad de decisión limitada. Es un
fixture comparativo, no una afirmación sobre la tasa de error de un modelo comercial.

## Resultados

| Brazo | Gate E2E | Calidad candidato | Affordances | Evidencia | Tema | Profundidad | Tipos usados | Cambio causal por perfil | Tokens entrada / salida |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Legacy | 100% | 27,8 | 4,5% | 73,1% | 20,5% | 30,8% | 3 | 0% | 85,7 / 87,3 |
| Catálogo completo | 0% | 76,9 | 80,8% | 85,1% | 80,8% | 89,6% | 17 | 52,3% | 295,6 / 90,6 |
| Shortlist 5 | 0% | 83,0 | 94,6% | 82,8% | 91,5% | 94,2% | 12 | 4,6% | 89,3 / 90,7 |
| Intent + autoría genérica | 0% | 88,2 | 94,9% | 97,4% | 93,6% | 97,1% | 11 | 15,4% | 132,8 / 137,8 |
| Intent + esquema específico | **100%** | **89,8** | **94,9%** | **100%** | **96,2%** | **99,0%** | 11 | 15,4% | 133,3 / 228,1 |

`Calidad candidato` mide la adecuación semántica antes de gates. La calidad final solo se
publica cuando pasan validez y grounding. Por eso los brazos intermedios pueden encontrar
un buen tipo y aun así tener 0% E2E: escoger bien no equivale a poder renderizarlo.

## Regresión real reproducida: defensa de boxeo

Se añadió como fixture dura la pantalla observada en la aplicación:

- el selector escoge `didact.data-explorer`;
- la definición contiene `title`, `description` y `steps`, pero no `task`, `axes`, `series`
  ni `interaction`;
- el renderer monta y termina mostrando “There is no data”;
- además aparecen vídeo, compañero, saco y sparring sin referencias en la fuente.

El gate nuevo la rechaza por dos motivos independientes:

1. `AUTHORING_SCHEMA_INVALID`: un data explorer sin serie no es una actividad degradada,
   es una elección imposible;
2. `UNSUPPORTED_CLAIM`: las prácticas añadidas no están vinculadas a ningún `source_ref`.

La variante guiada por esquema no intenta rellenar esos huecos inventando datos. Elige un
componente compatible o crea una definición con todos los campos obligatorios anclados a
los hechos disponibles.

## Qué hemos aprendido

1. **Mostrar los 34 contratos directamente no es la solución.** En este proxy consume 3,3×
   más contexto que shortlist y reduce 6,1 puntos la calidad de selección.
2. **Shortlist mejora la elección, no la autoría.** La cobertura sube mucho, pero una forma
   genérica de `title/description/steps` es inválida para los componentes ricos.
3. **`ExperienceIntent` sí añade valor**, especialmente para evidencia, tema y profundidad,
   pero necesita llegar hasta un esquema de autoría por componente.
4. **Más componentes no deben significar más componentes por pantalla.** La mejor variante
   compone un segundo componente solo si aporta una acción, evidencia o representación que
   falta. La riqueza medida es funcional.
5. **Personalización aún es débil.** El 15,4% de cambio causal mejora al 0% legacy, pero está
   lejos de un objetivo razonable de ≥75% en casos donde la preferencia es aplicable.
6. **Un cambio frecuente no es automáticamente bueno.** `full-catalog` cambia 52,3% entre
   perfiles, pero parte del cambio procede del ruido y su adecuación es peor.
7. **La selección cuesta menos de 0,2 ms.** El coste relevante estará en la autoría; la
   variante válida produce más estructura (228 tokens de salida frente a ~91).

## Decisión recomendada

No promocionar “catálogo completo en el prompt”. Mantener el inventario completo detrás de
un selector y llevar al runtime esta secuencia:

1. `ExperienceIntent` sin nombres de componentes;
2. shortlist renderer/puertos/datos compatible de 3–5 tipos;
3. esquema de autoría exacto del componente elegido;
4. validación server-side de campos y semántica (por ejemplo, `series` no vacía);
5. grounding por campo/claim, no solo una lista decorativa de `source_refs`;
6. `Decline` y nueva elección cuando la fuente no permite construir la actividad.

Antes de considerar cerrada la mejora hacen falta dos rondas reales:

- fixture del grafo completo con definiciones válidas por familia y montaje de los 34 tipos;
- generación ciega con un modelo pequeño real, previa autorización para enviar los packs,
  midiendo además fallos de montaje, latencia y tokens reportados por el proveedor.

## Artefactos

- Fixture: `apps/skillnet-api/tests/fixtures/rich-generation-v1.json`
- Harness: `apps/skillnet-api/scripts/rich_generation_bench.py`
- Tests: `apps/skillnet-api/tests/test_rich_generation_bench.py`
- Resultado completo: `docs/evidencia-testing/2026-08-12/rich-generation-fixture/report.json`

Los seis tests del harness pasan. La ejecución se verificó con Python 3.11; el entorno
Python del repositorio estaba bloqueado por permisos del caché local de `uv`, por lo que no
se afirma aquí que se haya ejecutado la suite completa de la API.

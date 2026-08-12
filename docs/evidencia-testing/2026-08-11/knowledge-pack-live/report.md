# Piloto live — fuente raw frente a `NodeKnowledgePack`

Fecha: 2026-08-11. Modelo: `gpt-4o-mini`. Estado: **NO-GO para activar en runtime**.

## Diseño

Se usaron tres nodos del banco de calidad: apertura/cierre de caja, alérgenos en hostelería y
atención de reclamaciones. El baseline raw contiene tres repeticiones por nodo (`n=9`). La condición
pack final contiene una repetición válida por nodo (`n=3`) después de preparar cada dossier con dos
llamadas: extractor y revisor.

La tanda no quedó intercalada y los tamaños son distintos. Por tanto sirve como piloto de
integración y descubrimiento de fallos, no como estimación causal.

Evidencia pack: [`runs/quality-20260811-204114.json`](runs/quality-20260811-204114.json). Existe
además un smoke anterior de apertura en
[`../knowledge-pack-debug/runs/quality-20260811-202951.json`](../knowledge-pack-debug/runs/quality-20260811-202951.json).

## Resultado de runtime

| Métrica | Raw (`n=9`) | Pack generado (`n=3`) | Lectura |
|---|---:|---:|---|
| Primera pasada | 9/9 | 3/3 | Empate; sin repairs ni fallback |
| Latencia media | 8,12 s | 6,25 s | -23 %, no causal con `n=1`/nodo |
| p50 | 7,53 s | 6,06 s | Prometedor, pero dentro del ruido observado |
| Entrada media | 632,3 tokens | 627 tokens | -0,8 %, esencialmente igual |
| Salida media | 35,2 tokens | 36 tokens | +2,3 %, esencialmente igual |
| Tipos del catálogo usados | 8/13 | 8/13 | Sin aumento global |
| Tipos distintos/pantalla | 5,0 | 5,0 | Sin aumento global |

Por nodo, pack tardó 5,11 s en apertura, 7,59 s en alérgenos y 6,06 s en reclamaciones. Las medias
raw correspondientes eran 6,75 s, 9,87 s y 7,72 s. Una sola observación pack no separa el efecto del
dossier de la variación del proveedor.

La composición tampoco es inequívocamente más rica:

- apertura: idéntica familia estructural (`TextContent`, `BeforeAfter`, `Callout`, `QuizItem`);
- alérgenos: pack eliminó `BeforeAfter` y conservó `Table`, `Callout` y `QuizItem`;
- reclamaciones: pack añadió `Table` al flujo `StepSequence` + `DragOrder`.

## Coste de preparación

Preparar los tres packs consumió 7.801 tokens de entrada y 3.178 de salida, con 35,57 s acumulados
en esta ejecución secuencial. A las tarifas usadas en el piloto ($0,15/M entrada y $0,60/M salida),
el coste aproximado fue **$0,00308 total**, unos **$0,00103 por nodo**.

Los tres renders pack costaron aproximadamente $0,000347 total ($0,000116/render), prácticamente
lo mismo que raw. El pack no reduce hoy el coste de runtime; añade una preparación amortizable entre
los alumnos que usen el nodo.

## Bloqueante pedagógico

La telemetría revela cobertura insuficiente:

| Nodo | Átomos | Invariantes |
|---|---:|---:|
| Apertura/caja | 0 | 0 |
| Alérgenos | 2 | 1 |
| Reclamaciones | 2 | 1 |

Que apertura renderice correctamente con cero átomos demuestra que el pipeline puede apoyarse en el
título, resumen y defaults para producir una pantalla plausible; **no demuestra que el pack conserve
la fuente**. Tampoco se guardaron en esta primera versión el Markdown completo ni la `ui_spec`
exitosa, así que no es posible puntuar retrospectivamente cobertura factual. El benchmark ya queda
corregido para guardar ambos artefactos en futuras tandas.

Además, el generador queda cerrado tras el piloto: cero invariantes o cualquier `missing_data`
bloqueante produce `status=review_required`, y el brazo pack del benchmark se niega a renderizarlo.
Una pantalla plausible ya no puede convertir un dossier pedagógicamente vacío en un falso éxito.

## Fallos que el experimento descubrió

Antes de obtener los tres resultados válidos, el modelo intentó:

1. inventar alias de campos internos aunque las cinco secciones superiores fueran correctas;
2. devolver el sobre del prompt en vez del candidato revisado;
3. copiar literalmente placeholders de enum como `fact|safety_rule|...`;
4. reutilizar el mismo `atom_id` entre invariantes y seleccionables;
5. copiar referencias de ejemplo inexistentes;
6. declarar evidencia obligatoria cuyo átomo no existía.

Ninguno llegó a persistencia ni a una pantalla. Como resultado, identidad y referencias pasan a ser
propiedad del programa: namespaces deterministas, actualización de referencias, eliminación de
relaciones desconocidas y conversión de evidencia obligatoria huérfana en `missing_data` bloqueante
para revisión humana. El selector trata seguridad y evidencia ausentes como `Declined` aunque el
caller no las pida explícitamente.

## Decisión

No activar el pack en runtime. La vertical demuestra que la arquitectura puede funcionar y que el
coste de preparación es pequeño, pero todavía no demuestra cobertura factual ni mayor riqueza.

Siguiente experimento, sin cambiar producción:

1. exigir cobertura mínima computable sobre hechos/reglas esperados antes de marcar un pack `ready`;
2. guardar siempre pack, Markdown y `ui_spec` canónica;
3. ejecutar raw/pack intercalado con 5–10 repeticiones por celda;
4. evaluación ciega de exactitud, seguridad, evidencia y personalización;
5. probar varios perfiles sobre el mismo pack, manteniendo invariantes idénticos;
6. activar solo si cobertura crítica es 100 % y calidad supera raw sin depender de más componentes.

### Variables añadidas para la siguiente ronda

`quality_bench.py` permite variar independientemente:

- `--pack-extractor-tokens` y `--pack-reviewer-tokens` (256–2.048);
- `--pack-min-invariants`;
- `--pack-max-atoms`;
- `--pack-min-fact-coverage` (0–1);
- `--pack-require-evidence` / `--no-pack-require-evidence`.

Los tres nodos tienen ahora siete comprobaciones gold cada uno, no enviadas al modelo. La cobertura se
mide únicamente sobre campos semánticos del pack, nunca sobre el texto fuente copiado ni sobre
metadata. Un check puede exigir varios términos: por ejemplo, el hecho de retirada de caja requiere
que aparezcan tanto `600 euros` como `buzón`.

Matriz propuesta para aislar la extracción antes de volver a renderizar:

| Variante | Extractor/revisor | Mín. invariantes | Cobertura | Evidencia | Hipótesis |
|---|---:|---:|---:|---:|---|
| compacta | 1.200 / 1.200 | 1 | 80 % | no | Más barata, riesgo de omisión |
| equilibrada | 1.600 / 1.600 | 3 | 100 % | sí | Candidata principal |
| cobertura | 2.048 / 2.048 | 5 | 100 % | sí | Techo para saber si faltaban tokens |

Primero se generan packs sin renders: 3 variantes × 3 nodos × 2 llamadas = 18 llamadas. Solo la
variante que alcance 100 % de hechos críticos pasa después al A/B de pantallas. Esto separa calidad
del dossier de calidad de OpenUI y evita gastar renders sobre packs que ya sabemos incompletos.

Verificación posterior: 63 pruebas focalizadas y 2.877 pruebas unitarias de backend superadas; Ruff
limpio. No se hicieron más llamadas externas después del pase registrado.

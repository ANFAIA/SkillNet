# Personalización on the fly: matriz contrafactual R1

Fecha: 2026-08-12  
Harness: `apps/skillnet-api/scripts/personalization_counterfactual_bench.py`  
Resultado completo: `results.json`

## Pregunta

Con el mismo nodo, fuente, curso, modelo y repetición, ¿cambiar una sola señal del perfil
produce una adaptación trazable y útil sin perder hechos, romper la caché o mover una
pantalla que ya está fijada?

## Qué se ejecutó

Se probaron 14 contrafactuales emparejados, cinco repeticiones cada uno:

- presentación visual, textual e interactiva;
- detalle conciso y detallado;
- imágenes preferidas y evitadas;
- experiencia nula y experimentada;
- bloques cortos y reducción de movimiento;
- vector aprendido dominante en ejercicio o datos;
- el mismo vector durante calibración, cuando todavía está «frío».

El recorrido usa fronteras reales del runtime, sin activar cambios de producto:

1. proyección cerrada del perfil;
2. planificación sobre el inventario completo;
3. construcción de los prompts de selector y generación;
4. material de clave de caché;
5. contrato de pin estable de `NodeRenderService`.

El universo Didact fue auditado explícitamente: **34 de 34 tipos**, con sus identificadores
guardados en el JSON. El planner también recibe los 15 bloques heredados, por lo que el
inventario creativo total observado es 49.

## Resultados

| Métrica | Resultado |
|---|---:|
| Pares contrafactuales | 14 |
| Repeticiones | 5 por perfil |
| La señal cambió el prompt | 13/14 (92,9 %) |
| La señal invalidó la caché | 14/14 (100 %) |
| Cambio en plan/componentes/soporte | 4/14 (28,6 %) |
| Hechos críticos conservados en prompt | 100 % |
| Ruido semántico intraperfil | 0/14 |
| Tiempo del tramo determinista | 10,36 ms de media (5,83–19,05 ms) |

Cambios causales claros:

- `presentation-visual` cambió representación, componentes, affordances, evidencia y
  shortlist visible al generador;
- `presentation-textual` cambió representación, componentes y affordances;
- `accessibility-short-blocks` redujo densidad y cambió la política de soporte;
- `accessibility-reduced-motion` cambió componentes y affordances y quedó correctamente
  separado en caché tras la regresión descubierta por esta matriz.

Las preferencias de detalle, imágenes y experiencia sí aparecen literalmente en los dos
prompts y particionan la caché, pero el plan determinista no cambia. Esto no demuestra que
sean inútiles: su efecto pertenece al turno generativo y `fixture/local` no genera texto
semántico. Sí demuestra que hoy no existe una garantía estructural de que el modelo las
obedezca.

El vector caliente cambia el prompt y la clave (`texto`, `ejercicio`, `dato`), pero no la
shortlist. Durante los tres primeros nodos queda correctamente suprimido. Por tanto, el
vector influye hoy en la decisión del modelo, no en la selección determinista de Didact.

La presentación interactiva alcanzó el prompt, pero no cambió el plan: los candidatos
interactivos que mejor encajaban requerían puertos que el objetivo fijo no declaraba. Es
una señal de que «tener los 34» no basta si la etapa de creación del curso no declara los
recursos/puertos que pueden materializarse.

## Hallazgo y corrección

`reduce_motion` modifica el planner y la shortlist, pero no forma parte de la clave de
caché. Dos personas con distinto requisito de reducción de movimiento pueden compartir
una renderización aunque su plan esperado sea distinto. La matriz detectó esa colisión y
se corrigió con un bucket cerrado y versionado: `a1:rm*:hc*:et*`. Incluye únicamente
`reduce_motion`, `high_contrast` y `extra_time`, las capacidades que alteran la selección;
ignora claves desconocidas y texto libre. `short_blocks` no se duplica porque ya queda
representado por `effective_density`. La repetición posterior obtuvo **cero cambios
semánticos sin invalidación de caché**.

Los pins se comportan como se diseñó: cambiar preferencias no reemplaza una pantalla que
la persona ya está leyendo. La nueva clave se aplica al siguiente nodo sin pin o tras una
regeneración explícita. El test lo verifica sin tocar base de datos ni renders reales.

## Qué prueba y qué no

Esta ronda prueba el **plumbing**: las señales llegan, se proyectan, alteran o no alteran el
plan de forma reproducible, conservan la fuente y construyen claves observables.

No prueba calidad lingüística, aprendizaje, latencia del proveedor, tokens ni coste. El
backend `fixture/local` devuelve grabaciones por hash y no es un modelo pequeño capaz de
obedecer una variante nueva; inventar tokens o coste habría sido una medida falsa.

## R2 necesaria: generación real

Ejecutar el mismo diseño emparejado con uno o dos modelos pequeños reales y tres temas
distintos (procedimiento, decisión y comprensión visual):

- 14 perfiles × 3 nodos × al menos 5 semillas por modelo;
- invalidar y regenerar cada variante sin reutilizar el pin del par anterior;
- guardar programa validado, componentes, actividad autorada, hechos citados, latencia,
  tokens, coste, reparaciones y fallback;
- evaluación ciega de adecuación al perfil, adecuación al tema, riqueza con propósito,
  claridad, grounding y calidad del feedback;
- medir cambio entre perfiles frente a ruido entre repeticiones del mismo perfil;
- exigir que el cambio interperfil supere claramente el ruido intraperfil.

La promoción de una estrategia debe depender de esa R2, no del proxy offline. Mientras
tanto, los 34 componentes siguen siendo el universo creativo auditable.

# Cursos lineales — lo que queda abierto

> **Estado: dos decisiones pendientes, ninguna urgente.** Nada de lo que hay aquí está
> a medias en el repo: lo que se hizo el 2026-08-28/29 está entero, probado y coherente.
> Esto es trabajo futuro, no deuda.
>
> De las cinco de la lista original quedan dos: el candado y la acreditación por nodo. Las
> otras tres se cerraron el 2026-08-29 y están abajo, en "Lo que ya se decidió"; las pistas
> y el contador por actividad también, resumidos en su sitio.
>
> El porqué de la dirección está en `future-progression-modes.md`. Esto es la lista corta.

## Dónde quedó

Los cursos son lineales. Se recorren de principio a fin, la maestría se mide sin gobernar
la navegación, un ítem que no se acierta entrega la solución al cuarto fallo, y un curso
terminado dice que se completó sin llevar nota **y sin derivar nivel de nada**: aquí no
hay exámenes, así que terminar el curso es el único criterio y acredita las habilidades
que ese curso cubre.

El problema que motivó todo —un nodo expositivo terminado dejaba el siguiente cerrado para
siempre, curso clavado al 33 %— está arreglado y cubierto.

## 1. ¿Basta con pasar por la lección, o hay que responder?

El candado **se hizo** el 2026-08-29: es el modo `sequential` de `navigation_mode`
(migración 0034), y canda donde debía — en `POST /nodes/{id}/complete`, no dentro del
predicado, que está escrito dos veces y ya costó un fallo.

Lo que queda es una pregunta que se planteó y nunca se contestó, porque el modo la
esquivó: hoy `sequential` abre la siguiente lección cuando la anterior está **hecha**, y
«hecha» incluye haber llegado al final del contenido sin responder nada.

> Un curso clásico puro se conforma con eso. Si quieres que además haya que **resolver la
> prueba** cuando el nodo tiene una, es otra regla — más exigente, y ya segura, porque toda
> actividad tiene salida garantizada desde ese mismo día.

No es urgente y se contesta mirando un curso, no razonando.

## 2. Las pistas y el contador por actividad — hechos el 2026-08-29

Estaban aquí como puntos 2 y 3 y se cerraron el mismo día, en `2254851`. Se resume porque
lo que importa es cómo encajaron:

**Eran el mismo problema.** La familia Didact no tenía contador propio por aprendiz, y de
esa única causa salían tres síntomas: `/evaluate` contaba fallos del nodo entero, «te
quedan N pistas» no significaba nada, y una solución revelada se olvidaba al recargar.
`learner_activity_states` (migración 0035) los cierra los tres.

**Las pistas no se autoraron.** Son deterministas, calcadas de la escalera del `QuizItem`:
el primer elemento de una secuencia, dos opciones descartadas en una elección, la forma de
una respuesta escrita. Autorarlas con el modelo sigue sobre la mesa y sería mejor prosa,
pero no hacía falta para que nadie se quede encerrado, que era el objetivo.

**Y una decisión que no es obvia:** en una asignación, la segunda pista nombra la primera
fila de la columna izquierda y **no** un par. Una secuencia puede permitirse regalar su
primer elemento; un par de asignación es una respuesta entera.

## 3. Acreditar por nodo, no por curso

**La forma buena, y hoy es un no-op.** Terminar un curso acredita, al nivel `medium` y sólo
hacia arriba, **todas** las habilidades de `course_skills`. Es un criterio honrado —se hizo
el trabajo— pero grueso: el aprendiz recorrió unos nodos concretos, y son esos los que dicen
qué cubrió.

La vía por nodo ya está montada entera. `course_nodes.skill_id` existe, y
`MasteryEvidenceService` llama a `SkillService.record_mastery` en la transición 6 con la
maestría medida en ese nodo — el único sitio donde derivar un nivel es legítimo, porque el
número viene de evidencia sobre *esa* habilidad y no del promedio de un curso.

**Lo que falta no es una regla: es el dato.** El diseñador de esquema **no rellena
`skill_id`** (`src/agents/schema/nodes.py` construye cada `CourseNode` sin ese campo, y
`_auto_create_skills` cuelga las habilidades que inventa de `course_skills`, a nivel de
curso). En todo curso generado la columna es NULL, `record_mastery` sale por la puerta de
arriba y la acreditación por nodo no escribe nada. Comprobado el 2026-08-29.

Así que el trabajo es: que el diseñador mapee cada nodo a una habilidad —creándola o
reusando una de la org, como ya hace a nivel de curso— y decidir después si el cierre del
curso sigue acreditando en bloque o se queda sólo con la suma de sus nodos.

## Lo que ya se decidió (2026-08-29)

Estaba aquí como puntos 4 y 5. Se queda escrito porque el motivo importa más que el cambio.

- **La puerta trasera de `POST /enrollments/{id}/complete`: cerrada con `409`.** Esa ruta es
  la regla de v1 y ahora comprueba `resolve_delivery`. Se eligió negar y no delegar en
  `close_dynamic_if_mastered`: un curso dinámico no tiene botón de "he terminado" *por
  diseño* —el cierre se computa y se dispara solo en los eventos que pueden moverlo—, así
  que delegar habría construido justamente el botón que el diseño rechaza. Negar es además
  la respuesta veraz: si sus nodos están hechos, la matrícula ya está cerrada. La guarda va
  delante de la rama idempotente, para que la puerta quede cerrada para el curso y no sólo
  para las filas que esa llamada habría escrito. v1 no cambia:
  `tests/integration/test_v1_regression.py` sigue verde y hay tres tests unitarios nuevos
  en `tests/test_course_closure.py`.
- **El promedio de nota del panel de admin: quitado entero.** No se restringió a cursos
  estáticos ni se cambió por otra cosa, porque **no hay exámenes**: una nota media no tenía
  nada que promediar, y encima mezclaba dos magnitudes (fracción de lecciones en v1, media
  de maestría en filas v2 viejas) que ninguna consulta separa a posteriori. La consulta, el
  campo del esquema y el tipo del cliente se fueron; la tarjeta ya no estaba (la sustituyó
  la tasa de finalización en `026a6f1`). **`enrollments.score` no se borra**: guarda la
  historia de las matrículas cerradas y v1 la sigue escribiendo.
- **El nivel derivado de la maestría, en la acreditación por curso: fuera.**
  `CourseCompletion.measured_mastery`, `measured_nodes` y `mastery_service.node_was_measured`
  se borraron con él, junto con las dos columnas que sólo ellos leían en las proyecciones
  (`course_node_repo.mastery_rows`, `NodeProgressRow`). `mastery_to_level` y
  `SkillService.record_mastery` **no se tocaron**: la vía por nodo sí tiene una medición que
  traducir, y es el punto 4 de arriba.

## Lo primero que haría quien retome esto

**Abrir un curso y recorrerlo entero como aprendiz.** Todo lo del 28 y el 29 cambia lo que se
ve en pantalla, y se decidió leyendo código y midiendo contra la API. Nadie lo ha mirado aún
con los ojos de quien lo usa, y el candado es precisamente la decisión que se contesta
mejor mirando que razonando.

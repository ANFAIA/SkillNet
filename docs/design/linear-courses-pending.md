# Cursos lineales — lo que queda abierto

> **Estado: cinco decisiones pendientes, ninguna urgente.** Nada de lo que hay aquí está
> a medias en el repo: lo que se hizo el 2026-08-28/29 está entero, probado y coherente.
> Esto es trabajo futuro, no deuda.
>
> El porqué de la dirección está en `future-progression-modes.md`. Esto es la lista corta.

## Dónde quedó

Los cursos son lineales. Se recorren de principio a fin, la maestría se mide sin gobernar
la navegación, un ítem que no se acierta entrega la solución al cuarto fallo, y un curso
terminado dice que se completó sin llevar nota.

El problema que motivó todo —un nodo expositivo terminado dejaba el siguiente cerrado para
siempre, curso clavado al 33 %— está arreglado y cubierto.

## 1. El candado — la petición original, sin hacer

> "Es tan simple como: haces la prueba, desbloqueas el siguiente."

Se aplazó **a propósito**, y el motivo importa: cuando se planteó, la familia de
actividades que cierra la mayoría de los nodos **no tenía ninguna salida**. Candar sin
salida es el mismo callejón que se acababa de arreglar, con otra puerta.

Esa salida ya existe (2026-08-29). Así que el candado ya se puede poner. Lo que falta es
probarlo con un curso delante antes de decidirlo.

**Cuando se haga, dos cosas que el análisis dejó dichas:**

- **Candar en el escritor, no en el lector.** La comprobación va en `POST /nodes/{id}/complete`,
  donde se sella `completed_at`, no dentro de `node_is_done`. Dos razones: ese predicado está
  escrito dos veces (Python y SQL) y ya costó un fallo; y a quien va por el nodo 4 con los tres
  primeros sellados no se le cierra nada retroactivamente.
- **`available` ya está en el contrato** (`NodeSummaryRead`) y hoy es siempre `true`. No hay que
  añadir campo: hay que empezar a moverlo.

## 2. Las pistas — la segunda afordancia

Hoy la única salida es automática: cuatro fallos y se entrega la solución. Falta lo que se
pidió expresamente — **un botón de pista y otro de ver la solución** — para las actividades
Didact, que son el cierre por defecto.

Es la mitad cara: hay que autorar las pistas en la misma llamada que crea la actividad
(dos claves más en el contrato, cero llamadas extra) y montar dos endpoints. El diseño
completo, con de dónde sale cada pista por modo de evaluación, está en el análisis.

**Ojo al hacerlo:** `HintLadder` se reutiliza casi entero; lo único atado al `QuizItem` es
la URL. `WorkedSolution` **no** se generaliza — se le añade una rama previa.

## 3. Un contador por actividad en `/activities/{id}/evaluate`

**Desviación conocida, marcada en el código.** Esa ruta cuenta fallos del nodo entero
(`consecutive_failed`) en vez de de la actividad, así que en un nodo con dos actividades,
fallar en una acerca a la otra a su solución.

No se pudo arreglar entonces: esas actividades no tienen `binding_id`, así que no hay fila
de intento que contar, y la única fila con el id de actividad solo se escribe si el cliente
manda `attempt_id` — cosa que la SPA no hace. Contarla daría cero y cerraría la salida para
todos.

**Las dos salidas, y son decisión:** una columna con el contador, o hacer que ese evento se
escriba siempre. La segunda arrastra un arreglo de una línea en el cliente
(`api/activity-ports.ts` ya tiene el `attempt_id` acuñado y no lo envía), y de paso reviviría
el replay y el dígest, que hoy están muertos.

## 4. Una puerta trasera en `POST /enrollments/{id}/complete`

Esa ruta es de v1 y **no comprueba si el curso es dinámico**. En uno dinámico al 100 %
escribe la nota vieja y acredita las habilidades **a nivel medio sin medir nada**, deshaciendo
en una llamada lo que hace `apply_dynamic_closure`.

No es explotable desde la interfaz —el botón de finalizar solo aparece en cursos con
lecciones— pero por API está abierta. El arreglo es un `resolve_delivery` de tres líneas; lo
que hay que decidir es si tocar una ruta de v1, que es lo que el proyecto lleva evitando a
propósito.

## 5. El promedio de las estadísticas de admin

`AVG(enrollments.score)` mezcla dos magnitudes sobre la misma escala: fracción de lecciones
(v1) y, en las filas escritas antes del 2026-08-29, media de maestría (v2). La mezcla deja de
crecer; la historia se queda, y no hay forma de separarla a posteriori.

Tres candidatos, ninguno obvio: quitar la tarjeta, limitarla a cursos estáticos, o cambiarla
por tasa de finalización — que es lo único que un curso dinámico afirma ya.

## Lo primero que haría quien retome esto

**Abrir un curso y recorrerlo entero como aprendiz.** Todo lo del 28 y el 29 cambia lo que se
ve en pantalla, y se decidió leyendo código y midiendo contra la API. Nadie lo ha mirado aún
con los ojos de quien lo usa, y las decisiones 1 y 2 son precisamente las que se contestan
mejor mirando que razonando.

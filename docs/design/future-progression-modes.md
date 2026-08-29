# Modos de progresión — el presente es lineal, el dominio es futuro

> **Estado: decisión tomada el 2026-08-28**, a partir de una reunión con testers. La parte
> lineal es alcance actual. El modo por dominio y el agente observador son dirección
> acordada, no alcance: aquí se documentan para que la arquitectura de hoy no los cierre.
>
> Sustituye a la sección "Current behavior" de `future-prerequisites.md`: los prerequisitos
> dejan de bloquear, así que la pregunta que aquel documento planteaba —qué ofrecerle a
> quien llega a un nodo bloqueado— ya no se plantea.

## 1. Los dos ejes que el sistema nunca separó

Sobre un nodo hay dos hechos distintos, y son ortogonales:

| eje | pregunta | dónde vive |
|---|---|---|
| **Evidencia** | ¿lo ha demostrado? | `state`, `mastery` (EWMA), `mastered_at` |
| **Recorrido** | ¿ha pasado por aquí? | `first_seen_at` (abierto), `completed_at` (terminado) |

El diseño original (§7) solo tenía el primero. `state` era *la* noción de progreso y todo se
resolvía contra `MASTERED`. La migración 0029 encontró el agujero —un nodo expositivo no
tiene ítem calificado, así que nunca puede llegar a `mastered`, contaba como cero progreso
para siempre y bloqueaba el cierre del curso— y añadió `completed_at`.

**Pero lo añadió como columna, no como concepto.** Nadie le puso nombre a la unión de los dos
ejes, así que cada consumidor se la deletreó por su cuenta y dos se equivocaron:

| consumidor | predicado de "hecho" | |
|---|---|---|
| `mastery_service.node_is_done` | `mastered ∨ completed_at` | correcto — es la fuente |
| `evaluate_course_completion` | usa `node_is_done` | correcto |
| `course_schema_service.recompute_enrollment_closure` | pasa `completed_at` | correcto |
| el candado de `routes/nodes.py` | `state != MASTERED` | **derivó** |
| `activity_progress._status` / `._percent` | `state is MASTERED` | **derivó** |

Los dos que derivaron son exactamente los dos únicos que escribieron el predicado a mano
**fuera del módulo que lo posee**. No es casualidad: el candado vivía dentro de un endpoint
HTTP, así que era irreusable, así que se copió, así que se copió mal.

La consecuencia era un callejón sin salida permanente: se lee un nodo expositivo entero, se
graba `completed_at`, el progreso sube, y el nodo siguiente se queda con el candado puesto
para siempre porque su prerequisito nunca será `mastered`.

### Reproducido contra la API, no deducido

Curso de tres nodos encadenados por prerequisitos, ninguno con ítem calificado, y un
aprendiz matriculado. Salida real de `GET /courses/{id}/nodes`:

```
ANTES     1. Que es una devolucion       state=not_started  locked=False
          2. Como se registra            state=not_started  locked=True
          3. Resumen del procedimiento   state=not_started  locked=True
          progreso: 0 %

POST /nodes/{n1}/complete  ->  200 {"completed_at": "...", "state": "not_started",
                                    "progress_percent": 33, "can_complete": false}

DESPUES   1. Que es una devolucion       state=not_started  locked=False  completed_at=si
          2. Como se registra            state=not_started  locked=True
          3. Resumen del procedimiento   state=not_started  locked=True
          progreso: 33 % | can_complete: False
```

El aprendiz termina el primer nodo entero, el servidor lo registra, el progreso sube — y el
segundo sigue cerrado. El curso se queda en 33 % para siempre, y no hay ninguna acción que
lo desbloquee: el nodo 1 no tiene nada que responder, así que su `state` no se moverá de
`not_started` nunca.

### Una cifra que el commit `422c1cc` da por buena y no lo es

Ese mensaje de commit justifica la urgencia con "7 de 20 nodos acaban sin ninguna
evaluación, y otros 4 con interacción sin evidencia calificada". **La medición era sobre una
imagen obsoleta.** El contenedor llevaba días corriendo código anterior a `8e0f420`, que es
el commit que arregló el anclaje de refs de `LearningExperience`; sobre código al día la
misma pasada da **20 de 20 con evaluación y cero fallbacks**.

Se anota aquí porque el número sigue escrito en la historia y alguien lo leerá.

Y no cambia nada de lo que sigue, que es el punto: la frecuencia era un argumento de
*urgencia*, nunca de diseño. Un nodo expositivo escrito a propósito —un resumen, un ejemplo
resuelto— existe con tasa de avería cero, y un predicado que vive en un solo sitio es
correcto a cualquier tasa, incluida esa. La reproducción de arriba se hizo contra el árbol
de trabajo, no contra la imagen, así que se sostiene entera.

## 2. Por qué hoy esto no es un curso por dominio

El beneficio de una formación por maestría es que la formación se mueve: te salta lo que ya
sabes, te insiste donde flojeas, cada persona hace un recorrido distinto. El coste son los
candados, el sondeo antes de enseñar y un porcentaje que se lee como nota.

Hoy se paga el coste entero y no se compra nada:

- **El sondeo no existe en la práctica.** Los endpoints `POST /nodes/{id}/probe` y
  `/probe/answer` funcionan y `ProbeService` está probado, pero **el frontend no los llama
  desde ningún sitio**. La única adaptatividad real del sistema —saltarte un nodo que ya
  dominas— está desconectada.
- **El grafo de prerequisitos es una cadena.** La regla 4 del prompt de esquema obliga a que
  un prerequisito aparezca *antes* en la lista, así que el DAG nunca contradice el orden
  lineal. No aporta información que el orden no dé ya.
- **El listón no es alto, es inalcanzable en medio catálogo.** `FADING_STREAK = 3` exige tres
  aciertos seguidos en ítems calificados, con umbral `0.90` en un nodo crítico y una EWMA de
  `ALPHA = 0.4` que sube despacio a propósito. Un nodo expositivo no tiene ningún ítem que
  responder, así que su techo no es alto: no existe.

Es decir: la maestría **es un freno, no un volante**. Toda la rigidez, ninguna de las ramas.

## 3. La decisión

**Todos los cursos son lineales.** Hay un orden, se pasa por todo, queda constancia.

La maestría se sigue midiendo, guardando y mostrando —es lo que hace que un certificado
signifique algo, y es la entrada que el agente observador va a necesitar— pero **deja de
gobernar la navegación**.

No se añade un `progression_mode` todavía. Un dial con un solo valor es especulación; lo que
hay que preservar no es la columna, es la costura.

### Enmienda del 2026-08-29: el dial ya tiene dos valores

Lo de arriba se sostiene entero salvo por su último párrafo, y por el motivo que ese mismo
párrafo daba: **el dial dejó de tener un solo valor.** `courses.navigation_mode` (migración
0034, y no `progression_mode`: el nombre dice lo que gobierna) toma dos:

| valor | qué hace | quién lo tiene |
|---|---|---|
| `free` | todo abierto, se navega a gusto | **el defecto** — o sea, todos los cursos que ya existían |
| `sequential` | una lección se abre cuando la anterior está *hecha* | quien lo elija al crear el curso o después |

Lo elige quien crea el curso y se edita con `PUT /courses/{id}`, como `tutor_style`. La
migración es aditiva y con `server_default`: no reescribe ninguna fila y ningún curso
cambia de comportamiento.

**Y no reintroduce el callejón de §1**, que es la única pregunta que importa aquí. Aquel
candado comparaba contra `mastered`, inalcanzable en un nodo sin ítem calificado; este
compara contra `done` —`mastered` **o** `completed_at`—, y terminar un nodo siempre está al
alcance. Una regla escrita sobre `done` no puede fabricar una puerta que nadie pueda abrir.

Dos detalles del diseño que no son cosméticos:

- **Un nodo ya hecho sigue abierto**, aunque el anterior no lo esté. Sin esto, cambiar a
  `sequential` un curso a medias cerraría lecciones por detrás de quien ya pasó por ellas.
- **El admin va suelto siempre** (`resolve_navigation`), por rol y no por matrícula, igual
  que en `services/course_access.py`: una previsualización no se puede parar en la lección
  dos.

La regla vive en un solo sitio, `services/node_progression`, y el candado de verdad está en
`POST /nodes/{id}/complete` — que le pide a ese módulo la misma foto que pinta
`GET /courses/{id}/nodes`, así que la lista y la negativa no pueden discrepar.

Lo que **no** cambia: `available` sigue siendo una respuesta y no una prohibición (§4), el
productor de `CourseProgression` sigue siendo el punto de extensión, y la maestría sigue sin
gobernar nada. El modo por dominio de §5 sigue fuera de alcance y sigue yendo bifurcado.

## 4. La arquitectura de hoy

### `services/node_progression.py`

Un módulo que responde una sola pregunta: *dónde está esta persona en este curso*.

```python
@dataclass(frozen=True, slots=True)
class NodeProgression:
    node_id: UUID
    position: int
    state: str        # la máquina de evidencia, intacta
    mastery: float
    done: bool        # el predicado, que ahora existe UNA vez
    available: bool   # en `free`, siempre True; en `sequential`, la regla de la enmienda de §3

@dataclass(frozen=True, slots=True)
class CourseProgression:
    nodes: tuple[NodeProgression, ...]
    next_node_id: UUID | None   # el primero no hecho, en orden
    progress_percent: int
    can_complete: bool
```

Por dentro llama a `mastery_service.node_is_done` y `evaluate_course_completion`. **No los
mueve**: `mastery_service` sigue siendo la regla pura cuyo número acaba en un certificado, y
moverla arrastraría a `enrollment_service`, `course_schema_service` y las rutas sin ganar
nada.

Lo que cambia es que `node_progression` es **la única puerta**. Las rutas y
`activity_progress` hablan solo con él, y nadie vuelve a derivar "hecho" por su cuenta — que
es exactamente cómo se rompió esto.

### El contrato deja de mandar una lista y pasa a responder

En `GET /courses/{id}/nodes`: fuera `locked` y `locked_by`, dentro `next_node_id`.

Y el vocabulario importa. `locked` es una prohibición; `available` es una respuesta. En
lineal todo está disponible. En dominio el conjunto lo elegirá el observador. Mismo campo,
dos significados legítimos.

### El cliente deja de decidir

Hoy `CourseView.tsx` y `NodeView.tsx` calculan en TypeScript cuál es el siguiente nodo y si
se puede ir; `CourseIndex.tsx` y `NodeList.tsx` pintan el candado. Todo eso pasa a leer lo
que dice el servidor.

**Este es el cambio que hoy no se nota y que decide si el futuro es posible**, porque un
agente observador no puede vivir en el navegador. Mientras el cliente calcule la navegación,
el modo adaptativo exige rehacer el frontend.

### Por qué una función y no una clase abstracta

Fue una decisión discutida, no un descuido:

- Hoy, para lo que el modo dominio hace, la diferencia es **una pregunta**, no una familia de
  comportamientos. `progress()` sería idéntico en los dos modos y `next()`/`available()` son
  la misma decisión vista por dos lados. Una interfaz con un método útil y sin estado es una
  función con ceremonia. (Esto deja de valer en cuanto llegue lo de §5.1, y entonces la
  bifurcación no es una interfaz: es otro camino.)
- **El repo ya contestó a esto.** `course_delivery.resolve_delivery` decide entre v1 y v2
  —dos pipelines de verdad— y es una función que devuelve un string. Meter polimorfismo para
  algo más pequeño introduce un estilo que el resto del código no usa.
- **No sabemos aún qué necesita la segunda implementación.** La lineal es pura: nodos,
  estados, aritmética. La adaptativa llamará a un observador, será asíncrona y tendrá
  dependencias. Fijar hoy la firma de un método para un colaborador sin diseñar produce una
  abstracción equivocada, que es más cara de cambiar que ninguna.

**El contrato estable no es la clase: es `CourseProgression`.** Quien llama solo ve ese dato
y le da igual quién lo produjo. Convertir la función en interfaz el día que haga falta es un
refactor sin tocar un solo sitio de llamada.

> Aquí es donde esto se bifurca cuando llegue el modo por dominio. El punto de extensión es
> el productor de `CourseProgression`, y el contrato que hay que respetar es el tipo, no la
> forma de producirlo.

## 5. El futuro: el modo por dominio

**Va bifurcado, y no se construye ahora.** Hoy todo es lineal; el trabajo de hoy solo tiene
que dejar la costura preparada y no cerrar la puerta.

### 5.1 Por qué bifurcado, y no un modo del mismo camino

El criterio, que vale más que la opinión de quien lo escribe:

> Bifurcar sale a cuenta cuando cambia **de qué está hecho** el curso. No cuando cambia **qué
> hace el sistema con lo que ya hay.**

Aplicado a lo que el repo ya hizo: un curso v1 son módulos y lecciones, markdown escrito una
vez e igual para todos; uno v2 son nodos y renders generados por persona. No comparten ni las
tablas. Ahí nadie decidió bifurcar — ya eran dos cosas distintas y el código lo reconoció. Y
el impuesto se ve: `tests/integration/test_v1_regression.py` existe porque hay que trabajar
activamente para que el camino menos transitado siga vivo.

Con ese criterio, "lineal contra dominio" **no** justificaba separar: mismos nodos, mismos
renders, mismas filas de evidencia, mismo tutor, mismo certificado, y una sola regla distinta.

Lo que sí lo justifica es lo que el modo dominio va a traer con él: **el observador crea
pantallas nuevas sobre la marcha cuando alguien se atasca.** Eso ya no es una regla aplicada
sobre el mismo material — es material que no existía. Cambia de qué está hecho el curso, y
por tanto pide camino propio con el mismo derecho con que lo pidió v2.

### 5.2 Con qué choca, y la línea que lo resuelve

Con la promesa central de v2, que sostiene `course_schema_service` y está escrita en su
cabecera: *ningún aprendiz recibe nunca contenido generado para un nodo que un humano no ha
firmado*. Una pantalla improvisada porque alguien va mal es, por definición, contenido que
nadie firmó.

La salida no es romper la promesa, es reconocer **dos tipos de material**:

| | qué es | quién lo aprueba | cuenta para el certificado |
|---|---|---|---|
| **Curriculum** | lo que alguien decidió que hay que aprender | humano, en el gate de §11.1 | sí |
| **Andamio** | lo que el sistema improvisa para sacarte del atasco: otro ejemplo, la misma idea contada de otra forma, práctica extra | nadie, se genera al vuelo | no |

El andamio **no necesita firma precisamente porque no certifica nada**. Es la misma línea de
§6 entre certificar y entender, aplicada al contenido: el observador puede permitirse
improvisar y equivocarse porque lo que produce no acaba en el certificado. Mezclarlas cuesta
las dos cosas — o le pides al andamio una fiabilidad que le quita la gracia, o le das al
certificado contenido que nadie miró.

### 5.3 El argumento contrario, anotado

Se deja escrito porque el día que se construya conviene tenerlo delante:

> Dominio podría no ser una alternativa a lineal, sino lineal **más** exigencias de
> evidencia — el camino lineal *dentro* del de dominio, ejercitado siempre y por tanto
> incapaz de pudrirse, como se pudrió `feat/dynamic-courses`.

El riesgo de pudrición es real. Lo que lo tumbó es §5.1: esa forma solo aguanta mientras el
modo dominio no traiga material propio, y va a traerlo.

### 5.4 Lo que no cambia entre los dos

**La generación del curso no cambia**, aunque los caminos se separen: el esquema se propone y
se valida igual, y quien crea el curso elige el modo como ya elige `delivery_mode` y
`tutor_style`. Lo que diverge es lo que pasa **después**, en tiempo de ejecución.

El patrón para elegirlo ya existe en el repo:
un curso es dinámico cuando tiene `delivery_mode='dynamic'` **y** `schema_status='validated'`;
los demás caen a v1. Es decir: **se declara un modo, una puerta decide si se honra, y hay un
plan B.**

`progression_mode` es exactamente eso. Se elige al crear, junto a `delivery_mode` y
`tutor_style`. Y la puerta ya existe también — la validación del esquema, con sus reglas
nombradas (`no_critical_node`, `orphan_prerequisite`, los ciclos). Se le añade una: si el modo
es dominio, cada nodo tiene que traer evidencia medible. Si no la trae, sale un aviso con el
mismo formato que los demás, en vez de producir en silencio un curso que nunca se puede
terminar — que es literalmente lo que pasa hoy.

Queda por decidir si un esquema que no pasa la puerta cae a lineal en silencio (como hace
`delivery_mode` con v1) o se le avisa a quien crea el curso. La inclinación es avisar: el caso
de v1 es un repliegue técnico, pero aquí alguien eligió una metodología a propósito.

## 6. El agente observador

La raíz de que la maestría de hoy se sienta a la vez rígida y tonta es que **hay dos preguntas
distintas y el sistema las contesta con el mismo número**:

| | qué pregunta | quién debe contestarla |
|---|---|---|
| **Certificación** | ¿puedo afirmar ante un tercero que esta persona sabe esto? | oráculo determinista, puro, no manipulable |
| **Pedagogía** | ¿esta persona lo está pillando ahora mismo? | agente observador, con juicio, incierto |

Separadas, cada una se puede hacer bien. El observador **no necesita ser infalsificable**,
porque no firma el certificado: puede leer la conversación con el tutor, las preguntas que se
hacen, dónde se atasca alguien, y decidir si saltar contenido, si el tutor interviene, si se
ofrece otra práctica. El oráculo **no necesita ser listo**, solo honesto y auditable.

La frontera por la que enchufa **ya existe**. La cabecera de `mastery_evidence_service.py` lo
dice: *"From this boundary onwards the component that produced the evidence is irrelevant"*. Y
el sustrato de entrada también: `learning_events` ya registra fallos, pistas, `scroll_fast` y
tipo de error.

Lo único que hay que ensanchar cuando toque: hoy la evidencia entra con forma de quiz
(`score`, `passed`, `error_kind`, `hints_used`). El juicio de un observador es de otra
naturaleza —continuo, incierto, sobre el nodo entero— así que la evidencia tendrá que llevar
**tipo y confianza**.

## 7. Lo que no hay que construir *hoy*

Ninguno de estos está cerrado para siempre. Están fuera del alcance actual, y el que tenga
un motivo para meterlo debería poder rebatir la línea que lo acompaña.

- **Un enum `traversal` paralelo a `state`.** Los dos hechos ya están guardados; lo que
  faltaba era un nombre para su unión, no una columna más.
- ~~**Un `progression_mode` con un solo valor.**~~ Sigue valiendo el argumento y sigue sin
  construirse ese: lo que existe desde el 2026-08-29 es `navigation_mode`, con dos valores
  y una regla escrita sobre `done`. Ver la enmienda de §3.
- **Una interfaz antes de conocer la forma de la segunda implementación.** Ver §4.
- **Reglas de validación distintas para el DAG.** Los prerequisitos dejan de cerrar puertas,
  pero siguen ordenando el esquema y alimentando la señal `revisar_prerrequisito` del tutor.
  Se quedan como están.

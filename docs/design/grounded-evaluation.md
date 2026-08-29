# Lo que se enseña y lo que se pregunta — un solo contrato

De la reunión con testers del 2026-08-28 salieron dos quejas, y eran la misma:

> *"En muchos cursos las preguntas no están acorde a lo que se ha explicado antes. Se me dice
> que debo buscar por correo y luego la respuesta es por nombre. Y a veces ni siquiera se
> explica el contenido que se pregunta."*

La primera mitad —la pregunta contradice la pantalla— tenía seis causas concretas, y están
corregidas (`07d7ca9`). La segunda —**se pregunta algo que no se explicó**— sigue abierta, y
es la que motiva este documento, porque no se arregla con otra regla.

## 1. El caso que lo demuestra

`prevencion-riesgos`, del corpus del banco. Falla tres de tres, siempre igual.

- La fuente dice: *"El peso máximo recomendado es de **25 kg**"*.
- El resumen del nodo dice: *"por encima de **25 kg** no se levanta a mano"*.
- La pantalla generada enseña: una frase de entrada y los cinco pasos de la técnica.
- **El límite de 25 kg no aparece por ningún sitio.**
- Y la pregunta es: *"¿Una caja de 30 kg se puede levantar a mano si se usa la técnica
  correcta?"*

La respuesta depende por completo de un dato que la pantalla tiró. Peor: la pantalla enseña
la técnica *sobre una caja de 30 kg*, así que sugiere que sí. Y la respuesta es que no.

La cadena, paso a paso:

1. `density: 2` → el prompt ordena **"3 bloques como máximo y frases cortas"**
2. La forma detectada es `procedure` → un `StepSequence` se lleva un bloque entero
3. Quedan tres: intro, procedimiento, pregunta. **Cupo agotado.**
4. El límite no cabe
5. La evaluación lo pregunta igualmente

El modelo no desobedece. **Le pedimos tres bloques y cuatro cosas.**

## 2. El patrón, que es lo que de verdad hay que arreglar

Todos los fallos de esa noche tienen la misma forma:

> Se le piden al modelo **varias restricciones a la vez, en prosa**, sin ningún mecanismo que
> resuelva los conflictos entre ellas ni que verifique después si se cumplieron.

| Restricción | Contra | Quién gana |
|---|---|---|
| "3 bloques como máximo" | "un nodo crítico lleva un aviso con el límite" | el presupuesto |
| "solo evalúa lo que enseñaste" | una fuente que trae más de lo que cabe | nadie: no hay árbitro |
| lo que explica una llamada | lo que pregunta otra | ninguna: no se hablan |

Y la puerta comprueba **forma** —gramática, número de bloques, forma de la clave— pero nunca
**la relación** entre lo explicado y lo preguntado.

De ahí el criterio que ordena todo lo demás:

> Las restricciones en prosa que se contradicen las resuelve el modelo al azar. Solo la
> estructura las resuelve igual siempre.

Poner un suelo al presupuesto habría sido la cuarta regla de prosa. Mañana chocaría con la
quinta.

## 3. Lo que ya existe y se está tirando

El `NodeKnowledgePack` ya distingue lo que hace falta:

- `must_preserve` — invariantes
- `selectable` — material adaptable
- `evidence_specs` con **`atom_refs`** — literalmente *"esta comprobación depende de estos
  hechos"*

Y el selector ya honra esa dependencia (`knowledge_pack/selector.py`):

```python
for evidence_id in required:
    selected_ids.update(evidence_by_id[evidence_id].atom_refs)
```

Los hechos de los que depende la evaluación **están garantizados en la selección**. La
relación existe, es del servidor, y es determinista.

Pero mira cómo se renderiza el dossier (`knowledge_pack/runtime_selection.py`):

```python
for evidence_id in result.evidence_ids:
    lines.append(_point(evidence[evidence_id].description, evidence_id))
```

Se escribe **sólo la descripción de la evidencia**. Los `atom_refs` se calculan y **se
descartan al construir el prompt**. El modelo recibe "esto hay que comprobarlo" por un lado y
una lista plana de hechos por otro, sin saber cuáles sostienen la pregunta.

**No hay que inventar el mecanismo. Hay que dejar de tirarlo.**

## 4. La criticidad no pinta nada aquí, y hay que dejarlo escrito

La regla que hoy intenta salvar el límite de 25 kg es ésta, en `llm/prompts/runtime.py`:

```python
_CRITICALITY_RULES["critical"] = (
    "es de cumplimiento obligatorio. Incluye un Callout('warn', ...) si la fuente "
    "marca un limite o prohibicion."
)
```

Intenta proteger un hecho **adivinándolo desde una etiqueta** que un modelo asignó al diseñar
el esquema. Es el mecanismo débil haciendo el trabajo del fuerte, y encima es el que choca
con el presupuesto.

Durante el análisis defendí conservar la criticidad tres veces. **Las tres eran falsas**, y
quedan aquí para que nadie las reproponga:

**"Es la costura por la que enchufará el modo por dominio."** Falso.
`future-progression-modes.md` decide que `progression_mode` se elige **al crear el curso**,
junto a `delivery_mode`, y que la comprobación por nodo es *"¿trae este nodo con qué medir?"*.
La criticidad no aparece ni una vez en ese diseño.

**"Es el listón de la certificación."** Falso.
`evaluate_course_completion` lo dice en su propio docstring: *"Criticality does not gate
closure"*, y `score` es **la media del valor de `mastery`**, no de la etiqueta. El umbral no
entra en el cálculo. El docstring además documenta que condicionar el cierre con la
criticidad se consideró y se rechazó.

**"Al menos fija la dificultad de la pregunta."** Falso en la práctica.

```python
def shu_ha_ri(mastery, threshold):
    if mastery < 0.5:        return "shu"   # el umbral NI SIQUIERA ENTRA
    if mastery < threshold:  return "ha"
    return "ri"
```

Por debajo de 0,5 el umbral no participa. Y la maestría casi nunca se mueve: exige una racha
de tres aciertos calificados, en nodos que muchas veces no traen ni una pregunta.

### El balance

| Consumidor | Efecto real hoy |
|---|---|
| `probe_item_count`, `requires_tiebreak` | Ninguno: ningún cliente llama al sondeo |
| `threshold_for` → `target_bloom` | Ninguno en el primer render, el único que casi todos ven |
| `threshold_for` → cierre y nota | Ninguno: rechazado a propósito |
| `_CRITICALITY_RULES` | **El único efecto vivo, y es el daño** |

En un curso lineal la criticidad no tiene **ni un solo efecto observable**, salvo la regla que
rompe el presupuesto.

**Decisión: se borra `_CRITICALITY_RULES`. La columna y `threshold_for` se quedan quietos.**
No se borran porque cuando aterricen el oráculo y el agente observador un listón por nodo
volverá a significar algo — pero **hoy no se diseña nada alrededor de ellos**, porque hoy no
hacen nada. Una etiqueta inerte y honesta es mejor que una inerte y dañina.

## 5. La arquitectura

Un principio:

> Un hecho del que depende la evaluación **no es contenido: es parte de la evaluación**. Tiene
> que llegar a la pantalla, y el servidor tiene que poder comprobar que llegó.

Tres movimientos y una supresión.

### 5.1 La dependencia viaja al prompt

`_render_context` escribe los `atom_refs` de cada evidencia junto a ella, marcados por lo que
son: *sin estos hechos la comprobación no se puede responder*. Deja de ser una regla de prosa
sobre nodos importantes y pasa a ser **una propiedad del material de este nodo**.

Vocabulario cerrado, como `_SIGNAL_RULES`: una referencia interna no puede convertirse en
prosa libre inyectada en un prompt, y el gate de andamiaje (`spec_scaffolding_markers`) sigue
vigilando que no acabe en pantalla.

### 5.2 El presupuesto resta, no compite

Hoy `_DENSITY_BUDGET` dice *"3 bloques como máximo"* y el modelo decide qué sacrificar. Pasa a
decir: **estos hechos ocupan lo que ocupen, y te quedan N bloques para desarrollar**. Lo
obligatorio se reserva primero; el recorte cae sobre lo elaborable.

La densidad sigue existiendo y sigue significando lo mismo —cuánto se desarrolla— pero deja
de poder comprar espacio vendiendo un hecho que la evaluación necesita.

### 5.3 La puerta lo comprueba

Hoy `validate_ui` no puede juzgar anclaje porque no sabe de qué depende la pregunta. Con 5.1
sí lo sabe: es un dato del servidor, no una inferencia.

La comprobación entra por el **bucle de reparación que ya existe** —lista de
`validation_errors` más `retry_count + 1`, nunca una excepción— igual que
`answer_key_problems`. Y el mensaje sigue el estándar del módulo: decir qué falta y qué
escribir en su lugar, para no quemar el único reintento con una queja vaga.

Es exactamente `selection_eval.GateCode.EVALUATION_UNGROUNDED`, que **ya está escrito y
probado** en el repo y sólo se usa desde bancos que no corren en producción. No hay que
inventarlo: hay que conectarlo.

### 5.4 Se borra la regla de criticidad

Ver §4. El conflicto no se arbitra: desaparece.

## 6. Por qué esta forma y no otra

Es la misma que ya eligió `future-progression-modes.md` para la progresión:

> *"se declara un modo, una puerta decide si se honra, y hay un plan B"*

Aquí, un nivel más abajo: **la evidencia declara de qué hechos depende, una puerta comprueba
que la pantalla los entregó, y el plan B es el bucle de reparación seguido del seed.** Que dos
problemas independientes converjan en la misma forma es la señal de que la forma es del
dominio y no del problema.

## 7. Lo que no hay que construir

- **Un suelo al presupuesto como regla de prosa.** Sería la cuarta restricción compitiendo con
  las otras tres. El presupuesto no necesita un mínimo: necesita saber qué no es negociable.
- **Un evaluador de anclaje con LLM.** La dependencia es determinista y el servidor la conoce.
  Un juez incierto para una pregunta cierta es coste y varianza a cambio de nada.
- **Un `progression_mode` o un flag nuevo.** Esto no es un modo: es cómo debe funcionar
  siempre.
- **Tocar la fontanería de las actividades.** El `fallback_seed` por refs sin anclar, la
  `LearningExperience` fantasma que se descarta al persistir y el `ConflictError` al
  rematerializar son reales y probablemente más graves, pero son otro frente. Mezclarlos es
  cómo se hace un parche grande en vez de dos arreglos limpios.

## 8. Qué medir

El banco ya sabe decir por qué camino va y con qué flags (`8dc5976`), así que una medición
vuelve a significar algo. Falta que pueda ejercitar el camino de episodios: hoy `--arm pack`
construye el dossier para el contexto pero no rellena `knowledge_pack_payload`, así que
`direct_episode` declina con `missing_knowledge_pack` en todos los brazos.

La medida que importa no es "acierto a la primera" —eso mide si el programa valida— sino
**cuántas pantallas preguntan algo que no enseñaron**. Leídas a mano el 2026-08-28 sobre el
camino legacy: 7 de 10 ancladas antes de los arreglos, 8 de 10 después. Con n=10 eso es un
caso de diferencia y **no es una señal**; queda escrito para que nadie lo cite como mejora.

`prevencion-riesgos` es el caso de regresión: entrada determinista, fuente conocida, respuesta
conocida, fallo reproducible tres de tres. Vale más que un porcentaje.

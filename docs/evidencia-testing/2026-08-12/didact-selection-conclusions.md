# Conclusiones adversariales sobre selección Didact

Fecha: 2026-08-12  
Ámbito: revisión de `didact-selection-experiment`, `didact-shortlist-r2` y
`experience-intent-r1`.

## Veredicto

Los tres experimentos apoyan continuar con un catálogo completo detrás de una shortlist
pequeña y con una intención educativa independiente de los nombres de componentes. **No
demuestran aún qué selector debe entrar en el runtime ni que los cursos generados sean
mejores.** `facets top 5` es una baseline para el próximo experimento, no una decisión de
producto.

## Confusores que cambian la lectura

### Inventario no equivale a disponibilidad

Los rankings usan los 34 descriptores instalados y consideran que los puertos declarados
en el fixture están disponibles. El host actual solo marca cinco tipos como emitibles:
Flashcard, Glossary, HintReveal, Timeline y WorkedExample. Además, un tipo sin puertos
puede pasar los filtros aunque todavía no tenga renderer habilitado.

Comparado con el estado real del host, fueron no emitibles:

| Informe / brazo | Selecciones no emitibles |
|---|---:|
| Didact R1, facetas k=3 | 18/29 (62,1%) |
| Didact R1, facetas k=5 y MMR k=5 | 25/46 (54,3%) |
| R2, facetas top 5 | 34/54 (63,0%) |
| R2, híbridos top 5 | 36/54 (66,7%) |
| ExperienceIntent, tipado | 16/24 (66,7%) |

Esto no invalida un bench de catálogo futuro, pero sí impide trasladar sus porcentajes a
OpenUI actual. La exposición real debe aplicar después del ranking un gate independiente:
`renderer_available && llm_emittable && required_ports_satisfied`.

### “Evidencia” significa tres cosas diferentes

- Didact R1 revela correctamente que los 34 `ComponentDescriptor` exportan cero
  `evidence_events`; su cobertura explícita es 0%.
- R2 informa 100% porque mide si aparece alguno de los `evidence_components` escritos a
  mano en el fixture. No comprueba un evento observable, evaluado ni persistido.
- ExperienceIntent infiere evidencia desde capacidades de manifiesto `response:*` y
  `result:*`. Es mejor semánticamente, pero tampoco observa que el evento ocurra en el
  renderer o llegue al host.

Por tanto, ningún informe prueba todavía preservación de evidencia. Hay que enriquecer el
contrato con eventos explícitos y medirlos en ejecución.

### Golds y queries no son independientes

- Los casos, componentes relevantes/preferidos/prohibidos y pesos se diseñaron viendo el
  catálogo. Varias queries contienen casi literalmente nombres o etiquetas del tipo
  esperado (`branching scenario`, `simulation lab`, `self explanation`, `worked example`).
  Esto favorece BM25 y MMR.
- Affordances, relevancia y preferencias se puntúan con los mismos metadatos empleados
  para ordenar. Es una comprobación de coherencia del contrato, no validez externa.
- En ExperienceIntent, la intención tipada actúa a la vez como entrada y como gold de
  cobertura. Es un **oracle ceiling test**. El brazo directo usa coincidencia exacta y es
  deliberadamente débil; la mejora 59,3% → 84,7% no estima la ganancia frente a un parser,
  embedding o LLM competente.
- Las variantes de una misma familia comparten manifiesto y descriptores casi idénticos.
  El bench no distingue honestamente, por ejemplo, qué formato concreto de quiz conviene.

### Métricas que pueden parecer mejores de lo que son

- La cobertura es la unión de toda la shortlist: top 5 puede alcanzar 100% aunque OpenUI
  elija solo un candidato inadecuado o componga una pantalla incoherente.
- “Tipos únicos” globales e índice Jaccard de texto no equivalen a variedad pedagógica
  útil. Pueden premiar vocabulario diferente sin cambiar la acción del alumno.
- Los prohibidos son pocos golds curados; cero prohibidos no es una prueba de seguridad.
- El rechazo de ExperienceIntent usa un único requisito artificial ausente para todos los
  tipos. Su 100% demuestra el filtro básico, no calibración de declines ni alternativas.
- La latencia medida es solo ranking en memoria. No incluye construcción de prompt,
  generación, reparación, descarga lazy, montaje o interacción.
- Los informes usan fixtures, `k`, métricas y pesos distintos. No se pueden usar sus
  porcentajes para afirmar que k=3 o k=5 ganó globalmente.

Tampoco se midieron hechos críticos, grounding, validez OpenUI, montaje del renderer,
accesibilidad interactiva, calidad del feedback, coherencia de una pantalla completa,
aprendizaje ni retención.

## Qué se puede decidir ya

1. Mantener los 34 tipos en el inventario y cargar código bajo demanda.
2. No entregar normalmente los 34 contratos al modelo; usar una shortlist acotada.
3. Separar selección pedagógica de exposición técnica. Un selector puede conocer un tipo
   futuro, pero OpenUI solo puede recibir tipos emitibles por el host actual.
4. Tratar requisitos, accesibilidad, hechos críticos y evidencia como gates no
   compensables, antes de optimizar diversidad.
5. Usar facetas top 5 como baseline sencilla de investigación. BM25 y MMR no han mostrado
   una mejora material que justifique su complejidad.
6. Conservar `ExperienceIntent` como hipótesis de arquitectura y explicación auditable,
   pendiente de demostrar cómo se infiere y cómo afecta a pantallas reales.

## Qué no se puede decidir aún

- Promover k=3, k=5, BM25, MMR o ExperienceIntent al runtime.
- Afirmar que hay más personalización o mejor aprendizaje en cursos reales.
- Exponer tipos bloqueados porque el fixture simule sus puertos.
- Usar “100% evidencia” de R2 como garantía del producto.
- Elegir embeddings frente a reglas o LLM pequeño.
- Considerar resuelto el coste temporal de generación o lazy loading.

## Siguiente experimento live

Generar pantallas reales con fuente fija y evaluación ciega:

- 12 objetivos no usados para ajustar los fixtures;
- dos perfiles por objetivo: una diferencia relevante y un control irrelevante;
- tres semillas por celda;
- dos brazos: catálogo emitible completo actual vs `ExperienceIntent + facetas top 3`;
- misma fuente, knowledge pack, modelo, parámetros y presupuesto en ambos brazos;
- 144 renders en total, conservando prompt, shortlist, spec, reparaciones, eventos, tokens
  y tiempos.

El productor de `ExperienceIntent` debe fijarse antes de abrir el conjunto ciego. Para esta
ronda puede ser una regla o un modelo pequeño, pero no un oracle escrito después de ver el
resultado. Los nombres de componentes no deben aparecer en el input de intención.

### Gates para aceptar un brazo

1. **Exposición:** 0 tipos no emitibles o con puertos ausentes llegan al prompt.
2. **Grounding:** 0 hechos críticos omitidos, contradichos o sin soporte.
3. **Ejecución:** 100% specs válidas, montables y alcanzables; 0 crashes o fallbacks
   silenciosos.
4. **Evidencia:** 100% de los eventos requeridos se observan en el host y, cuando procede,
   quedan evaluados/persistidos; la mera capacidad del manifiesto no cuenta.
5. **Accesibilidad:** 0 incumplimientos de teclado, lector de pantalla o alternativa al
   drag cuando sean requisitos del perfil.
6. **Personalización causal:** al menos 75% de pares relevantes cambia en una dimensión
   semántica prevista; al menos 80% de controles irrelevantes permanece estable.
7. **Calidad ciega:** el brazo candidato no pierde frente a baseline y gana por mayoría en
   adecuación de la acción, feedback informativo y coherencia de la pantalla.
8. **Operación:** registrar p50/p95, tokens, reparaciones y descargas lazy. Se comparan por
   separado; no pueden compensar un fallo de los gates anteriores.

Solo después de superar estos gates tendría sentido activar la política detrás de una
flag y ampliar la prueba a nuevas familias de renderers.

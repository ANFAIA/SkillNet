# Dossiers pedagógicos por nodo (`NodeKnowledgePack`)

## Decisión

SkillNet conserva el índice/grafo del curso y añade una preparación asíncrona por nodo:

```text
documentos → índice revisable → commit → pack estructurado + Markdown revisable
                                      ↓ selección por perfil y misión
                                      ↘ OpenUI on-the-fly
```

El pack no es una lección canónica ni una pantalla. Es una fuente intermedia de verdad
pedagógica: hechos obligatorios, reglas de seguridad, procedimiento, casos, errores comunes,
evidencia que debe obtenerse, huecos conocidos y espacios acotados donde sí se puede generar.
OpenUI sigue componiendo la experiencia para cada contexto; cuando existe un pack `ready`, adapta
material previamente revisado en vez de inventar a la vez el fondo y la forma. Si no existe o la
selección declara un hueco bloqueante, conserva automáticamente la fuente raw actual.

El Markdown es una proyección determinista para personas. Nunca se vuelve a parsear como autoridad:
la autoridad es el JSON versionado `node-knowledge-pack/1` almacenado completo junto con su hash.

## Estado de implementación

La vertical está integrada en el entorno de desarrollo:

1. `persist_schema` confirma el índice y cierra su transacción.
2. Después lanza `run_packs_for_schema`; un fallo no impide `schema_ready` ni cambia el curso.
3. El runner abre sesiones nuevas, limita la concurrencia a dos nodos y aplica un timeout de 120 s
   por nodo. No mantiene una conexión de base de datos durante llamadas al modelo.
4. Una primera llamada extrae el dossier y una segunda lo revisa/corrige. Ambas devuelven JSON,
   usan temperatura cero y tienen un máximo de 3.200 tokens de salida. Es preparación asíncrona:
   este presupuesto no se añade a la espera del alumno.
5. Referencias, hashes, identidad del nodo y procedencia los instala el programa, no el modelo.
6. Pydantic rechaza campos extra, referencias inexistentes, ciclos y packs incoherentes.
7. La escritura terminal está condicionada al fingerprint reclamado. Un worker antiguo puede acabar,
   pero no publicar sobre una fuente nueva.
8. `ready` y `review_required` son estados distintos también en PostgreSQL; un dossier rechazado no
   puede aparecer listo por un error de proyección.
9. Crear o modificar el esquema encola automáticamente la preparación. Abrir la pantalla no inicia
   trabajo. Cada nodo muestra dentro de su desplegable solo el
   estado accionable, los gaps que requieren revisión y, cuando existe, la base pedagógica legible;
   no hay un panel global ni un botón manual de generación.
10. El runtime selecciona invariantes y material opcional mediante vocabulario cerrado. La selección
    y el hash del pack entran en la clave de caché antes de modificar el prompt.

La tabla `node_knowledge_packs` conserva Markdown, payload canónico completo, vista compacta de
átomos, procedencia, hashes, tokens, duración y error. Los snapshots anteriores pasan a `stale` y
siguen disponibles para auditoría.

Solo un pack `ready` puede sustituir `source_context`. `review_required`, `failed`, ausencia de pack o
un `Declined` conservan el camino raw. Si un pack cambia entre la consulta de caché y el comienzo del
grafo, la generación se rechaza para que nunca se escriba contenido raw bajo una clave de pack ni al
revés.

## Por qué no basta un Markdown genérico

Un texto lineal fija demasiado pronto una explicación y favorece que todas las variantes converjan.
Un pack conserva posibilidades. Por ejemplo, la misma regla de alérgenos puede aportar una tabla para
lectura visual, un caso de decisión para práctica o una explicación detallada, manteniendo en todas
las variantes la misma regla crítica y su fuente.

La selección es determinista: incluye siempre invariantes y evidencia requerida; filtra los
casos opcionales por misión, presentación y accesibilidad; incluye prerequisitos; y devuelve
`Declined` si faltan datos imprescindibles. Nunca pedirá al modelo que rellene un hueco factual.

## Evidencia y coste conocidos

El control con 72 planes equivalentes produjo exactamente la misma planificación para raw y pack:
atomizar el mismo contenido no mejora ni aplana por sí solo el resultado. La ventaja potencial procede
del trabajo pedagógico previo —casos, evidencia, errores y límites—, no de llamar Markdown al formato.

El baseline live raw actual (nueve renders con `gpt-4o-mini`) fue p50 7,53 s, p95 10,75 s y 632 tokens
de entrada medios. La planificación local y el fingerprint cuestan microsegundos. La preparación del
pack sí añade dos llamadas por nodo, pero ocurre una vez al crear el curso y fuera de la espera del
alumno; sus tokens y duración quedan registrados para calcular el coste amortizado.

El benchmark admite `--arm raw|pack|both`. El brazo pack sustituye solo `source_context` después de
`load_context`, conserva sesiones frías separadas y reporta hashes, átomos, tamaño de contexto y firma
de UI por brazo. El modo offline ya verifica compatibilidad; una comparación causal live requiere el
mismo modelo, orden intercalado y 5–10 repeticiones por celda.

## Puertas aplicadas al runtime

La integración puede ejecutarse durante el desarrollo, pero cada pack individual solo sustituye la
fuente raw cuando cumple las puertas estructurales:

- evidencia requerida cubierta o `Declined` explícito;
- fallback raw cuando el pack no está `ready`;
- `pack_hash` y hash de selección añadidos a la clave de caché antes de afectar una pantalla;
- prueba de carrera: un resultado de una fuente antigua no puede quedar activo;
- componentes ricos resueltos por capacidades, sin hardcodearlos en el pack.

Cobertura factual, calidad frente a raw y variedad entre perfiles siguen siendo métricas del banco,
no responsabilidades del catálogo de componentes. La pantalla de creación solo expone en cada nodo
lo necesario para intervenir; tokens, duración, hashes y conteos técnicos quedan en observabilidad.

El pack tampoco depende de un componente concreto. Describe qué debe aprenderse y qué evidencia se
necesita. El planificador resuelve después si el catálogo puede materializarlo como texto, tabla,
imagen, simulación u otra capacidad. Añadir un laboratorio de animación enriquecerá la experiencia
sin cambiar el contrato factual del pack.

## Resultado del primer ajuste real

Una matriz de 18 llamadas con `gpt-4o-mini` comparó presupuestos de 1.200, 1.600 y 2.048 tokens
para extractor y revisor sobre caja, alérgenos y reclamaciones. Ninguna configuración produjo tres
packs utilizables: la cobertura fue 0/7, 2/7 y 7/7 respectivamente, y el último resultado agrupó todo
el procedimiento en un solo átomo. Los nueve quedaron `review_required`, por lo que la frontera
fail-closed evitó que material incompleto llegase al runtime.

Subir el presupuesto no cambió los resultados. El problema está en el contrato del prompt: sus
ejemplos semánticos fueron copiados como contenido y las referencias de evidencia propuestas no
quedaron conectadas a átomos válidos. Antes de otra prueba de pantallas se comparará el contrato
actual con JSON Schema sin valores de ejemplo y con una fase explícita de cobertura/atomización. El
informe reproducible está en
[`../evidencia-testing/2026-08-11/knowledge-pack-tuning/report.md`](../evidencia-testing/2026-08-11/knowledge-pack-tuning/report.md).

## Gate trazable adoptado (`knowledge-pack/v3`)

Las rondas posteriores convirtieron cobertura y procedencia en propiedades verificables. La fuente
se divide de forma determinista en unidades operativas; cada átomo declara sus unidades y el programa
añade un gap bloqueante si queda alguna sin representar. Los encabezados no se confunden con hechos,
las referencias admitidas se enumeran literalmente y cada pack `ready` exige evidencia. Una categoría
pedagógica desconocida puede degradar a `fact`, pero nunca se corrige ni reasigna silenciosamente el
texto o su fuente.

Con `gpt-4o-mini`, 3.200 tokens por pasada y dos llamadas por nodo, el gate terminó 3/3:

- caja: 11 invariantes, 100 % de los siete hechos gold, 35,77 s y unos 0,00288 USD;
- alérgenos: 9 invariantes, 100 %, 31,94 s y unos 0,00249 USD;
- reclamaciones: 19 invariantes, 100 %, 62,46 s y unos 0,00394 USD.

La preparación media fue aproximadamente 43 s y 0,0031 USD por nodo. Es más lenta que extraer un
resumen débil, pero ocurre una vez y evita servir material incompleto. Por eso el entorno de desarrollo
usa `knowledge-pack/v3`; el cambio de versión impide reutilizar packs anteriores bajo el contrato nuevo.

El primer A/B OpenUI (caja, tres repeticiones por brazo) mantuvo 3/3 renders a la primera. El pack no
cambió los cinco tipos de componentes, pero elevó la cobertura factual visible media de 19,0 % a
28,6 %, redujo tokens de entrada de 616 a 600 y de salida de 40 a 30; la latencia p50 fue prácticamente
neutra (5,609 s raw frente a 5,516 s pack). Es una señal favorable, no una prueba definitiva: `n=3` y
la cobertura absoluta de la pantalla sigue baja. El siguiente cuello de botella está en seleccionar
invariantes para una pantalla de baja densidad, no en añadir más prosa al extractor.

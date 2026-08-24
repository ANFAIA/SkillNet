---
title: "Ajuste fino (tuning)"
order: 33
section: "core"
---

# Ajustando el generador de cursos dinámicos

Los diales que se tocan cuando la salida de v2 sale mal, y qué hace cada uno en realidad.

Esto es el compañero de `apps/skillnet-api/scripts/quality_bench.py`, que es la única forma
honesta de saber si un cambio ayudó. El bucle es: tocar un dial, correr el banco, leer el
volcado de fallos. Un porcentaje sin los fallos delante no te dice qué arreglar.

```bash
cd apps/skillnet-api
uv run python scripts/quality_bench.py --offline     # sin clave, comprueba que el arnés funciona
uv run python scripts/quality_bench.py --repeat 3    # proveedor real desde .env
uv run python scripts/quality_bench.py --only extintor --model groq/openai/gpt-oss-120b
```

El banco corre el pipeline **real** (`run_node_render` → `build_node_graph()` → los ocho
nodos de `src/agents/runtime/nodes.py`). Falsea exactamente tres costuras — la sesión de BD,
SSE, y un wrapper bajo `litellm.acompletion` que añade un User-Agent y hace retroceso ante
429. Reporta tasas de acierto a la primera / reparado / fallback / error, latencia p50 y p95,
tokens y USD, diferencias frente a la ejecución anterior, y vuelca cada salida fallida con el
motivo del validador. Flags útiles: `--repeat`, `--only`, `--offline`, `--out`, `--compare`,
`--pause`, `--model` / `--model-fast` / `--model-heavy`, `--price-in` / `--price-out`,
`--dump-prompts`, `--list`, `--seed`.

**Cada valor de abajo se leyó del fichero citado.** Los números de línea se desplazan; los
nombres de las constantes no, así que busca por el nombre si la línea no coincide.

---

## Qué se midió, y qué significa para el ajuste

Medido contra Groq real el 2026-07-27 (`groq/llama-3.1-8b-instant` como nivel rápido,
`groq/openai/gpt-oss-120b` como el pesado): **de menos de un segundo a unos 3 s por render, a
unos 0,0008 USD por render**, con la contabilidad de tokens poblada.

El problema de "20-30 segundos de generación" que la fase de investigación asumía **no existe
en esta pila**. Las cifras de 60-150 s en las fuentes internas venían de un modelo 7B en CPU
local. Esto importa para el ajuste porque elimina la razón para pre-generar, para añadir capas
de espera, o para cambiar calidad por latencia: no hay presupuesto de latencia bajo presión.
Gastar los diales en *corrección*, no en velocidad.

La única restricción operativa real es que **el nivel gratuito de Groq devuelve 429 con
facilidad**. Cualquier ejecución de medición necesita retroceso — el banco lo trae integrado
(`RATE_LIMIT_MAX_RETRIES = 5`, `RATE_LIMIT_BASE_DELAY = 4.0`, `RATE_LIMIT_MAX_DELAY = 90.0`,
`quality_bench.py:119-121`), y cuenta la espera por separado en `rate_limit_seconds` para que
un rate limit nunca se compute como un fallo de calidad. Si escribes tu propio arnés, haz lo
mismo o tus números son ruido.

---

## 1. Qué modelo, y cuánto margen se le da

`src/config.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `LLM_RUNTIME_FAST_MODEL` | 30 | `None` | El nivel barato. Vacío significa que cae en cascada por `org_settings["llm_model"]` → `settings.LLM_MODEL`, así que toda la funcionalidad trabaja con un solo modelo configurado. Subirlo a un modelo mejor mejora *cada* render de `explanation`/`exercise` y lo encarece — eso es ~90 % de los renders por diseño. |
| `LLM_RUNTIME_HEAVY_MODEL` | 31 | `None` | El nivel caro, usado solo para `chart` / `mixed`. Misma cadena de fallback. Es el sitio más barato para comprar calidad, porque muy pocos renders pasan por aquí. |
| `LLM_REASONING_EFFORT` | 41 | `"low"` | Solo se envía a modelos de razonamiento (o-series, gpt-oss, deepseek-reasoner). `none` nunca envía el parámetro. Subirlo compra mejor estructura en `chart`/`mixed` y cuesta tokens de pensamiento facturados contra el mismo presupuesto que la respuesta. |
| `LLM_REASONING_TOKEN_HEADROOM` | 45 | `2048` | Presupuesto de finalización extra entregado a un modelo de razonamiento *por encima* de lo que pidió el punto de llamada, porque el punto de llamada presupuesta la respuesta y no puede ver el pensamiento. Fallo medido que esto existe para arreglar: en `groq/openai/gpt-oss-120b` con `max_tokens=1200` el modelo a veces gastaba todo el presupuesto pensando y devolvía `content` vacío, que el runtime leía como un programa inválido y enviaba al bucle de reparación para nada. Bajarlo y eso vuelve; `0` desactiva el margen por completo. |

`src/agents/runtime/router.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `HEAVY_FORMATS` | 36 | `{"chart", "mixed", "simulation"}` | Qué formatos van al nivel caro. Añadir `exercise` aquí es la forma contundente de subir la calidad en general; también mueve la mayor parte del tráfico al modelo caro, así que comprueba después la proporción rápido/pesado en `llm_usage_log`. |
| `ALLOWED_UI_FORMATS` | 40 | `{"explanation", "exercise", "chart", "mixed"}` | Qué puede devolver `decide_formato`. Cualquier otra cosa la recorta `coerce_ui_format`. `simulation` está deliberadamente ausente: nada en el kit congelado puede renderizar uno. |

---

## 2. Prompts y presupuestos

`src/llm/prompts/runtime.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `PROMPT_VERSION` | 44 | `"runtime/2"` | Parte de la `cache_key`. **Súbela cada vez que cambies cualquier prompt de este módulo de forma que cambie la salida**, o estarás midiendo renders cacheados obsoletos y concluyendo que tu cambio no hizo nada. Es la invalidación de caché más barata que hay — sin escrituras a BD. |
| `DECIDE_MAX_TOKENS` | 48 | `256` | Presupuesto para `decide_formato`, que responde un objeto JSON de una línea. No hay razón para subirlo; si el decisor se está truncando, el prompt está mal, no el presupuesto. |
| `DECIDE_TEMPERATURE` | 49 | `0.0` | La elección de formato es una clasificación. Subir esto hace que el mismo nodo renderice distinto para el mismo alumno en días distintos, y además fragmenta la caché. |
| `UI_TEMPERATURE` | 52 | `0.4` | La temperatura de generación de contenido. Hacia `0.0` para un dialecto sintácticamente más fiable y prosa más plana; hacia arriba para ejemplos más variados y más entradas al bucle de reparación. Es el primer dial a probar cuando la validez a la primera es baja. |
| `UI_MAX_TOKENS` | 57 | `{"fast": 1200, "heavy": 2400}` | Presupuesto de finalización por nivel. Una pantalla `chart`/`mixed` necesita espacio; una explicación simple no, y pagarlo en el 90 % de los renders es toda la razón de que existan los dos niveles. Si los fallos parecen programas truncados, sube el nivel que se está truncando — pero comprueba primero `LLM_REASONING_TOKEN_HEADROOM` si el modelo razona. |
| `MAX_UI_RETRIES` | 61 | `1` | Un intento de reparación, luego `fallback_seed`. Subirlo a 2 cuesta otra generación completa para un modelo que ya ha fallado dos veces con las mismas instrucciones; la palanca mejor medida es la cabecera de reparación de abajo. |
| `SOURCE_CONTEXT_MAX_CHARS` | 65 | `6000` | Cuánto texto fuente viaja con `genera_ui` (`clip_source` recorta en un límite de espacio en blanco, nunca a mitad de palabra). Por encima de esto el prompt deja de tratar sobre el nodo y empieza a tratar sobre el documento. Bájalo si el modelo está generando contenido de la parte equivocada de un manual largo. |
| `_DENSITY_BUDGET` | 77 | 5 entradas, 1–5 | El presupuesto de longitud en palabras, por `effective_density`. `1` = "2-3 bloques y frases muy cortas", `5` = "5-7 bloques". Es el texto que el modelo realmente lee — edita la redacción, no solo el número de bloques. |
| `_SCAFFOLD_RULES` | 86 | `novice` / `neutral` / `advanced` | Qué cambia cada banda de andamiaje, expresado como comportamiento y no como etiqueta. `novice` exige un ejemplo resuelto antes de preguntar nada; `advanced` va directo a los casos límite. Si los alumnos avanzados se quejan de que se les explica de más, este es el string a afinar. |
| `_ERROR_RULES` | 102 | `detail` / `procedural` / `conceptual` | Cómo `last_error_kind` cambia la siguiente pantalla (§7.4). |
| `_SIGNAL_RULES` | 119 | 5 acciones | Vocabulario cerrado que mapea `tutor_notes.signals` a instrucciones. Cerrado a propósito: una señal nunca puede convertirse en prosa libre inyectada en un prompt (§3.3). Añade una entrada aquí *y* en el productor, nunca solo aquí. |
| `FORMAT_DECIDER_SYSTEM` | 133 | — | Todo el prompt de selección de formato. Las reglas duras que importan: nada de `chart` sin cifras reales en la fuente, nada de `exercise` salvo que el resultado esperado del nodo sea una acción, nunca `chart` solo en un nodo `critical`, y `explanation` en caso de duda. Si el nivel pesado supera ~25 % del tráfico, este prompt está eligiendo `chart` de más. |
| `_UI_REPAIR_HEADER` | 267 | — | La cabecera del prompt de sistema de reparación. El bloque de contraejemplo MAL/BIEN no es decoración: medido contra `qwen2.5:7b-instruct` (2026-07-26), los dos errores de sintaxis que comete un modelo pequeño son **argumentos con nombre** y **dividir una llamada en varias líneas**, ambos ya prohibidos en la prosa y cometidos igualmente. El último párrafo existe porque el modo de fallo real del bucle era *perseguir el bug equivocado* — el modelo reescribiendo comillas correctas tres intentos seguidos. Con un solo reintento, esta cabecera es donde se compra la calidad. |

**El fragmento del dialecto nunca se escribe a mano.** `ui_generator_system()` es
`src.render.prompt.render_prompt()` — el artefacto generado a partir del kit del frontend —
más el protocolo de clave de respuestas. No pegues firmas de componentes en este módulo; ese
es el desajuste que `tests/test_render_prompt_artifact.py` existe para detectar.

---

## 3. La puerta: qué se rechaza antes de parsear

`src/render/gate.py`. Son límites de seguridad, no diales de calidad — pero un programa
rechazado aquí aparece en el banco como una reparación o un fallback, así que se leen como
problemas de calidad.

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `MAX_PROGRAM_BYTES` | 47 | `16_384` | Tope de tamaño total del programa, aplicado antes de que ocurra nada costoso. Una especificación de 12 componentes con prosa larga son ~4 kB, así que esto es generoso. Acota el trabajo que un documento envenenado puede pedirle al parser y al navegador. |
| `MAX_PROGRAM_LINES` | 50 | `MAX_COMPONENTS + 8` (= 20) | Contado en líneas **lógicas** — declaraciones, unidas a través de saltos de línea que caen dentro de un corchete abierto (`src/render/lines.py::logical_lines`), que es donde lang-core también divide sentencias. Antes contaba líneas físicas, así que un programa del tamaño correcto con una línea en blanco entre declaraciones medía 23 y al modelo se le decía que acortara una lección que tenía la longitud correcta. `MAX_COMPONENTS` es `12` (`src/render/spec.py:51`); el `+ 8` es margen para un bloque delimitado y un intento de reparación. |
| `MAX_LINE_BYTES` | 53 | `4_096` | Una línea es el texto de un componente. Nota: `FALLBACK_BLOCK_CHARS` de abajo está fijado bastante por debajo de esto a propósito. |
| `RENDER_ALLOW_REACTIVE` (`src/config.py:85`) | 85 | `False` | **Déjalo apagado.** El precio de activarlo está en `openui-adoption.md` §3: hay que enseñarle al modelo toda la sintaxis reactiva de golpe (los flags del prompt no se dividen), y una propiedad estructural — "la gramática no puede expresarlo" — degrada a un contrato que hay que reverificar en cada release de `@openuidev`. |

La comprobación de reactividad es deliberadamente ligera y textual: primero deja en blanco
cada literal de cadena, luego comprueba el esqueleto restante contra el alfabeto que la
gramática congelada puede producir. Ese orden es todo el truco — un grep de palabras clave
sobre texto crudo ha medido falsos positivos en prosa legítima ("en SQL una Query() se
escribe con SELECT", "cuesta $300").

---

## 4. La regla de maestría

`src/services/mastery_service.py`. Todo en este módulo es puro — sin BD, sin LLM, sin reloj
que no se pase explícitamente — porque la regla que decide qué dice un certificado tiene que
ser testeable caso por caso. **Cambiar cualquiera de estos cambia qué significa "dominado"**,
así que cámbialos con los tests unitarios abiertos.

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `THRESHOLDS` | 37 | `critical 0.90`, `recommended 0.80`, `contextual 0.70` | El listón de maestría por criticidad. Depende del nodo, nunca de la persona (§7.2 regla 4). `course_nodes.mastery_threshold` lo sobreescribe por nodo. Subir `critical` hace que los cursos sean más difíciles de completar — completar exige que *todos* los nodos críticos no archivados estén dominados. |
| `DOUBT_BAND_FLOOR` | 38 | `0.55` | Estimaciones en o por encima de esto pero por debajo de 1.0 van al desempate en vez de directas a `learning`. Bájalo y más alumnos reciben un tercer ítem construido. |
| `W_APPLY` / `W_UNDERSTAND` | 39 | `0.6` / `0.4` | Pesos de los dos ítems de sondeo de respuesta seleccionada. |
| `W3_APPLY` / `W3_UNDERSTAND` / `W3_CONSTRUCTED` | 42 | `0.45` / `0.15` / `0.40` | Pesos de desempate renormalizados. Suman 1.0 deliberadamente: en la versión anterior el desempate topaba en 0.80 y era código muerto en un nodo `critical`. |
| `APPLY_FLOOR` | 44 | `0.5` | Fallar el ítem de "aplicar" nunca puede producir maestría, digan lo que digan los otros ítems. Es la cláusula anti-adivinanza; no la bajes para que los números se vean mejor. |
| `ALPHA` | 48 | `0.4` | Peso de la evidencia nueva en el EWMA. Más alto = la maestría reacciona más rápido a la última respuesta y es más ruidosa. |
| `FADING_STREAK` | 49 | `3` | N respuestas correctas seguidas → se aplica el techo de maestría *y* elegibilidad para `mastered`. El techo arregla un bug aritmético real: `0.6*old + 0.4*score` tiene su punto fijo en `score`, así que un 0.85 sostenido se quedaba 0.05 por debajo del umbral de un nodo crítico para siempre y el curso era permanentemente inacabable. Bajar esto a 1 elimina la defensa de "racha, no un pico de suerte" contra la descarga cognitiva. |
| `REGRESS_STREAK` | 50 | `2` | Fallos consecutivos antes de que la dificultad baje y se emita `reforzar_con_ejemplo`. |
| `HINT_LIMIT` | 54 | `3` | Pistas por ítem. Un click-para-explicar dentro de un `QuizItem` sin responder cuenta y consume cuota (§8.5). |
| `NEEDS_REVIEW_FAILURES` | 55 | `4` | Fallos del mismo ítem, tras gastar las pistas, antes de que el nodo salga a `needs_review`. |
| `REPROBE_COOLDOWN_DAYS` | 59 | `7` | Re-sondear solo desde `needs_review`, y solo tras este tiempo. Es la regla anti-reintento (§3.4). |
| `MASTERY_PRIOR` | 63 | `high 0.85`, `medium 0.55`, `low 0.25` | Semilla para `learner_node_states.mastery` a partir de `user_skills.level` (§7.1). Un punto de partida solo para el EWMA y la banda de andamiaje — nunca salta un nodo por sí solo. |
| `SKILL_LEVEL_MEDIUM_FLOOR` / `SKILL_LEVEL_HIGH_FLOOR` | 67 / 68 | `0.5` / `0.85` | `mastery` → `user_skills.level` a la salida. |
| `TARGET_BLOOM` | 69 | `shu→understand`, `ha→apply`, `ri→analyze` | El nivel cognitivo pedido al ejercicio, derivado de dónde está la maestría respecto al umbral. Viaja hacia `build_ui_prompt`. |

---

## 5. Comportamiento del grafo de runtime

`src/agents/runtime/nodes.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `RETRIEVAL_TOP_K` | 104 | `8` | Chunks recuperados para la rama `chunked` de `load_context`. Solo se alcanza para documentos por encima de `FULL_TEXT_PAGE_THRESHOLD` (`5` páginas, `src/agents/content/helpers.py:20`); cualquier cosa más pequeña entra entera y no necesita embeddings en absoluto. Subirlo mete más fuente en un prompt que `SOURCE_CONTEXT_MAX_CHARS` luego recortará, así que sube ambos o ninguno. |
| `FALLBACK_BLOCK_CHARS` | 108 | `2800` | Tamaño de cada bloque `Markdown` en el fallback de semilla. Limitado bastante por debajo de `MAX_LINE_BYTES` (4096) porque toda la lección semilla vive en **una** línea una vez serializada, saltos de línea escapados y todo. |
| `FALLBACK_MAX_BLOCKS` | 110 | `4` | El fan-out raíz está limitado a 5 y el bloque principal ocupa uno de ellos. |

`src/services/learner_profile_service.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `CALIBRATION_NODES` | 66 | `3` | Por debajo de este número de nodos completados, `decide_formato` **no hace ninguna llamada al LLM** y el formato es `node.default_ui_format`. No es "preguntado e ignorado" — preguntado e ignorado seguiría costando una llamada. La razón es pedagógica, no económica: el alumno tiene que construir un mapa mental antes de que la interfaz empiece a moverse (la lección de los menús adaptativos de Office 2000). Bajarlo a 0 activa la personalización desde el primer nodo y hace que los casos de calibración del banco dejen de ejercitar esa rama. |

El corpus del banco incluye deliberadamente alumnos con `nodes_completed < 3`
(`extintor`, `prevencion-riesgos`) precisamente para medir esta rama.

---

## 6. Trabajar sin una clave de API

`src/config.py`

| Dial | Línea | Actual | Al tocarlo |
|---|---|---|---|
| `LLM_FIXTURE_DIR` | 49 | `"src/llm/fixture_data"` | Dentro del paquete, así que los fixtures grabados van en la imagen Docker. |
| `LLM_FIXTURE_MODE` | 50 | `"replay"` | `replay` sirve pares grabados; `record` llama al proveedor real y escribe cada par `(prompt, response)` en el directorio. Los fixtures se activan poniendo `LLM_MODEL=fixture/local` (y `EMBEDDING_MODEL=fixture/local`), no con este flag. |

`FixtureLLMService` resuelve por hash exacto de `(system, user)`, así que un corpus nuevo no
tiene grabaciones y fallaría en la primera llamada. Nota la consecuencia para el ajuste:
**cambiar un prompt invalida todos los fixtures**. Regraba, o usa `--offline`, que se
autosiembra.

---

## Dónde viven los números después

- `llm_usage_log` — por llamada: `use_case`, `purpose`, `model`, `tier`, `tokens_in`,
  `tokens_out`, `duration_ms`. Esto es lo que responde "¿de verdad es 90/10 la proporción
  rápido/pesado".
- `node_renders` — por render: `tokens_*` y `duration_ms` para el render **completo**, con
  todas las llamadas y cada reintento incluidos.
- Los conteos de tokens son `None`, nunca `0`, cuando nadie contó. `0` afirma que la llamada
  fue gratis; fusionar ambos haría que un modelo de coste no medido pareciera medido.
</content>

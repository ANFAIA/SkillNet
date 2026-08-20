# Como probar SkillNet a mano

Guia de recorrido para v2 (cursos dinamicos). Esta escrita para hacerse entera de una
sentada, en el orden en que estan las cosas: primero se levanta la pila, luego se siembra
un cliente creible, y despues se recorren las tres superficies — creador, aprendiz y v1
intacto — cada una con lo que hay que mirar y con lo que significa si sale mal.

Lo automatico esta al final (§7 y §8). Ninguna de las dos partes sustituye a la otra: las
suites demuestran que el sistema hace lo que dice, el recorrido a mano demuestra que lo
que dice sirve para algo.

---

## 1. Levantar la pila

```bash
cp .env.example .env     # y rellenar SECRET_KEY, POSTGRES_PASSWORD, LLM_*
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

`--build` no es decoracion: el fichero de desarrollo cambia el `target` a `builder`, y sin
build docker reutiliza en silencio la imagen `runtime`, que no tiene `uv` en el PATH.

Queda:

| | |
|---|---|
| SPA | http://localhost:3000 |
| API | http://localhost:8000 — docs en `/docs` |
| Postgres | `localhost:5432` |

Ambos modos (v1 estatico y v2 dinamico) estan siempre disponibles. La eleccion es por
curso: un curso es dinamico cuando tiene `delivery_mode='dynamic'` y `schema_status='validated'`.

Comprobacion en una linea:

```bash
curl -s http://localhost:8000/health
# {"status":"ok","version":"0.1.0","database":"connected",...}
```

### Sin ninguna clave de API

```bash
docker compose --profile fixtures up -d db api-fixtures    # http://localhost:8001
```

Misma imagen, pero `LLM_MODEL=fixture/local` y `EMBEDDING_MODEL=fixture/local`: cada llamada
al modelo se sirve de las grabaciones de `src/llm/fixture_data`. Sirve para recorrer el flujo
y para demostrar que la aplicacion arranca; **no** sirve para juzgar la calidad de la
generacion, porque no genera nada.

---

## 2. Sembrar los datos de prueba

```bash
docker compose exec api uv run python -m src.seed_learning_demo
```

Es la demo publica: un tema meta y on-brand sobre **como aprende la mente**, dentro de la
unica organizacion que la aplicacion arranca. Genera y valida cada curso en el seed, asi que
la generacion es LLM-backed y un run completo es lento (es lo esperado). Es idempotente y
re-ejecutable: reusa un curso ya validado con el mismo titulo. Al arrancar limpia los datos
de la panaderia retirada ("La Espiga") en bases de dev que todavia los arrastren.

**Tres aprendices demo**, contrasena `aprender2026` para todos. Cada uno declara un estilo
distinto para ejercitar la personalizacion:

| Cuenta | Para que esta |
|---|---|
| `ana@skillnet.dev` | Metaforas + AUDIO: el broker de medios le ofrece el `PodcastPlayer` inline. |
| `bruno@skillnet.dev` | Definiciones primero + VISUAL: ve la `InfographicImage` inline. |
| `carla@skillnet.dev` | **Sin perfil de aprendiz a proposito.** Es la cuenta con la que se recorre el onboarding. |

El admin es el `ADMIN_EMAIL` / `ADMIN_PASSWORD` del `.env`.

**Cuatro cursos dinamicos**, todos validados en el seed: "Como aprende tu cerebro" (el
escaparate, con podcast + infografia por nodo), "Sesgos cognitivos", "La ciencia de los
habitos" y "Memoria y olvido" (estos tres con un podcast a nivel de curso). El script imprime
los ids y los resultados por curso al terminar.

`--skip-delete` omite la limpieza de datos antiguos y solo crea/actualiza la demo nueva.

> Nota: esta demo no siembra ningun curso **estatico v1**, asi que el recorrido §4.3 (comparar
> los dos caminos en la misma instancia) requiere crear a mano un curso `delivery_mode='static'`.

---

## 3. Recorrido del creador (admin)

Entrar en http://localhost:3000 con la cuenta de admin.

1. **Contenido** → la lista de cursos. Los dos dinamicos tienen ahora un boton **Esquema**
   junto a "Ver curso". Antes no lo tenian: la unica forma de llegar al esquema era teclear
   la URL. Ahora el boton aparece siempre para cursos dinamicos.
2. **Esquema** → el grafo de nodos que el creador valida. Mirar, en este orden:
   - cada nodo con su titulo, resultado, criticidad (`critical` / `recommended` /
     `contextual`) y los encabezados del documento de los que sale;
   - **la puerta**: un esquema `validated` no se puede editar, y un nodo sin revisar no
     deja validar. Las dos cosas devuelven `422` con `code: schema_invalid`, no un 500
     ni un guardado silencioso;
   - el enlace **← Volver al curso**, que tampoco existia.
3. Desde **Crear curso**, con un documento como fuente, aparece **Definir esquema**: es el
   camino "esquema primero", en el que la IA propone el indice y el creador lo valida antes
   de que se genere una sola pantalla.

Lo que se esta comprobando aqui es que el creador manda. Si algo se puede validar sin
revisar, o se puede editar despues de validar, es un fallo grave y no cosmetico.

---

## 4. Recorrido del aprendiz

### 4.1 Onboarding — con `carla@skillnet.dev`

Es la unica cuenta sin perfil, asi que al entrar el gate la manda al asistente. Preguntas
cortas: puesto, sector, objetivo, experiencia declarada y necesidades de lectura.

**No se pregunta por ningun diagnostico** (TEA, TDAH, dislexia). Es un dato de salud del
articulo 9 del RGPD y no se recoge: se pregunta por *necesidades* — bloques cortos, mas
ejemplos — que es lo que el motor puede usar de verdad.

Se puede saltar. Y desde el menu de la cuenta, arriba a la derecha, **Preferencias de
aprendizaje** vuelve a entrar en el asistente: saltarlo era permanente hasta ahora, y el
asistente es el unico sitio donde se fija el perfil. Aviso conocido: al reentrar los campos
salen en blanco, no precargados, y un envio completo sobrepisa el perfil entero.

### 4.2 Un nodo, de principio a fin

Con cualquiera de las cuentas con perfil (`ana@` o `bruno@`), abrir **Como aprende tu
cerebro**.

1. **La lista de nodos.** Los nodos con prerrequisitos sin cumplir salen bloqueados. En el
   panel y en Mis Cursos los cursos dinamicos llevan una etiqueta **Por nodos** para
   distinguirlos de los v1 antes de abrirlos.
2. **El pre-assessment.** Antes de generar nada, el nodo pregunta. Si el aprendiz demuestra
   que ya lo sabe, el nodo se salta y **cuesta cero tokens**: es el ahorro que justifica
   todo el diseno. Con `ana@` (audio) y `bruno@` (visual) el broker de medios ademas ofrece
   distintos componentes inline segun el estilo declarado de cada uno.
3. **La generacion.** La pantalla se construye al vuelo para *ese* aprendiz. Mirar la
   secuencia de pasos que llega por SSE: `load_context → probe_gate → decide_formato →
   genera_ui → validate_ui → persist_render`.
4. **La pantalla.** Bloques del kit congelado, nunca HTML del modelo. Son 9 los que el
   modelo puede emitir (`GET /render-kit` → `components`) mas `Markdown`, que solo escribe
   el servidor para la version de respaldo; los 10 que el navegador sabe pintar salen en
   `render_components`.
5. **Todo es clicable.** Seleccionar un termino que no se entienda pide una explicacion en
   contexto, sin salir de la pantalla.
6. **Las pistas.** En un ejercicio fallado, la escalera de pistas va de menos a mas antes de
   dar la solucion.
7. **Maestria.** Al responder bien, el estado del nodo avanza y desbloquea el siguiente. Al
   cerrarse el ultimo nodo critico, se cierra la matricula.

**Que mirar si sale una pantalla sosa.** Si el contenido parece la leccion semilla de
siempre, probablemente lo es: el render acabo en `fallback`. Eso no es un error visible al
usuario a proposito — el aprendiz se lleva una pantalla en vez de un fallo — pero para
juzgar la calidad hay que saber distinguirlo:

```bash
docker exec skillnet-db-1 psql -U skillnet -d skillnet -c \
  "SELECT status, tier, model, ui_format, tokens_in, tokens_out, duration_ms,
          left(coalesce(error_message,'-'),200) AS err
     FROM node_renders ORDER BY created_at DESC LIMIT 10;"
```

`status='ready'` es una pantalla generada. `fallback` es la leccion semilla. `failed` es un
fallo de verdad y lleva `error_message`. El porque exacto de un `fallback` sale del banco de
calidad (§8), que vuelca la queja literal del validador y la salida cruda del modelo.

### 4.3 Comparar los dos caminos

La demo publica no siembra ningun curso estatico v1. Para comparar los dos caminos en la
misma instancia, crear a mano un curso con `delivery_mode='static'` (el arbol de modulos y
lecciones de siempre) y recorrerlo junto a uno dinamico: verlos seguidos es la forma mas
rapida de entender que cambia v2.

---

## 5. Que tiene que seguir siendo verdad

Cuatro invariantes. Cualquiera de ellas rota es un bloqueante, no una incidencia:

1. **Con el flag en `off`, v1 se comporta exactamente igual.** Toda ruta v2 devuelve `404`,
   indistinguible de una ruta que no existe, y ninguna pantalla v1 cambia. Cubierto por
   `tests/integration/test_v1_regression.py`.
2. **`answer_key` no sale nunca al cliente**, en ninguno de los cuatro sitios por donde
   podria escaparse: items del probe, render, resultado del intento e historial.
3. **El navegador no recibe nunca `raw_dsl`**, solo texto reserializado desde una `UISpec`
   validada.
4. **La reactividad de OpenUI esta apagada.** Ninguna pantalla dispara consultas por su
   cuenta. Las razones, medidas, estan en `docs/design/openui-adoption.md`.

Comprobacion rapida: crear un curso estatico (v1) y verificar que el recorrido §4.3 sigue
intacto. Los cursos con `delivery_mode='static'` se sirven siempre por v1.

---

## 6. Los tres modos del flag

| Valor | Backend | Frontend |
|---|---|---|
| `off` (defecto) | Todas las rutas v2 dan `404`; `delivery_mode` se ignora | Nada de v2. Produccion tal cual esta hoy |
| `shadow` | Solo la superficie de **admin** (proponer, editar, validar esquema; previsualizar con `?preview=1`) | El creador ve el esquema; el empleado ve v1 |
| `on` | Todo activo | v2 completo |

Con `on`, un curso solo va por v2 si es `delivery_mode='dynamic'` **y**
`schema_status='validated'`. Cualquier otro sigue por v1 en la misma instancia. La condicion
vive en un solo sitio: `src/services/course_delivery.py::resolve_delivery`.

---

## 7. Las suites automaticas

```bash
cd apps/skillnet-api
uv run pytest -m "not integration"    # sin base de datos ni claves
uv run ruff check src tests

# Las de integracion necesitan un Postgres vivo:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
$env:DATABASE_URL="postgresql+asyncpg://skillnet:skillnet@localhost:5432/skillnet"
uv run pytest -m integration
```

```bash
cd apps/skillnet-web
pnpm exec tsc -b && pnpm test && pnpm lint
```

Las tres suites de integracion, que son las que tocan SQL de verdad:

- `test_migration_0005.py` — sube y baja la migracion con datos v1 dentro. **Baja el esquema
  mientras corre**, asi que no se lanza en paralelo con las otras dos contra la misma base.
- `test_v1_regression.py` — v1 entero con el flag apagado.
- `test_dynamic_flow.py` — el corte vertical de v2, de esquema propuesto a curso cerrado.

Para correr varias a la vez, una base por suite:

```bash
docker exec skillnet-db-1 psql -U skillnet -d postgres -c "CREATE DATABASE skillnet_t1"
```

Fallo pre-existente conocido, heredado de `main` y ajeno a este trabajo:
`tests/test_grading.py::test_grade_open_answer_fallback` (el commit `c68d045` cambio el
comportamiento y no actualizo el test). Ruff tiene 5 violaciones igualmente pre-existentes.

---

## 8. Medir la calidad de la generacion

Un recorrido a mano dice "esto parece peor". El banco dice cuanto:

```bash
cd apps/skillnet-api
uv run python scripts/quality_bench.py --offline      # sin clave, comprueba que el banco va
uv run python scripts/quality_bench.py --repeat 3     # contra el proveedor del .env
uv run python scripts/quality_bench.py --only extintor --model groq/openai/gpt-oss-120b
```

Corre el pipeline **real** sobre 10 encargos fijos y saca: aciertos a la primera, rescatados
por el bucle de reparacion, acabados en fallback, errores, p50 y p95, tokens y coste — mas la
comparacion con la ejecucion anterior y **el volcado de cada salida fallida con el motivo
exacto del validador y la salida cruda del modelo**, en `bench_out/failures/`. Un porcentaje
sin los fallos delante no arregla nada, asi que las dos cosas salen siempre juntas.

Los diales que se tocan entre ejecucion y ejecucion estan en `docs/design/tuning.md`.

Dos avisos medidos el 2026-07-27 contra Groq:

- **El plan gratuito da 429 con facilidad.** El banco ya reintenta con retroceso
  exponencial, pero una ejecucion completa se pasa minutos durmiendo y la latencia p50 que
  reporta incluye esa espera. Para hablar de latencia real, mirar los milisegundos por
  intento en los volcados, no el p50.
- Los volcados de fallos contienen `raw_dsl` **a proposito** — son para leerlos en un
  editor. `answer_key` no se escribe en ningun fichero.

---

## 9. Cuando algo va mal

```bash
docker compose logs api --tail 100 -f
docker compose ps                       # ningun servicio deberia estar (unhealthy)
```

Tres cosas que parecen un fallo de la aplicacion y no lo son:

- **Todas las rutas v2 dan 404.** El flag esta en `off` o en `shadow`. Mirar `/health`.
- **Un curso dinamico se sirve como v1.** Le falta `schema_status='validated'`, o el flag no
  esta en `on`. Las dos condiciones tienen que darse.
- **La pantalla del nodo es la leccion de siempre.** Es un `fallback`; ver §4.2.

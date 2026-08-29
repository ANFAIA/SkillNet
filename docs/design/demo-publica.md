# Demo pública — una máquina de 1 vCPU decide la arquitectura

> **Estado: diseño acordado el 2026-08-30. Nada implementado.** Las cifras de la sección 1
> están medidas ese día sobre la máquina de despliegue; si la máquina crece, la sección 1
> es lo primero que hay que volver a medir, porque **de ella sale todo lo demás**.

Una persona que llega a la landing debe poder probar SkillNet sin instalar nada, y salir
sabiendo qué es. Este documento decide cómo, y sobre todo **qué es lo que manda**.

## 1. La restricción real

No es el dinero del proveedor de modelos. Es la máquina:

| | |
|---|---|
| CPU | **1 vCPU** |
| RAM | 3.8 GB, de los que ~2.0 GB ya están ocupados, **~1.8 GB disponibles** |
| Swap | 2 GB, con ~830 MB **ya en uso** |
| Disco | 48 GB, 24 GB libres |
| Carga | ~0.65 sostenido sobre un único núcleo |

Del disco, lo medido el mismo día: 24 GB libres, con **6.10 GB recuperables de caché de
construcción** y 12 GB en imágenes. La imagen de la API pesa **1.97 GB**; la del sitio, 80 MB.
Los volúmenes de un despliegue anterior de SkillNet ocupan 46 MB en total — borrarlos es
higiene, no espacio.

Y los datos por visita: el paquete del curso escaparate pesa 212 KB (26 KB por nodo), que se
instalan en la org de cada visita, más lo que genere. Del orden de **1-2 MB por visita**,
purgados a las 24 h. Con el techo de 150 cursos al día, el pico de datos vivos ronda los
**300 MB**.

Conclusión que conviene tener clara antes de optimizar nada: **el disco no es la
restricción.** Lo es la memoria — 1.8 GB para Postgres y API — y lo es el único núcleo.

Y no está vacía: comparte máquina con el panel de despliegue (que por sí solo pasa del
gigabyte entre su proceso y su Postgres), el proxy inverso, otro sitio y la propia landing.

De ahí sale la frase que gobierna el resto del documento: **la demo no compite por euros,
compite por el único núcleo.** Un curso más no cuesta más dinero de forma apreciable;
cuesta que la siguiente persona espere el doble.

## 2. Lo que ya existe y hace que esto sea barato de construir

Cuatro piezas del repo, no cuatro cosas por escribir:

- **Los paquetes de curso se instalan sin una sola llamada al LLM**
  (`services/course_package/install.py`, `docs/design/course-packages.md`). Las pantallas se
  siguen generando vivas por aprendiz. Eso separa lo caro (el curso) de lo barato (la
  pantalla), y es lo que permite que la demo sea **instantánea** en vez de una barra de
  progreso.
- **Todo está scopeado por `org_id`.** Una org por visita no añade ninguna regla de
  aislamiento: reusa la única que hay.
- **`<Gated>` y `derive_capabilities`** ya son el mecanismo para decir "aquí no" sin
  esparcir condicionales (`components/Gated.tsx`, `services/capabilities.py`).
- **`explain_service.check_rate_limit`** ya es el patrón de ventana deslizante.

Y una que **falta** y es la más importante: la generación son tareas asyncio dentro del
proceso de la API (`services/course_finalization.py:175`), con semáforo *dentro* de un curso
(`knowledge_pack/runner.py:237`) pero **ningún techo entre trabajos**. Hoy da igual, porque
quien las dispara es una persona administradora. Con una puerta pública, diez visitantes son
diez pipelines en un proceso, en un núcleo, con 1.8 GB.

## 3. Decisiones

### D1 — Una org efímera por visita, y el visitante es su admin

`POST /demo/session` crea org + usuario **con rol admin**, instala el paquete del curso
escaparate y devuelve **la cookie de siempre**. A partir de ahí no hay código de demo en
ninguna ruta: es un usuario normal de una org normal, usando el producto entero — su
biblioteca, el asistente de creación de verdad, el editor de esquema, los ajustes.

Es admin **porque crear un curso es lo que la demo existe para enseñar**, y crear cursos es
`AdminUser` (`routes/courses.py:289`). La alternativa —visitantes con rol `employee` en una
org compartida, aislados por matrículas— respeta más invariantes y enseña la mitad del
producto: sirve para exhibir la experiencia de aprender, no la de montar formación.

Nadie ve nada de nadie porque la frontera es `org_id`, **la misma que separa a dos empresas
clientes**. No se introduce ninguna segunda regla de aislamiento que pueda discrepar de la
primera. Las alternativas se descartaron así: una **org compartida con admins** deja a
cualquiera borrar los cursos de los demás; **credenciales publicadas** no dejan crear nada y
convierten la demo en un vídeo.

`workspace_mode='individual'` (migración 0017) describe exactamente lo que es cada visita:
una persona que administra y aprende en su propio espacio.

La org lleva su caducidad y su consumo en la fila (`demo_expires_at`, contadores). Purgar es
borrar la org.

#### El precio, y por qué es pequeño

Esto convierte en real el multi-org en un despliegue donde `routes/settings.py:8` afirma
*"SkillNet is one organization per deployment"*. Medido, el coste es **una función de cuatro
líneas copiada cuatro veces**: `_org_settings` en `deps/llm.py:24`, `explain.py:41`,
`nodes.py:179` y `course_orchestration.py:169`, todas con `select(Organization).limit(1)`
**sin `ORDER BY`** para leer los ajustes de proveedor.

El arreglo es una `deployment_org_settings(db, org_id=None)` compartida que prefiere el
`org_id` y ordena el fallback por antigüedad. `chat.py:37` **ya tiene esa versión**, así que
el patrón no hay ni que inventarlo, y el comentario de `explain.py` explica que la
duplicación fue por reparto de trabajo, no por diseño.

Y ese `ORDER BY` **no es deuda de la demo**: hoy, en cualquier despliegue que llegue a tener
dos orgs, esos cuatro sitios devuelven la que Postgres decida. La demo solo obliga a mirarlo.

El resto de sitios que consultan la org sin `org_id` (`course_package/install.py:87`, los
`nodes.py` de los tres agentes) solo lo hacen **cuando no reciben uno**, y la demo siempre lo
pasa. No hay que tocarlos.

### D2 — Una cola global de concurrencia 1, con la posición a la vista

Es la pieza central, por delante del control de gasto. Un 429 en la cara es una demo rota;
*"vas segundo, ~90 s"* es una demo honesta, y de paso enseña que detrás hay trabajo real.

La cola vive tras su propia frontera (`services/demo_queue.py`), **no** como `create_task`
esparcidos. Esa frontera es la razón de que crecer sea cambiar un número, y de que el día
que la cola tenga que ser un proceso aparte no haya que tocar ninguna ruta.

### D3 — La fricción va delante del gasto, no en la puerta

- **Entrar: sin fricción.** Un clic. Cuesta un paquete (cero LLM) y las pantallas que la
  persona mire.
- **Crear un curso: Turnstile.** Un token verificado en el servidor, delante de la única
  operación cara. No exige pasar el DNS por Cloudflare y no pone cookies de seguimiento.
- **Límite por IP** en la creación de sesiones, para que nadie llene el disco de orgs.
- **Techo diario global** como interruptor final.

Se descartó pedir **email** a la entrada: cuesta conversión justo en el instante en que la
demo iba a convencer, mete datos personales en un flujo anónimo, y un bot escribe un email
falso — o sea que frena a quien no había que frenar. Si se quiere el contacto, se pide
**después**, con el curso ya hecho y como ofrecimiento.

El techo se cuenta en **trabajos, no en euros**: los euros solo se conocen a posteriori y
por una API ajena; los trabajos se cuentan en la fila antes de gastar nada.

### D4 — Lo que no está en la demo se dice con el mecanismo que ya existe

Un `CapabilityReason` nuevo (`demo_deployment`) y `<Gated mode="explain">` en los controles
afectados. El control se ve, está inerte y dice por qué, con su llamada a instalar. Ninguna
rama `if demo` en las vistas.

El detalle que lo hace valer la pena: **cuando salte el techo diario, la degradación va por
el mismo camino**. Un solo modo de decir que no, ya escrito y ya probado.

### D5 — Base de datos propia y límites de memoria explícitos

«Propia» aquí no contradice a D7: la instalación es una sola, pero su Postgres es suyo.
Base de datos propia con pgvector — **nunca** el Postgres del panel de despliegue, que es su
cerebro de control. Y `mem_limit` en cada servicio: sin él, un pico invoca al OOM killer,
que elige a ciegas y se puede llevar por delante el panel o el proxy, tirando también la
landing y el otro sitio. Con límites muere el contenedor culpable y reinicia solo.

Reparto de partida, sobre los ~1.8 GB: base de datos 400 MB, API 700 MB, estático ~20 MB.
Subir la swap de 2 GB a 4 GB es la red, no el plan.

### D6 — Caducidad y purga

Sesiones con TTL de 24 h, purga nocturna de las caducadas, `MAX_UPLOAD_SIZE_MB` bajo.

**La cookie es la sesión, y no se recupera.** Quien cierre el navegador y vuelva encuentra
un espacio nuevo; el anterior se purga. Se descartó darle un enlace personal para volver:
es más código, obliga a decidir cuánto vive ese enlace, y la demo no es un sitio donde
guardar trabajo — es un sitio donde entender qué es esto. Lo que sí abre esa puerta es lo
que queda en la sección 7.

24 GB libres se llenan solos si cada visita deja rastro y nadie barre.

### D7 — La máquina es solo la demo

No hay instancia «de casa» en el servidor: el trabajo real se hace en local. **Toda org que
exista en ese despliegue es una visita y toda org caduca.** `demo_expires_at` se queda porque
es lo que la purga necesita, no porque distinga dos clases de organización.

Esto tiene una consecuencia que conviene anotar, porque contradice lo que parecía:
**consolidar `_org_settings` (D1) deja de ser un bloqueo.** Si ninguna org lleva `settings`,
el `select(Organization).limit(1)` sin orden devuelve `{}` igual que devolvería la fila
correcta, y todo el mundo hereda el proveedor del `.env`. Sigue mereciendo la pena —son
veinte líneas y desactiva una mina que estallaría el día que una org tenga ajustes propios—
pero es higiene, no requisito.

El proveedor, entonces, es uno solo y vive en el `.env`: la clave barata, para todos.

### D8 — El gasto se cuenta en filas, no en contadores

Dos preguntas, dos consultas, ningún estado que mantener:

- **Cuota por visita:** ¿esta org ya tiene un curso creado? Entonces no hay segundo.
- **Techo diario:** ¿los cursos creados hoy por orgs con `demo_expires_at` llegan a
  `DEMO_DAILY_COURSES` (150)? Entonces la demo dice "vuelve mañana", por el mismo camino de
  `<Gated>` que todo lo demás.

Un contador en memoria habría mentido en el primer redespliegue, y uno en base de datos es
un segundo sitio donde la verdad puede desajustarse. Las filas ya están ahí.

El 150 es variable de entorno **a propósito**: es un dial que se toca sin desplegar. Con cola
de 1 y ~2 min por curso, un día lleno son unas 5 h del único núcleo, compartidas con lo de
casa. Si la máquina pesa, se baja el número.

## 4. Qué entra y qué no

Entra **el producto entero**, porque la visita es admin de su propio espacio: la biblioteca
(con el curso escaparate ya dentro, no vacía), el asistente de creación real, el editor de
esquema, los ajustes por curso, el recorrido como aprendiz, el tutor y las explicaciones a
clic. Nada de pantallas de demo ni fachadas.

Lo que se apaga, con `<Gated mode="explain">`:

| Fuera | Por qué |
|---|---|
| Subir documentos propios | Disco, parseo y embeddings en la máquina que solo tiene un núcleo |
| Podcast, voz e infografías | CPU y disco, por lo mismo |
| Invitar personas | Crearía usuarios y correos reales desde una sesión anónima |
| Exportar e instalar paquetes | Salida de datos y escritura en disco |
| Más de **un** curso creado por sesión | No cuesta más dinero: cuesta que la siguiente persona espere el doble |

Los paneles de grupos y talento se quedan: funcionan, son gratis y son parte del producto.
Estarán vacíos, porque la org de una visita tiene una persona — que es la verdad.

Nada de esto se apaga por ser secreto. Se apaga porque no cabe en un núcleo compartido, y el
aviso lo dice así, con su llamada a instalarlo para probarlo.

## 5. Lo que hay que escribir

- `services/organization_settings.py` — la `deployment_org_settings` compartida (ver D1).
  **Va primero**: sin ella el multi-org es no determinista.
- `routes/demo.py` — un endpoint: org + usuario admin + paquete + cookie.
- `services/demo_queue.py` — la cola global y la posición.
- `services/demo_budget.py` — contadores por org y techo diario.
- Verificación del token de Turnstile, solo en la creación de curso.
- Una migración: caducidad y contadores en `organizations`.
- `CapabilityReason.DEMO_DEPLOYMENT` y los `<Gated mode="explain">` de la tabla anterior.
- Exportar a paquete el curso escaparate desde una instancia con contenido bueno, y
  versionarlo en `course-packages/`. Es la primera impresión de todo el que entre: se
  elige mirándolo, no por estar ya en el repo.
- Entrada en la landing, pantalla de bienvenida en la SPA, purga programada.

## 6. Cómo crece

Cuando la máquina crezca, el orden es: **subir la concurrencia de la cola** (un número),
**sacar la base de datos a su propia máquina** (una variable), y solo entonces plantearse si
la cola necesita vivir fuera del proceso. Nada de eso toca una ruta, y esa es toda la razón
de que la cola y el presupuesto tengan módulo propio desde el primer día.

## 7. Dónde vive cada pieza

La landing **ya está en este repositorio** (`apps/skillnet-site`, 184 ficheros versionados).
Se despliega como contenedor aparte, pero no es otro proyecto, así que no hay ninguna
decisión que tomar sobre «dónde mandar esto».

Lo que sí es una decisión: **la demo es la SPA, no una página nueva de la landing.**
Reconstruir un trozo de la experiencia en Astro para enseñarla significaría mantener dos
versiones del producto, y la peor de las dos sería la primera que ve un visitante.

| Pieza | Dónde | Cuánto |
|---|---|---|
| Botón «Probar SkillNet» | `apps/skillnet-site/src/components/Hero.tsx` | tres líneas, junto a los CTA que ya hay |
| Bienvenida de la visita y avisos `<Gated>` | `apps/skillnet-web` | pequeño |
| Endpoint, cola, presupuesto, purga | `apps/skillnet-api` | el grueso |
| Curso escaparate | `course-packages/` | 212 KB |
| Variables y compose | raíz: **los dos** composes y `.env.example` | |
| Claves y notas de la máquina | fuera del repositorio | |

### Un repositorio, dos aplicaciones

No hay repositorio nuevo ni fork. Tres cosas que se confunden y son independientes:
**repositorio** (uno), **despliegues** (dos: la landing y la app) y **dominio** (dos
hostnames). Ya es así hoy: la landing y la app salen de este mismo repositorio y se
despliegan por separado.

Un fork sería lo peor de las opciones: cada mejora del núcleo habría que trasplantarla a
mano, y el fallo se descubriría el día que alguien abra la demo.

En el panel de despliegue es **una segunda aplicación** sobre el mismo repositorio, con
`docker-compose.dokploy.yml`, su propio entorno (`DEMO_MODE=true`, la clave del proveedor,
`DEMO_DAILY_COURSES`, el secreto de Turnstile) y su dominio.

Y el recordatorio que ya costó una vez: **una variable que no esté listada en el
`environment:` de `skillnet-api` de ese compose no llega nunca al contenedor**, porque `.env`
está en el `.dockerignore` y ningún servicio declara `env_file`. Rellenarla en el panel no
hace nada.

El botón apunta a un **hostname propio** (`demo.<dominio>`), no a una ruta de la landing: la
SPA llama a la API por rutas relativas y no tiene URL base configurable, así que necesita sus
dos entradas —`/` y `/api`— en el mismo host y con Strip Path apagado. Está en el `CLAUDE.md`
porque romperlo da síntomas que parecen fallos de frontend.

**El código va al repositorio como capacidad apagada por defecto** (`DEMO_MODE=false`), la
misma forma que ya tienen `ONBOARDING_ENABLED` o `WORKSPACE_MODE`. Fuera sería un fork que se
pudre en cuanto el núcleo se mueva; dentro, cualquiera que se autohospede puede encenderla.

Y cada variable nueva va a **los dos** composes y a `.env.example`:
`tests/test_compose_env_parity.py` lo pone en rojo, y su docstring explica por qué existe —
una clave añadida en un sitio y no en el otro es *"el fallo más repetido en la historia de
este repositorio"*, y falla en silencio porque `${VAR:-}` resuelve a vacío igual de bien que
a un valor.

Este documento habla de la máquina por su forma —un núcleo, 3.8 GB— y nunca por su nombre:
sin IP, sin hostname, sin nombres de clave.

## 8. Abierto

- Si la creación de curso resulta ser demasiado lenta para una espera en vivo, la salida no
  es acelerarla: es ofrecer el enlace por email cuando termine. Eso convierte la fricción
  descartada en D3 en algo que se pide **después** de dar valor.
- Cuántos renders por sesión antes de considerar que alguien está paseando de más. Se decide
  midiendo, no ahora.

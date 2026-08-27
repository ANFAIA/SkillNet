# Biblioteca administrativa y registro de talento

**Estado:** decisión de producto e implementación inicial
**Ámbito:** organización de cursos y trazabilidad básica de formación
**Fuera de alcance:** personalización, puestos, recomendación de candidatos y grafos de competencias

## Objetivo

SkillNet separa dos preguntas administrativas:

- **Biblioteca:** qué cursos tiene la organización y cómo se encuentran.
- **Talento:** qué cursos tiene asignados o completados cada persona y qué habilidades ha obtenido.

Esta primera versión es deliberadamente registral. No pretende inferir rendimiento laboral ni
decidir si una persona es adecuada para un puesto.

## Biblioteca

Los cursos pueden pertenecer a una carpeta administrativa opcional. Las carpetas son planas en la
primera versión y no controlan permisos, generación, publicación ni matrícula.

**La pantalla se llama «Biblioteca»** en todos los textos que lee un usuario. La ruta
`/admin/contenido`, el fichero `Content.tsx` y el espacio de nombres de mensajes `content.*`
conservan el nombre viejo **a propósito**: renombrarlos es una refactorización de rutas y
namespace que toca marcadores, el tour de onboarding y todas las pantallas que enlazan aquí, y
no le compra nada al usuario. Solo se unificaron las cadenas visibles, que antes llamaban a esto
de seis maneras distintas.

La Biblioteca ofrece:

- búsqueda por título o descripción;
- filtro por carpeta y estado;
- vistas virtuales «Todos» y «Sin organizar»;
- creación, renombrado y eliminación segura de carpetas;
- traslado de un curso entre carpetas;
- publicar, **archivar y desarchivar** un curso;
- asignar una carpeta completa a varias personas, y quitarla.

Una carpeta que contiene cursos no se elimina implícitamente ni elimina sus cursos.

**Archivar oculta un curso; no lo aprueba.** Solo se puede archivar un curso `published` (409 en
cualquier otro caso) y las matrículas **no se tocan**: antes se cerraban todas las abiertas como
`completed` con la fecha de ese momento, así que quien iba a medias acababa con un registro de
curso terminado —y con el crédito— sin que nada guardase qué restaurar. `POST
/courses/{id}/unarchive` devuelve el curso a `published` y a todos exactamente donde estaban;
vuelve a pasar las validaciones de publicar, porque el esquema de un curso archivado sigue
siendo editable y puede haber perdido su último nodo mientras tanto. La superficie del aprendiz
excluye los cursos archivados de «Mis cursos»; **la ficha del admin los sigue mostrando**, que es
justo el punto ahora que el progreso sobrevive.

## Habilidades del curso

Durante la pregeneración del esquema, la misma respuesta rápida que propone sus nodos devuelve entre
dos y seis habilidades observables del curso. Una habilidad se expresa como una acción («Configurar
una taquilla»), no como un tema («Taquilla»).

Las sugerencias son editables y no crean taxonomía hasta que el administrador confirma el curso. Al
persistirlas:

1. se reutiliza una habilidad existente de la organización cuando coincide su nombre normalizado;
2. se crea una nueva cuando no existe;
3. se reemplaza atómicamente la relación `course_skills` del curso.

En esta fase las habilidades pertenecen al curso, no a nodos individuales. `course_nodes.skill_id`
se conserva por compatibilidad, pero no forma parte de este flujo de producto.

## Registro de talento

La finalización del curso concede al usuario sus `course_skills` mediante el mecanismo existente de
`user_skills`. La interfaz inicial puede presentar la posesión de la habilidad sin convertir los
niveles internos `low | medium | high` en una afirmación de medición precisa.

El administrador puede consultar:

- **Personas:** asignados, en curso, completados, progreso y habilidades.
- **Detalle de persona:** cursos con estado/progreso —los archivados incluidos— y habilidades con su
  curso de procedencia cuando el origen sea una finalización. Desde aquí también se **asigna
  formación**: un curso suelto o una carpeta entera (`POST /enrollments` con `course_id` o
  `folder_id`, exactamente uno de los dos). Asignar es **idempotente**: a quien ya la tiene se le
  salta, no se aborta el lote. Quitar solo puede retirar matrículas sin empezar, y el diálogo dice
  con palabras lo que no se puede quitar en vez de fallar en silencio.
- **Cursos:** participantes y estado agregado.
- **Habilidades:** personas y cursos relacionados.

No se añade un segundo sistema de progreso. Talento proyecta inscripciones, progreso dinámico y
`user_skills` existentes.

## Grupos de personas

Un **grupo** es una lista con nombre de personas de la organización, y existe para una sola cosa:
asignar formación a varias personas de una vez sin recorrerlas una a una. Es la contraparte exacta
de la carpeta —una colección plana que agrupa cursos— aplicada al otro lado de la matrícula.

### Qué significa asignar a un grupo

**Un grupo es una audiencia, no una suscripción.** Asignar un curso o una carpeta a un grupo
resuelve el grupo a sus miembros *en ese momento* y crea las matrículas normales, una por persona
y curso. Quien entre en el grupo después **no** hereda lo ya asignado.

La alternativa —matrícula derivada de la pertenencia, sincronizada de forma continua— se descartó
a propósito. Una matrícula en SkillNet es una fila que pertenece a la persona: lleva
`started_at`, `score`, `completed_at`, cierra un curso y respalda un certificado, y solo puede
borrarse mientras siga en `assigned`. Sacar a alguien de un grupo obligaría a decidir qué pasa con
todo eso, y cualquier respuesta es falsa para alguien: borrar la matrícula destruye un curso
terminado, conservarla convierte «el grupo tiene este curso» en mentira. La regla del repo ya
existía (`EnrollmentService.delete` contesta 409 a lo que no esté en `assigned`) y no se duplica
aquí con otro criterio.

Esa decisión sí deja la puerta abierta, y por eso se toma ahora la única que no se puede tomar
después: **la matrícula recuerda de qué grupo salió** (`enrollments.source_group_id`). La
procedencia no se puede rellenar hacia atrás; si algún día se añade sincronización viva, hará
falta saber qué filas nacieron de un grupo, y sin la columna esa información ya se habría perdido.
Borrar un grupo pone la columna a `NULL` y **no toca ninguna matrícula**.

Se marca **por persona, no por encargo**, y eso importa justo para el día que exista esa
sincronización: queda en `NULL` para quien el encargo nombró a mano —el grupo no la puso ahí, y
apuntarlo haría que un futuro «quita lo que asignó este grupo» le retirase un curso que le dio el
administrador— y también para quien está en dos de los grupos del mismo encargo, porque cualquiera
de las dos respuestas sería una moneda al aire escrita como un hecho. Una fila que ya existía
conserva la procedencia que tuviera: la asignación es idempotente, así que el grupo no la creó y
no puede reclamarla.

### Reglas

- Los grupos son **planos** y están dentro de la organización, igual que las carpetas. El nombre es
  único por organización sin distinguir mayúsculas.
- Un grupo puede contener a cualquier miembro de la organización, administradores incluidos.
- **La expansión de un grupo ocurre siempre en el servidor**, en `EnrollmentService.resolve_audience`
  y en ningún otro sitio. El cliente manda `group_ids`, nunca la lista de personas: con la lista
  paginada el navegador no conoce a todos los miembros, y mandarlos chocaría además con el tope de
  100 `user_ids` del contrato.
- **Las personas desactivadas son miembros pero no se matriculan.** Se cuentan aparte
  (`skipped_inactive_count`) y la pantalla lo dice. Un `user_ids` explícito sí matricula a quien
  sea: nombrar a alguien es una instrucción, resolver un grupo es una consulta.
- La audiencia es **aditiva** (`user_ids` ∪ miembros de `group_ids`, deduplicada) mientras que el
  objetivo sigue siendo **excluyente** (`course_id` o `folder_id`, nunca los dos). Unir personas y
  grupos tiene un significado obvio; un curso *y* una carpeta no lo tiene.
- Una asignación sigue siendo idempotente: quien ya tenía el curso se cuenta como
  `skipped_existing_count`, no es un error.
- Se rechaza (422) una orden cuyo tamaño real —personas × cursos— supere
  `MAX_ASSIGNMENT_PAIRS`. Es preferible un error que dice cuánto sobra a una petición que agota el
  tiempo del proxy.

### Superficie

No hay endpoint nuevo de asignación. Los dos que ya existían aprenden `group_ids`, para que no
puedan discrepar sobre qué significa asignar:

| Operación | Endpoint |
|---|---|
| CRUD de grupos | `GET/POST /user-groups`, `PUT/DELETE /user-groups/{id}` |
| Listar grupos (paginado) | `GET /user-groups?search=&offset=&limit=` → `PaginatedResponse[UserGroupRead]` |
| Grupos a los que **no** pertenece alguien | `GET /user-groups?exclude_user_id=` |
| Miembros | `GET /user-groups/{id}/members`, `PUT /user-groups/{id}/members` (`{add, remove}`) |
| Asignar curso o carpeta a grupos | `POST /enrollments` con `group_ids` |
| Asignar una carpeta a grupos | `POST /course-folders/{id}/assign` con `group_ids` |
| Filtrar personas por grupo | `GET /users?group_id=` |

`POST /enrollments` conserva su respuesta antigua —`list[EnrollmentRead]`— **solo** para la forma
antigua exacta (`course_id` + `user_ids`). Cualquier orden que nombre una carpeta o un grupo
contesta `EnrollmentAssignmentResult`, porque solo esa forma puede decir cuántas matrículas se
crearon, cuántas ya existían y cuántas personas inactivas se quedaron fuera.

### Pantalla de Personas

La lista de personas está paginada de verdad (offset/limit sobre `GET /users`, no una primera
página de 50 disfrazada de lista completa) y filtra por texto, rol, estado y grupo. El carril de
grupos a la izquierda es el mismo patrón que el carril de carpetas de la Biblioteca: seleccionar
filtra, y cada grupo lleva sus acciones de miembros, asignación, renombrado y borrado.

Los grupos escalan igual que las personas: `GET /user-groups` devuelve **una página** con su
`total`, y busca por nombre en SQL (`ILIKE`). El carril enseña su buscador cuando hay más grupos de
los que caben, pagina de diez en diez y termina con la misma línea honesta que la lista de al lado
(«1-10 de 33»). Las dos filas virtuales —«Todas las personas» y «Sin grupo»— no se paginan ni se
filtran: son vistas, no grupos, y siguen siempre arriba. El grupo seleccionado tampoco desaparece
al pasar de página o buscar otra cosa: se queda fijo encima de la página, porque un filtro que
sigue estrechando la lista de al lado sin nada en pantalla que lo explique es inexplicable.

En la ficha de la persona, «añadir a un grupo» es un buscador con una lista corta y un botón por
fila, no un `<select>` con todos los grupos dentro. Los grupos a los que ya pertenece los excluye
el servidor (`exclude_user_id`) y no el navegador: una página no es la colección, así que quitarlos
solo de la página que tocó dejaría ofreciendo los de las demás —una acción que no hace nada y se
informa como un éxito.

En el diálogo de asignar una carpeta, la lista de personas se busca y se pagina, y dice en voz
alta cuántas no caben. Los grupos van **primero y con la misma forma de fila** que las personas,
porque asignar a un grupo entero es el caso normal y estaba en lo último de la pantalla, debajo de
una lista paginada. Lo que separa los dos controles no es la forma —eso costaba la lectura obvia—
sino **el encabezado y la línea de ayuda de cada sección**: la casilla de una persona es un
*estado* con dos sentidos («marcada significa que ya tiene la carpeta, y desmarcarla se la quita»)
y la de un grupo solo puede ser una *acción* («marcar un grupo le asigna la carpeta a todos sus
miembros activos, y nunca se la quita a nadie»), porque el diálogo no conoce a los miembros que no
están en la página. Cada casilla apunta a esa línea con `aria-describedby`, así que la distinción
también existe para quien no ve la pantalla. Dos controles con la misma pinta y ningún sitio donde
se diga en qué se diferencian sería justo la mentira que ese diálogo lleva tiempo corrigiendo.

### Lo que un grupo no hace

- No concede permisos ni visibilidad: no es un rol.
- No organiza contenido: eso son las carpetas.
- No anida. `parent_id` se puede añadir después; quitar la anidación una vez prometida, no.
- No sincroniza matrículas con la pertenencia (ver arriba).

## Límites arquitectónicos

- Las carpetas organizan cursos; no organizan ni conceden habilidades.
- Las habilidades describen lo que concede un curso; no modifican la personalización del render.
- Talento es una proyección de datos existentes; no escribe progreso ni mastery.
- Las rutas aplican siempre el ámbito de la organización autenticada.
- La resolución y creación de habilidades vive en el servicio, no en componentes React ni rutas.
- La sustitución de habilidades de un curso es una operación completa y atómica para evitar estados
  parciales.

## Evolución aplazada

Pueden añadirse posteriormente criterios, evidencias, relaciones, vigencia, perfiles de puesto o
consultas explicables. Ninguno de esos conceptos debe anticiparse mediante campos genéricos en esta
versión. Una necesidad futura se modelará como una capa separada sobre el registro actual.

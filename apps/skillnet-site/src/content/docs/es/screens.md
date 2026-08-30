---
title: "Pantallas"
order: 42
section: "extensibility"
---

# Pantallas

> Especificaciones de pantalla para implementación. Cada pantalla define ruta, propósito, secciones, datos, estados y acciones.

---

## Autenticación

### Login

**Ruta:** `/login`
**Rol:** público

Formulario de email + contraseña. Con éxito, el backend crea la cookie de sesión y redirige a `/dashboard` (empleado) o `/admin` (admin).

**Secciones:**
- Logo + nombre de la app
- Campo de email
- Campo de contraseña
- Botón de envío
- Mensaje de error (credenciales incorrectas, cuenta deshabilitada)

**Estados:**
- Por defecto: formulario listo
- Cargando: enviando credenciales
- Error: mensaje inline debajo del formulario

**Acciones:**
- Enviar -> `POST /api/v1/auth/login` -> redirección según rol

---

## Empleado

### Dashboard

**Ruta:** `/empleado`
**Rol:** empleado

La pantalla principal. No es un catálogo de cursos. Es un plan diario: qué hacer hoy, cómo van las cosas, qué se sabe.

**Secciones:**
- **Saludo** — "Hola, Laura" + "Lo que toca hoy"
- **Acciones de hoy** (máximo 3) — repaso urgente (repetición espaciada), curso asignado a continuar, recomendación. Cada una con arranque en un clic
- **Cursos en progreso** — barra de progreso, módulo actual, última actividad con resultado
- **Mapa de skills** — 3 columnas: dominadas / en progreso / pendientes. Se actualiza automáticamente con los resultados de los ejercicios
- **Actividad reciente** — lista cronológica de las últimas acciones (resultados de ejercicios, lecciones completadas)

**Datos:**
- `GET /api/v1/users/me/today` — repasos pendientes, siguiente acción del curso, recomendación
- `GET /api/v1/enrollments?status=in_progress` — cursos activos con progreso
- `GET /api/v1/users/me/skills` — niveles de skill
- `GET /api/v1/users/me/activity` — intentos de ejercicio recientes

**Estados:**
- Vacío: sin cursos asignados -> aviso para esperar al admin o explorar contenido disponible
- Cargando: layout skeleton que respeta la estructura de secciones
- Con datos: dashboard completo

**Acciones:**
- Click en acción de hoy -> navegar al curso/ejercicio
- Click en curso -> `/courses/:id`
- Click en skill -> mostrar detalle (ejercicios que contribuyeron al nivel)

---

### Mis Cursos

**Ruta:** `/empleado/cursos`
**Rol:** empleado

Lista de todos los cursos asignados al empleado.

**Secciones:**
- **Pestañas de filtro** — Todos / En progreso / Completados / Sin empezar
- **Tarjetas de curso** — título, barra de progreso, número de módulos, fecha límite (si existe), última actividad

**Datos:**
- `GET /api/v1/enrollments` — todas las matriculaciones con datos del curso y progreso

**Estados:**
- Vacío: sin cursos asignados
- Con datos: rejilla/lista de tarjetas

**Acciones:**
- Click en curso -> `/courses/:id`
- Filtrar por estado

---

### Vista de Curso

**Ruta:** `/empleado/curso/:id`
**Rol:** empleado

La experiencia del curso. Lista de módulos -> contenido de lección -> ejercicios. Navegación secuencial.

**Secciones:**
- **Cabecera del curso** — título, resultado, progreso, total de módulos
- **Barra lateral/lista de módulos** — módulos con estado de finalización, módulo actual resaltado
- **Contenido de la lección** — contenido de texto de la lección actual
- **Ejercicio** — renderizado por tipo (test, verdadero/falso, rellenar hueco, ordenar pasos, caso práctico, diálogo). Muestra la pregunta, acepta la respuesta, da feedback inmediato con cita de fuente
- **Navegación** — botones anterior/siguiente, indicador de progreso

**Datos:**
- `GET /api/v1/courses/:id` — curso con módulos, lecciones, ejercicios
- `POST /api/v1/exercises/:id/attempt` — enviar respuesta, recibir puntuación + feedback
- `GET /api/v1/enrollments/:id` — progreso actual

**Estados:**
- Cargando: skeleton
- Lección: leyendo contenido
- Ejercicio: respondiendo pregunta
- Feedback: mostrando resultado (correcto/incorrecto + explicación)
- Módulo completado: mensaje de celebración + aviso de siguiente módulo
- Curso completado: puntuación final + certificado + aviso de encuesta de feedback

**Acciones:**
- Navegar entre lecciones/ejercicios
- Enviar respuesta de ejercicio
- Continuar al siguiente módulo
- Al completar el curso -> disparar encuesta de feedback

---

### Chat Tutor

**Ruta:** `/empleado/chat`
**Rol:** empleado

Tutor de IA entrenado con los documentos de la empresa. El empleado hace preguntas y obtiene respuestas fundamentadas en el conocimiento interno con citas de fuente.

**Secciones:**
- **Lista de mensajes** — historial de la conversación, mensajes del usuario alineados a la derecha, del tutor a la izquierda
- **Entrada** — campo de texto + botón de enviar
- **Citas** — cada respuesta del tutor muestra el documento y la sección fuente
- **Prompts sugeridos** — sugerencias contextuales según el curso actual ("¿Quieres saber más sobre X?")

**Datos:**
- `POST /api/v1/chat` — enviar mensaje, recibir respuesta en streaming vía SSE
- La respuesta incluye `citations: [{document, section, page}]`

**Estados:**
- Vacío: mensaje de bienvenida + primeras preguntas sugeridas
- Streaming: respuesta del tutor apareciendo palabra por palabra (SSE)
- Error: mensaje de modelo no disponible

**Acciones:**
- Enviar mensaje
- Click en cita -> abrir documento/sección fuente
- Click en prompt sugerido -> auto-enviar

---

### Mapa de Skills

**Ruta:** `/empleado/skillmap`
**Rol:** empleado

Mapa visual de lo que sabe el empleado.

**Secciones:**
- **Skills por categoría** — agrupadas por categoría de skill (Ventas, Tecnología, etc.)
- **Cada skill** — nombre, nivel (bajo/medio/alto), fuente (checkpoint vs manual), fecha de última evaluación
- **Indicadores de progreso** — representación visual del nivel por skill

**Datos:**
- `GET /api/v1/users/me/skills` — skills con niveles y categorías

**Estados:**
- Vacío: sin skills registradas aún
- Con datos: skills agrupadas por categoría

**Acciones:**
- Click en skill -> mostrar historial (qué ejercicios/checkpoints contribuyeron)

---

### Visor de Manual

**Ruta:** *no implementado* — no hay página de visor de manual ni ruta para ella
**Rol:** empleado

Material de referencia. Los empleados lo consultan cuando necesitan buscar algo.

**Secciones:**
- **Índice** — lista navegable de secciones
- **Contenido** — contenido del manual renderizado por sección
- **Búsqueda** — búsqueda dentro del manual

**Datos:**
- `GET /api/v1/manuals/:id` — contenido del manual

**Estados:**
- Cargando: skeleton
- Con datos: contenido con índice

**Acciones:**
- Navegar por sección (click en el índice)
- Buscar dentro del manual
- Enlace al curso relacionado si existe

---

### Ajustes del Empleado

**Ruta:** `/empleado/ajustes`. El menú de cuenta y la navegación lateral enlazan esta pantalla
como «Preferencias de aprendizaje». El empleado puede cambiar presentación, detalle, tratamiento
de imágenes y accesibilidad sin repetir el onboarding.
**Rol:** empleado

**Secciones:**
- **Perfil** — nombre, email (solo lectura), cambiar contraseña
- **Perfil de aprendizaje** — selección: Estándar / Foco / Rápido. Un clic, sin configuración. Privado (nadie más lo ve)
- **Accesibilidad** — preferencias de presentación opcionales guardadas en `users.accessibility`. Solo ajustes neutros y de comportamiento ("bloques de texto más cortos" y similares): lo que el lector quiere ver en pantalla, nunca un diagnóstico. **No se recogen, almacenan ni ofrecen etiquetas de neurotipo.** Privado, y nunca se envía al LLM — `short_blocks` llega a la generación solo como un `effective_density` menor

**Datos:**
- `GET /api/v1/users/me` — perfil actual
- `PUT /api/v1/users/me` — actualizar perfil, perfil de aprendizaje, accesibilidad

**Estados:**
- Formulario con los valores actuales precargados

**Acciones:**
- Cambiar perfil de aprendizaje -> guardado inmediato
- Alternar flags de accesibilidad -> guardado inmediato
- Cambiar contraseña -> confirmar contraseña actual primero

---

## Admin

### Dashboard de Admin

**Ruta:** `/admin`
**Rol:** admin

Mapa de quién sabe qué. No es un dashboard de métricas. Es un mapa de talento con sugerencias de acción.

**Secciones:**
- **Estadísticas resumidas** — total de empleados, cursos activos, número de gaps críticos, empleados que necesitan atención
- **Matriz de skills** — tabla: filas = skills, columnas = empleados, celdas = nivel (color: verde/amarillo/rojo). Filtrable por categoría, con búsqueda
- **Alertas** — máximo 5, solo accionables: fecha límite próxima con 0% de progreso, fallos consecutivos, certificado por caducar, empleado nuevo sin cursos, decaimiento de skill. Cada alerta trae una acción sugerida
- **Sugerencias de mentoría** — detectadas automáticamente: "Laura sabe X (alto). Carlos necesita X (bajo). ¿Emparejarlos?"

**Datos:**
- `GET /api/v1/skills/matrix` — matriz de skills completa
- `GET /api/v1/alerts` — alertas activas
- `GET /api/v1/skills/mentorship-suggestions` — sugerencias de emparejamiento
- `GET /api/v1/stats` — números resumidos

**Estados:**
- Vacío: sin empleados todavía -> asistente de onboarding (invitar empleados, crear primer curso, asignar)
- Con datos: dashboard completo con matriz, alertas y sugerencias

**Acciones:**
- Click en celda de la matriz -> ver detalle de skill del empleado
- Click en alerta -> navegar a la acción relevante
- Aceptar/descartar sugerencia de mentoría
- Navegar al detalle de empleado, creación de contenido, gestión de contenido

---

### Empleados

**Ruta:** `/admin/empleados`
**Rol:** admin

Listar y gestionar empleados.

**Secciones:**
- **Lista de empleados** — nombre, email, rol, número de cursos activos, % de cobertura de skills, última actividad
- **Búsqueda y filtro** — por nombre, rol
- **Detalle de empleado** (expandible o vista separada) — skills, cursos matriculados, historial de actividad

**Datos:**
- `GET /api/v1/users` — lista de empleados con estadísticas resumidas

**Estados:**
- Vacío: sin empleados -> aviso para invitar
- Con datos: lista/tabla

**Acciones:**
- Click en empleado -> vista de detalle
- Invitar nuevos empleados -> en el mismo sitio de esta pantalla (ver *Invitar Empleados* más abajo; no hay ruta separada)
- Desactivar empleado
- Asignar curso a empleado

---

### Invitar Empleados

**Ruta:** *no implementada como ruta propia* — invitar ocurre dentro de `/admin/empleados`
**Rol:** admin

**Secciones:**
- **Invitación individual** — formulario nombre + email
- **Invitación masiva** — subida de CSV (columnas nombre, email)
- **Invitaciones pendientes** — lista de invitaciones enviadas con su estado

**Datos:**
- `POST /api/v1/users/invite` — enviar invitación
- `POST /api/v1/users/invite/bulk` — subida de CSV
- `GET /api/v1/users/invitations` — invitaciones pendientes

**Acciones:**
- Enviar invitación individual
- Subir CSV
- Reenviar / cancelar invitación pendiente

---

### Gestión de Contenido

**Ruta:** `/admin/contenido`
**Rol:** admin

Vista general de todo el contenido (cursos + manuales).

**Secciones:**
- **Lista de contenido** — título, tipo (curso/manual), estado (borrador/publicado/archivado), fecha de creación, documento fuente
- **Filtro** — por tipo, por estado
- Botón **Crear nuevo** -> `/admin/crear-curso`
- Botón **Esquema** por curso -> `/admin/curso/:id/ajustes`

**Datos:**
- `GET /api/v1/courses` — todos los cursos
- `GET /api/v1/manuals` — todos los manuales

**Acciones:**
- Click en contenido -> editar/ver
- Crear nuevo -> flujo de creación de contenido
- Archivar / publicar / despublicar

---

### Flujo de Creación de Contenido

Flujo multipaso para crear un curso o manual.

**Ruta:** `/admin/crear-curso` — **una sola ruta, no cinco.** Los pasos de abajo son estado interno de
`CreateCourse.tsx` gobernado por un `StepIndicator`, así que no hay URL por paso ni deep link a
un paso concreto. Cuando el flag v2 lo permite, el paso 1 gana una ruta opcional de "definir el
esquema"; la ruta v1 sigue disponible.

**Paso 1 — Selección de tipo**

Elegir salida: curso + manual, o solo manual. Subir documento fuente (PDF) o empezar desde cero.

**Paso 2 — Entrada**

Si se subió un documento: mostrar el estado del procesamiento. Si es desde cero: campos de título + tema + resultado.

**Paso 3 — Vista previa**

Vista previa del contenido generado. Módulos, lecciones y ejercicios listados. El admin revisa.

**Paso 4 — Edición**

El admin puede editar el contenido generado: reordenar módulos, editar el texto de la lección, modificar ejercicios, eliminar/añadir contenido.

**Paso 5 — Publicación**

Definir metadatos: título, descripción, resultado, skills que enseña, asignar a empleados (opcional). Publicar.

**Datos:**
- `POST /api/v1/documents` — subir documento fuente
- `POST /api/v1/documents/:id/process` — disparar la ingesta
- `POST /api/v1/courses/:id/generate` — disparar la generación (diferido)
- `POST /api/v1/courses/:id/publish` — publicar
- `PUT /api/v1/courses/:id` — editar contenido

---

### Chat de Admin

**Ruta:** `/admin/chat`
**Rol:** admin

Asistente de IA para tareas de admin. Distinto del tutor — este ayuda a gestionar la plataforma.

**Secciones:**
- Mismo layout que el Chat Tutor
- Contexto distinto: conoce empleados, cursos, skills, contenido

**Datos:**
- `POST /api/v1/chat/admin` — enviar mensaje, respuesta SSE

**Acciones:**
- Igual que el Chat Tutor pero con respuestas con alcance de admin

---

### Ajustes de Admin

**Ruta:** `/admin/ajustes`
**Rol:** admin

**Secciones:**
- **Empresa** — nombre, logo
- **Taxonomía de skills** — gestionar categorías y skills (añadir, renombrar, reordenar, eliminar)
- **Configuración del LLM** — endpoint de la API, clave de API, nombre del modelo (entrada enmascarada para la clave)
- **Valores por defecto de gestión de usuarios** — autorregistro on/off, perfil de aprendizaje por defecto

**Datos:**
- `GET /api/v1/organizations/me` — ajustes actuales de la org
- `PUT /api/v1/organizations/me` — actualizar ajustes
- `GET /api/v1/skills/categories` — taxonomía
- `POST/PUT/DELETE /api/v1/skills/categories` y `/api/v1/skills` — gestionar taxonomía

**Acciones:**
- Actualizar información de la empresa
- Añadir/editar/eliminar categorías y skills
- Configurar proveedor de LLM
- Alternar autorregistro

---

## Compartido

### Layout

Todas las pantallas autenticadas comparten:

- **Barra lateral** — enlaces de navegación agrupados por rol. Empleado: Dashboard, Mis Cursos, Skills, Chat, Manuales, Ajustes. Admin: Dashboard, Empleados, Contenido, Chat, Ajustes. Colapsable
- **Cabecera** — título de la página actual, nombre de usuario + avatar, indicador de rol, cerrar sesión
- **Contenido principal** — el contenido de la pantalla

La barra lateral se colapsa a iconos en móvil. La cabecera permanece fija.

---

## Resumen de Rutas

**Las rutas están en español.** El código es la fuente de verdad aquí (`apps/skillnet-web/src/App.tsx`)
y las rutas en inglés que este documento solía listar nunca existieron. Decidido en
`v2-dynamic-courses.md` §14.2 #8: seguir al código; cambiar a inglés sería un renombrado mecánico
de `App.tsx` y los `Link`, sin efecto en la API.

| Ruta | Pantalla | Rol |
|-------|--------|------|
| `/` | Redirección según rol | público |
| `/login` | Login | público |
| `/setup` | Asistente de puesta en marcha | público |
| `/onboarding` | Asistente de perfil del aprendiz (v2) | empleado |
| `/empleado/ajustes` | Preferencias de aprendizaje y accesibilidad | empleado |
| `/empleado` | Dashboard del Empleado | empleado |
| `/empleado/cursos` | Mis Cursos | empleado |
| `/empleado/curso/:id` | Vista de Curso | empleado |
| `/empleado/curso/:id/nodo/:nodeId` | Vista de Nodo (curso dinámico v2) | empleado |
| `/empleado/skillmap` | Mapa de Skills | empleado |
| `/empleado/chat` | Chat Tutor | empleado |
| `/admin` | Dashboard de Admin | admin |
| `/admin/demo` | Lección escaparate | admin |
| `/admin/empleados` | Empleados (invitar vive dentro) | admin |
| `/admin/talento` | Talento | admin |
| `/admin/contenido` | Gestión de Contenido | admin |
| `/admin/crear-curso` | Creación de Contenido (los 5 pasos, una ruta) | admin |
| `/admin/curso/:id` | Vista Previa de Curso | admin |
| `/admin/curso/:id/ajustes` | Esquema de Curso (v2) | admin |
| `/admin/curso/:id/esquema` | Redirige a `/admin/curso/:id/ajustes` | admin |
| `/admin/curso/:id/estudio` | Redirige a `/admin/probar-curso/:id` | admin |
| `/admin/probar-curso/:id` | Vista de Curso — la prueba del admin | admin |
| `/admin/probar-curso/:id/nodo/:nodeId` | Vista de Nodo — la prueba del admin | admin |
| `/admin/chat` | Chat de Admin | admin |
| `/admin/ajustes` | Ajustes de Admin | admin |
| `/dev/motion` | Demo de animación (solo desarrollo) | público |
| `/dev/didact` | Laboratorio de componentes Didact (solo desarrollo) | admin |

Tres de estas pertenecen a v2: `/onboarding`, `/empleado/curso/:id/nodo/:nodeId` y
`/admin/curso/:id/ajustes`. Siempre están montadas; que muestren contenido v2 depende del
curso, no de ningún ajuste global — un curso que no es `dynamic`+`validated` se sirve en
su formato v1 (`resolve_delivery`, ver `v2-dynamic-courses.md` §10).

**Un curso se lee desde dos de estas rutas, no desde una.** `/admin/probar-curso/:id` monta
los mismos componentes que usa el aprendiz — `CourseView` y `NodeView` — dentro de
`AdminLayout`, para que el admin pruebe el curso sin salir de su contexto. Así que todo lo que
vive dentro de un curso tiene que funcionar bajo los dos prefijos, y nada de lo que hay dentro
debe reconstruir la URL del curso recortando la actual: `src/lib/courseRoutes.ts` es el dueño de
esa forma y la contesta a cualquier profundidad. Queda escrito porque el código hacía ese
recorte en cuatro sitios, y la copia del mapa del curso producía `/…/curso/A/nodo/B/nodo/C` al
abrirse desde dentro de una lección — no casaba ninguna ruta, el comodín mandaba al aprendiz a
su inicio, y pulsar una lección parecía pulsar Inicio.

No existe una página de ajustes de empleado ni una página de visor de manual; ambas están
especificadas arriba pero no construidas.

### Puntos de entrada de v2

Navegación hacia las superficies v2, todo con gating para que nada aparezca con el flag apagado:

| Dónde | Qué | Puerta |
|---|---|---|
| `pages/admin/Content.tsx` | Enlace "Esquema" por curso | flag es `shadow` u `on` |
| `pages/admin/CoursePreview.tsx` | Enlace "Esquema" | flag es `shadow` u `on` |
| `pages/admin/CourseSchema.tsx` | Enlace de vuelta "← Volver al curso" | siempre (está dentro de la pantalla) |
| `pages/employee/MyCourses.tsx` | Badge "Por nodos" en cursos dinámicos | `enrollment.delivery_mode` |
| `pages/employee/Dashboard.tsx` | Badge "Por nodos" en cursos dinámicos | `enrollment.delivery_mode` |
| `components/layout/Header.tsx` | Elemento "Preferencias de aprendizaje" en el menú de cuenta, abre `/empleado/ajustes` | empleado |

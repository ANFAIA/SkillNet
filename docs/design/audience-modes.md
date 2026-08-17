# Modos de audiencia: Organization e Individual

> **Estado: implementado (primera vertical).** El modo es una capacidad estable del
> despliegue, `organizations.workspace_mode` (migración 0017), fijada al crear la
> organización desde `WORKSPACE_MODE` (por defecto `organization`) y nunca inferida
> del número de usuarios. El documento sigue describiendo la dirección de producto;
> lo ya construido se resume abajo en «Estado de implementación». No implica crear
> una web comercial, un SaaS multi-tenant ni dos productos distintos.

## Decisión

SkillNet tendrá un único núcleo de producto y dos modos de uso:

| Modo interno | Etiqueta de producto | Para quién | Propietario del espacio |
|---|---|---|---|
| `organization` | **Company** / **Organization** | Empresas, equipos, clases, academias, asociaciones y otros grupos | Una persona administradora gestiona contenido y participantes |
| `individual` | **Individual** | Una persona que instala y utiliza SkillNet para sí misma | La misma persona administra su contenido y aprende |

No se crea un modo separado para `class`. Una clase es un caso de uso de
`organization`: tiene una persona responsable, un conjunto de participantes,
contenido compartido y seguimiento colectivo. Las diferencias entre una empresa y
una clase pertenecen al lenguaje, las plantillas y la configuración, no a la
arquitectura principal.

Tampoco se llamará `user` al segundo modo. Todas las personas del sistema son
usuarios; usar ese término para un tipo de instalación haría ambiguos el código, la
documentación y el marketing.

## Qué permanece común

Los dos modos comparten el flujo que constituye el producto:

1. incorporar documentos propios;
2. convertirlos en cursos y material de consulta;
3. aprender mediante experiencias adaptadas;
4. conservar progreso, preferencias y memoria personal;
5. regenerar o actualizar el aprendizaje cuando cambian las fuentes.

La generación, el runtime adaptativo, los ejercicios, la tutoría, la trazabilidad
de fuentes y la persistencia del perfil no deben bifurcarse por modo. Las
diferencias se resuelven mediante capacidades visibles y permisos, no manteniendo
dos aplicaciones.

## Experiencia por modo

### Organization

Mantiene el producto actual y sus roles principales:

- una persona administradora sube documentos y revisa contenido generado;
- puede invitar participantes, asignar cursos y consultar progreso colectivo;
- dispone de biblioteca compartida, habilidades, talento e informes de equipo;
- cada participante conserva su progreso y recibe una experiencia personalizada;
- la organización controla la configuración del despliegue y sus datos.

La etiqueta concreta puede cambiar según la vertical (`Empresa`, `Clase`,
`Academia` o `Equipo`) sin alterar el modo interno.

### Individual

La persona es simultáneamente propietaria del espacio y alumna:

- sube sus propios documentos;
- crea, revisa y publica cursos para sí misma;
- configura el modelo y el despliegue como lo haría una persona administradora;
- conserva progreso, preferencias, historial y personalización entre cursos;
- no ve gestión de empleados, talento, asignaciones colectivas ni informes de
  organización;
- no necesita crear usuarios secundarios para completar su propio contenido.

`Individual` no es una edición desechable o sin memoria. La personalización y la
persistencia son precisamente parte de su valor: SkillNet aprende cómo estudia esa
persona y utiliza esa información en sus cursos posteriores.

## Modelo técnico recomendado

La ampliación no requiere eliminar `organizations` ni introducir multi-tenancy.
Cada despliegue continúa teniendo una sola fila de organización:

- en modo `organization`, representa a la empresa, clase o equipo;
- en modo `individual`, representa el espacio personal del propietario.

Cuando se implemente, el modo puede almacenarse como una capacidad estable del
despliegue, por ejemplo `workspace_mode = organization | individual`. No debe
inferirse repetidamente a partir del número de usuarios.

El frontend puede derivar de ese valor la navegación y las funciones disponibles.
La API debe seguir aplicando permisos en el servidor: ocultar una sección no es un
mecanismo de autorización.

La primera configuración debería pedir únicamente el modo de uso y los datos
necesarios para crear al propietario. Cambiar de `individual` a `organization`
puede admitirse como una ampliación no destructiva; el camino inverso exige tratar
participantes, asignaciones y datos colectivos y por tanto no debe asumirse
automático.

## Producto horizontal y marketing vertical

SkillNet sigue siendo un producto horizontal: convierte conocimiento propio en
aprendizaje adaptativo. La segmentación comercial no necesita convertirse en
segmentación técnica.

Puede haber varias landings o narrativas verticales sobre el mismo producto:

| Página o campaña | Problema que cuenta | Modo de producto |
|---|---|---|
| Empresas | Onboarding, procedimientos y conocimiento interno | `organization` |
| Academias o clases | Material docente propio y seguimiento del alumnado | `organization` |
| Consultoras | Entrega de formación basada en documentación del cliente | `organization` |
| Individual | Estudiar documentos propios con memoria y adaptación | `individual` |

Estas páginas pueden usar ejemplos, imágenes, testimonios y llamadas a la acción
distintos. No deben prometer funcionalidades exclusivas que obliguen a crear forks
del producto. Una vertical es una puerta de entrada y una prioridad de marketing,
no una edición independiente.

## Storytelling común

La historia central debe funcionar en ambos modos y partir del conocimiento, no
del organigrama:

> SkillNet transforma los documentos que ya tienes en aprendizaje que se adapta a
> cada persona.

Después se concreta por audiencia:

- **Company:** el conocimiento de tu organización se convierte en formación para
  cada miembro del equipo.
- **Individual:** tus documentos se convierten en cursos que recuerdan cómo
  aprendes.

Así se conserva una marca única y se evita que la ampliación diluya el mercado
inicial. El marketing puede seguir concentrando presupuesto y mensajes en pymes,
incluso aunque el software descargable cubra más casos de uso.

## Fuera de alcance de esta decisión

- ofrecer SkillNet como SaaS alojado o multi-tenant;
- crear una aplicación distinta para cada vertical;
- implementar ahora una web de marketing;
- renombrar inmediatamente roles, tablas o rutas existentes;
- diseñar facturación, licencias o precios por modo;
- convertir `class` en una entidad raíz separada.

## Criterios para una implementación futura

La ampliación estará bien resuelta si:

1. una instalación individual puede completar el ciclo entero sin encontrar
   conceptos de RR. HH. o gestión de plantilla;
2. una instalación de organización conserva todas las funciones actuales;
3. el contenido, el progreso y la personalización utilizan los mismos servicios en
   ambos modos;
4. añadir una nueva vertical de marketing no requiere modificar el modelo de
   dominio;
5. una persona puede ampliar su espacio individual a organización sin perder sus
   cursos ni su historial;
6. el aislamiento y la propiedad de los datos siguen siendo los de un despliegue
   self-hosted de una sola organización.

## Frontera de nuevas funciones

Audio en el chat, conversaciones en vivo, mascota y podcasts pueden reutilizarse en ambos
modos. Esta decisión no añade por sí sola más funciones al producto empresarial. La nota
de dirección está en [conversational-modalities.md](conversational-modalities.md).

## Estado de implementación

Primera vertical construida (mantiene `organization` intacto por defecto):

- **Datos.** `organizations.workspace_mode` (enum `workspace_mode`, migración 0017),
  default `organization`. Sin multi-tenancy: una fila por despliegue, como antes.
- **Arranque.** `bootstrap.ensure_organization` lee `WORKSPACE_MODE` (env, default
  `organization`) sólo al crear la organización; los despliegues existentes conservan
  su valor.
- **API.** El modo viaja al cliente en `GET /auth/me` (`workspace_mode`) y en
  `GET /settings`. Las superficies colectivas —empleados (alta/lista/reset), talento,
  estadísticas, asignación de cursos y catálogo de skills— pasan por la dependencia
  `require_organization_workspace`, que responde **404** en `individual`: ahí esos
  conceptos no existen. La autorización sigue en el servidor; ocultar en la SPA es UX.
- **Frontend.** La navegación se deriva del modo (`useWorkspaceMode`). En `individual`
  el propietario es un `admin` que además aprende: la barra lateral omite Empleados y
  Talento, «Contenido» se presenta como «Mis cursos», y el panel de empresa se
  sustituye por un inicio personal. El propietario pasa una vez por el onboarding del
  aprendiz para tener perfil y personalización.
- **Roles.** Sin rol nuevo: `individual` reutiliza `admin` como propietario-alumno.
- **Seed.** `src.seed_demo_individual` levanta un espacio personal mínimo (un
  propietario, un documento, un curso; sin empleados ni matrículas) reutilizando los
  bloques de `seed_demo_v2`.

Pendiente (fases siguientes): fijar el modo desde un wizard de primer arranque (hoy es
env), pulir el onboarding del propietario, y la ampliación no destructiva
`individual → organization`.

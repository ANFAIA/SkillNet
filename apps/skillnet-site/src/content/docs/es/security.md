---
title: "Seguridad"
order: 9
section: "core"
---

## 7. Seguridad y control de acceso

> **Estado: v1.** Arquitectura de seguridad completa para el MVP de SkillNet (autoalojado, una instancia por empresa). Cubre autenticacion, autorizacion, seguridad de agentes, cumplimiento del RGPD, endurecimiento de la API y gestion de secretos.

---

### 7.1 Flujo de autenticacion

SkillNet usa **autenticacion basada en sesion** mediante fastapi-users con `CookieTransport`. Sin JWT en cookies, sin gestion de tokens en el codigo del frontend. El navegador envia una cookie httpOnly automaticamente en cada peticion.

#### 7.1.1 Flujo de inicio de sesion

```
1. Employee opens https://formacion.empresa.com/login
2. Submits email + password via POST /api/v1/auth/login
3. Backend verifies credentials:
   a. Look up user by (org_id, email)
   b. Verify password hash with bcrypt (passlib[bcrypt])
   c. Check user.is_active == true
4. If valid: create session row in PostgreSQL
5. Set response cookie:
   - Name: skillnet_session
   - Value: session token (opaque, 64-byte hex via secrets.token_hex)
   - HttpOnly: true (JavaScript cannot read it)
   - Secure: true (HTTPS only, enforced in production)
   - SameSite: Lax (blocks cross-origin POST, allows navigational GET)
   - Max-Age: 604800 (7 days)
   - Path: /
   - Domain: omitted (defaults to current host, no subdomain leakage)
6. Return 200 with user profile (id, email, full_name, role)
7. Frontend redirects to role-appropriate screen:
   - admin  -> /admin/dashboard
   - employee -> /dashboard
```

#### 7.1.2 Almacenamiento de sesiones

Las sesiones viven en PostgreSQL, no en memoria. Esto sobrevive a reinicios del servidor y permite despliegues multiproceso.

```sql
CREATE TABLE user_sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE,
    ip_address  inet,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    last_used   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_sessions_token ON user_sessions(token_hash);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at);
```

**El token de sesion se hashea antes de almacenarlo** (SHA-256). Si la base de datos se ve comprometida, los tokens en crudo no quedan expuestos. La cookie guarda el token en crudo; la base de datos solo guarda su hash.

En cada peticion:
1. Leer la cookie `skillnet_session`.
2. Hashear el token con SHA-256.
3. Buscar en `user_sessions` por `token_hash`.
4. Comprobar `expires_at > now()`.
5. Hacer join con la tabla `users` para obtener `user_id`, `role`, `org_id`, `is_active`.
6. Si es valida y esta activa: actualizar `last_used`, adjuntar el usuario al estado de la peticion.
7. Si es invalida/expirada/inactiva: devolver 401 y borrar la cookie.

#### 7.1.3 Invalidacion de sesiones

| Disparador | Que ocurre |
|---------|-------------|
| **Cierre de sesion** | `DELETE FROM user_sessions WHERE token_hash = $1`. Se borra la cookie. |
| **Cambio de contrasena** | `DELETE FROM user_sessions WHERE user_id = $1 AND id != $current_session`. Se eliminan el resto de sesiones de ese usuario. La sesion actual se mantiene (el usuario acaba de cambiar su propia contrasena). |
| **El admin desactiva a un empleado** | `UPDATE users SET is_active = false WHERE id = $1`. La siguiente peticion con cualquiera de las sesiones de ese usuario pasa por la comprobacion de `is_active` y devuelve 401. Las sesiones se recogen (garbage-collected) mas tarde. |
| **Expiracion de sesion** | Un cron diario ejecuta `DELETE FROM user_sessions WHERE expires_at < now()`. |

#### 7.1.4 Proteccion CSRF

SameSite=Lax bloquea las peticiones POST entre origenes distintos procedentes de otros sitios. Esta es la defensa principal frente a CSRF. Ademas:

- **Patron de doble cookie (double-submit cookie)** para operaciones que cambian estado. Al iniciar sesion, el backend establece una segunda cookie no httpOnly (`skillnet_csrf`) con un token aleatorio. El frontend lee esta cookie y la envia como cabecera `X-CSRF-Token` en cada peticion POST/PUT/DELETE. El backend verifica que el valor de la cabecera coincide con el valor de la cookie.
- **Por que ambos?** SameSite=Lax permite GET entre origenes. El token CSRF garantiza que incluso los cambios de estado basados en GET (que SkillNet evita por convencion, pero es defensa en profundidad) queden protegidos. SameSite=Lax tambien tiene casos limite de soporte reducido en navegadores muy antiguos.

```python
# FastAPI middleware (simplified)
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        cookie_token = request.cookies.get("skillnet_csrf")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or cookie_token != header_token:
            return JSONResponse(status_code=403, content={"detail": "CSRF token mismatch"})
    return await call_next(request)
```

#### 7.1.5 Hashing de contrasenas

- **Algoritmo:** bcrypt via passlib (el predeterminado en fastapi-users).
- **Factor de trabajo:** 12 rondas (por defecto). Esto produce un tiempo de hash de ~250ms en hardware moderno, suficientemente rapido para el login pero suficientemente lento para resistir fuerza bruta.
- **El backend no impone reglas de contrasena** mas alla de un minimo de 8 caracteres. El frontend puede sugerir complejidad, pero el backend no rechaza contrasenas por su composicion. Motivo: la investigacion muestra que la longitud importa mas que las reglas de complejidad, y esta es una herramienta interna de empresa donde el admin crea las cuentas.

---

### 7.2 Modelo de autorizacion

Dos roles: `admin` y `employee`. Sin roles intermedios (el antiguo rol "jefe/responsable" se elimino por simplicidad). El admin puede delegar asignando cursos y viendo datos; no necesita un rol aparte para eso.

#### 7.2.1 Matriz de permisos por rol

| Recurso | Admin | Empleado |
|----------|-------|----------|
| **Perfil propio** (ver/editar) | Si | Si |
| **Progreso/skills propios** (ver) | Si | Si |
| **Flags de accesibilidad propios** (ver/editar) | Si | Si |
| **Perfiles de otros empleados** (ver) | Si, todos los del org | No |
| **Progreso/skills de otros empleados** (ver) | Si, todos los del org | No |
| **Flags de accesibilidad de otros empleados** | **No** (privado) | No |
| **Contenido de cursos** (ver) | Todo | Solo cursos matriculados |
| **Cursos** (crear/editar/publicar) | Si | No |
| **Documentos** (subir/gestionar) | Si | No |
| **Usuarios** (crear/desactivar/eliminar) | Si | No |
| **Ajustes del org** (editar) | Si | No |
| **Taxonomia de skills** (gestionar) | Si | No |
| **Matriculas** (asignar/gestionar) | Si | No |
| **Exportar datos de empleado** | Si | Solo sus propios datos |
| **Chat del tutor** | Si (contexto admin) | Si (contexto empleado) |

**Regla critica: los flags de accesibilidad NUNCA son visibles para el admin.** La columna `users.accessibility` es privada. Ningun endpoint de la API la devuelve a nadie que no sea el propietario. El panel de admin muestra los perfiles de empleado sin el campo de accesibilidad. Esto se impone a nivel de serializador (modelos de respuesta Pydantic distintos para "yo mismo" frente a "admin viendo a un empleado").

#### 7.2.2 Guardas a nivel de ruta (dependencias de FastAPI)

Tres dependencias reutilizables que se componen:

```python
from fastapi import Depends, HTTPException, status

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Extract and validate session from cookie. Returns User or raises 401."""
    token = request.cookies.get("skillnet_session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > func.now()
        )
    )
    session = session.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account deactivated")
    # Update last_used
    session.last_used = func.now()
    await db.commit()
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Returns User if admin, raises 403 otherwise."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_same_org(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Path(...)
) -> User:
    """Ensures user belongs to the requested org. Prevents cross-org access."""
    if user.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return user
```

Uso en las rutas:

```python
# Employee sees own dashboard
@router.get("/api/v1/dashboard")
async def get_dashboard(user: User = Depends(get_current_user)):
    ...

# Admin-only: list all employees
@router.get("/api/v1/admin/users")
async def list_users(user: User = Depends(require_admin)):
    ...

# Admin-only: create a course
@router.post("/api/v1/courses")
async def create_course(user: User = Depends(require_admin)):
    ...
```

#### 7.2.3 Segmentacion a nivel de datos

Toda consulta a la base de datos esta acotada. No hay consultas sin acotar en la aplicacion.

**Las consultas de empleado siempre filtran por `user_id`:**

```python
# Employee sees ONLY their own skills
async def get_my_skills(user_id: uuid.UUID, db: AsyncSession):
    return await db.execute(
        select(UserSkill).where(UserSkill.user_id == user_id)
    )

# Employee sees ONLY their own exercise attempts
async def get_my_attempts(user_id: uuid.UUID, db: AsyncSession):
    return await db.execute(
        select(ExerciseAttempt).where(ExerciseAttempt.user_id == user_id)
    )

# Employee sees ONLY courses they're enrolled in
async def get_my_courses(user_id: uuid.UUID, db: AsyncSession):
    return await db.execute(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user_id)
    )
```

**Las consultas de admin filtran por `org_id`:**

```python
# Admin sees all employees in their org (never cross-org)
async def list_org_users(org_id: uuid.UUID, db: AsyncSession):
    return await db.execute(
        select(User).where(User.org_id == org_id)
    )

# Admin sees all skills across org
async def get_skills_matrix(org_id: uuid.UUID, db: AsyncSession):
    return await db.execute(
        select(User.full_name, Skill.name, UserSkill.level)
        .join(User, User.id == UserSkill.user_id)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .where(User.org_id == org_id)
    )
```

**Los modelos de respuesta Pydantic imponen la visibilidad de campos:**

```python
# What an employee sees about themselves
class UserSelfResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    learning_profile: str
    accessibility: dict  # Only returned to the user themselves

# What an admin sees about an employee
class UserAdminResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    hired_at: date | None
    # NO accessibility field — admin never sees this

# What one employee would see about another (if any endpoint existed — it doesn't)
# This model does not exist. Employees cannot see other employees' profiles.
```

---

### 7.3 Seguridad de agentes (modelo de compartimentos)

Los agentes de SkillNet son maquinas de estados de LangGraph. Acceden a datos de usuario y al conocimiento organizacional. El modelo de seguridad garantiza que un agente SOLO pueda acceder a los datos que necesita para su tarea especifica, y SOLO pueda emitir informacion que el usuario solicitante este autorizado a ver.

El principio: **controlar en el arranque (que puede ver el agente) y en la frontera (que puede emitir), nunca dentro del agente.**

#### 7.3.1 Definicion de compartimento

Un compartimento es un ambito con nombre de acceso a datos. Los compartimentos no son jerarquicos: tener acceso a uno no implica acceso a ningun otro.

Para el MVP, los compartimentos se corresponden directamente con tipos de datos:

| Compartimento | Que incluye |
|-------------|-----------------|
| `user_profile:{user_id}` | Nombre, email, perfil de aprendizaje de un usuario concreto |
| `user_progress:{user_id}` | Matriculas, intentos de ejercicios, estado de repeticion espaciada de un usuario |
| `user_skills:{user_id}` | Niveles de skills de un usuario |
| `course_content:{course_id}` | Lecciones, ejercicios, estructura de modulos de un curso |
| `org_documents` | Fragmentos de documentos disponibles para recuperacion RAG (acotado por org_id) |
| `org_skills_matrix` | Datos agregados de skills de todos los empleados (solo admin) |

Los compartimentos NO se almacenan como filas en la base de datos. Son una convencion de nombres que usa el proceso de arranque del agente para determinar que consultas ejecutar.

#### 7.3.2 Filtrado en el arranque

Cuando se invoca un agente para una tarea, el orquestador construye un **mandato** antes de arrancar el agente:

```python
@dataclass(frozen=True)
class AgentMandate:
    """Immutable specification of what an agent is authorized to do."""
    principal: uuid.UUID          # Who requested this (user_id)
    principal_role: str           # "admin" or "employee"
    agent_type: str               # "tutor", "content_generator", "evaluator"
    objective: str                # Human-readable task description
    compartments: frozenset[str]  # Immutable set of allowed data compartments
    max_output_tokens: int        # Hard limit on response size
    allowed_tools: frozenset[str] # Which LangGraph tools the agent can call
    created_at: datetime          # When the mandate was created
    expires_at: datetime          # When the mandate expires (max 1 hour)
```

**El mandato es inmutable (frozen)** (dataclass con `frozen=True` y frozensets). El agente no puede modificar sus propios permisos en tiempo de ejecucion.

**Ejemplo: agente tutor sirviendo al Empleado A durante el curso X:**

```python
mandate = AgentMandate(
    principal=employee_a_id,
    principal_role="employee",
    agent_type="tutor",
    objective="Answer question about course module",
    compartments=frozenset({
        f"user_profile:{employee_a_id}",
        f"user_progress:{employee_a_id}",
        f"course_content:{course_x_id}",
    }),
    max_output_tokens=2000,
    allowed_tools=frozenset({"search_course_content", "get_lesson"}),
    created_at=now,
    expires_at=now + timedelta(hours=1),
)
```

**Lo que este mandato EXCLUYE:**
- El progreso del Empleado B (no hay compartimento `user_progress:{employee_b_id}`)
- El grafo de skills del Empleado A (no hay `user_skills:{employee_a_id}` — el tutor no lo necesita)
- Otros cursos (no hay `course_content:{course_y_id}`)
- Documentos del org no relacionados con este curso
- Datos exclusivos de admin (matriz de skills, perfiles de otros empleados)

El **cargador de datos** lee los compartimentos del mandato y ejecuta UNICAMENTE las consultas que encajan. Los datos fuera de los compartimentos nunca se recuperan de la base de datos, asi que nunca entran en la ventana de contexto del agente.

```python
async def load_agent_context(mandate: AgentMandate, db: AsyncSession) -> dict:
    """Load only data authorized by the mandate. Nothing else enters memory."""
    context = {}

    for compartment in mandate.compartments:
        ctype, cid = compartment.split(":", 1) if ":" in compartment else (compartment, None)

        if ctype == "user_profile":
            user = await db.get(User, uuid.UUID(cid))
            # Return ONLY non-sensitive fields — never accessibility
            context["user_profile"] = {
                "name": user.full_name,
                "learning_profile": user.learning_profile,
            }

        elif ctype == "user_progress":
            enrollments = await get_user_enrollments(uuid.UUID(cid), db)
            attempts = await get_recent_attempts(uuid.UUID(cid), db, limit=20)
            context["user_progress"] = {
                "enrollments": enrollments,
                "recent_attempts": attempts,
            }

        elif ctype == "course_content":
            course = await get_course_with_modules(uuid.UUID(cid), db)
            context["course_content"] = course

        elif ctype == "org_documents":
            # RAG chunks scoped by org_id — the org_id comes from the principal's user record
            context["rag_available"] = True

        # Unknown compartment types are silently ignored (fail-closed)

    return context
```

#### 7.3.3 Aplicacion de frontera

Despues de que el agente genera una respuesta, un **escaner de frontera** inspecciona la salida antes de que llegue al usuario. Esta es una capa dura y determinista, no una instruccion de prompt.

```python
async def enforce_boundary(
    output: str,
    mandate: AgentMandate,
    db: AsyncSession
) -> str:
    """Scan agent output and strip or block unauthorized content."""

    # 1. Check output length
    if len(output) > mandate.max_output_tokens * 4:  # rough char estimate
        output = output[:mandate.max_output_tokens * 4]
        output += "\n\n[Response truncated: exceeded maximum length]"

    # 2. Check for other users' data leaking
    #    (If the agent somehow hallucinates or recalls from prior context)
    if mandate.principal_role == "employee":
        # Scan for names/emails of other users in the org
        other_users = await get_org_users_except(mandate.principal, db)
        for user in other_users:
            if user.full_name.lower() in output.lower():
                output = output.replace(user.full_name, "[REDACTED]")
            if user.email.lower() in output.lower():
                output = output.replace(user.email, "[REDACTED]")

    # 3. Check for accessibility data (must NEVER appear in agent output)
    accessibility_terms = ["TEA", "TDAH", "dislexia", "neurodiverg"]
    for term in accessibility_terms:
        if term.lower() in output.lower():
            # Hard block — do not return this response
            return (
                "I encountered an error generating this response. "
                "Please try again or rephrase your question."
            )

    return output
```

**Dos capas de aplicacion de frontera:**

1. **Escaner duro (deterministico):** el codigo anterior. Se ejecuta en cada respuesta. No se puede saltar. Comprueba fugas de PII, datos de accesibilidad, tamano de la salida, patrones conocidos.

2. **Agente de aduanas suave (opcional, post-MVP):** una llamada a un LLM separado y barato que revisa la respuesta contra el mandato. "¿Contiene esta respuesta informacion sobre usuarios distintos del solicitante?" Esto detecta fugas semanticas que el emparejamiento de patrones no capta. Es consultivo: si hay duda, marca para revision humana en lugar de bloquear.

#### 7.3.4 Prevencion de fuga de datos entre usuarios

**Problema:** si dos usuarios hacen preguntas al tutor de forma secuencial, un estado de agente compartido podria filtrar las respuestas de ejercicios del Usuario A al Usuario B.

**Solucion: los agentes carecen de estado entre usuarios.** Cada invocacion de agente recibe:
- Un estado de LangGraph nuevo (sin arrastre entre peticiones de distintos usuarios)
- Contexto cargado exclusivamente desde los compartimentos del mandato
- Ninguna cache en memoria compartida entre sesiones de usuario

```python
# Each request creates a new graph execution — no shared state
async def handle_tutor_question(user: User, question: str, course_id: uuid.UUID):
    mandate = create_tutor_mandate(user, course_id)
    context = await load_agent_context(mandate, db)

    # Fresh graph per invocation — no prior state from other users
    graph = build_tutor_graph()
    initial_state = {
        "messages": [HumanMessage(content=question)],
        "context": context,
        "mandate": mandate,
    }

    result = await graph.ainvoke(initial_state)
    output = result["messages"][-1].content

    # Boundary enforcement before returning to user
    safe_output = await enforce_boundary(output, mandate, db)
    return safe_output
```

**Para continuidad conversacional dentro de la sesion del mismo usuario:** checkpointing de LangGraph con un `thread_id` acotado a `{user_id}:{course_id}`. El thread_id se valida contra el usuario solicitante antes de cargarlo: un usuario no puede cargar el hilo de otro usuario.

```python
thread_id = f"{user.id}:{course_id}"
config = {"configurable": {"thread_id": thread_id}}

# Before loading a thread, verify ownership
if not thread_id.startswith(str(user.id)):
    raise HTTPException(status_code=403, detail="Access denied")
```

#### 7.3.5 Ejemplos de mandato por tipo de agente

| Tipo de agente | Solicitante | Compartimentos | Herramientas permitidas | Notas |
|------------|-----------|-------------|---------------|-------|
| **Tutor** (empleado que pregunta) | Empleado A | `user_profile:A`, `user_progress:A`, `course_content:X` | `search_course_content`, `get_lesson` | No puede ver a otros usuarios. No puede ver otros cursos. |
| **Tutor** (admin probando un curso) | Admin B | `course_content:X` | `search_course_content`, `get_lesson` | El admin obtiene acceso solo al contenido. Ningun dato de alumno se filtra en la prueba. |
| **Generador de contenido** (creando curso desde un PDF) | Admin B | `org_documents`, `course_content:new` | `search_chunks`, `create_module`, `create_exercise` | Sin acceso a ningun dato de usuario. Opera solo sobre documentos. |
| **Evaluador** (calificando un caso practico) | Empleado A | `user_progress:A`, `course_content:X` | `get_exercise`, `get_rubric` | Ve la rubrica y la respuesta del alumno. Nada mas. |
| **Reportero de skills** (generando informe de matriz) | Admin B | `org_skills_matrix` | `query_skills` | Ve skills agregadas. Sin intentos de ejercicio individuales. Sin datos de accesibilidad. |

---

### 7.4 Cumplimiento del RGPD

SkillNet es autoalojado. La empresa que lo despliega es el **responsable del tratamiento** (RGPD art. 4(7)). SkillNet es el software — como instalar cualquier herramienta de codigo abierto, la responsabilidad de un tratamiento licito recae en la organizacion que lo despliega. SkillNet proporciona los mecanismos para cumplir; la empresa debe usarlos correctamente.

#### 7.4.1 Derecho de supresion (art. 17)

Cuando un admin activa "Eliminar empleado", el sistema ofrece dos rutas:

**Ruta A: eliminacion completa (CASCADE)**

```sql
-- All these tables CASCADE from users(id):
-- user_sessions       -> deleted (ON DELETE CASCADE)
-- enrollments         -> deleted (ON DELETE CASCADE)
-- exercise_attempts   -> deleted (ON DELETE CASCADE)
-- user_skills         -> deleted (ON DELETE CASCADE)
-- spaced_repetition   -> deleted (ON DELETE CASCADE)
-- course_feedback     -> deleted (ON DELETE CASCADE)
-- documents.uploaded_by -> SET NULL (documents are org property, not user property)
-- courses.created_by   -> SET NULL (courses persist, authorship anonymized)
-- enrollments.assigned_by -> SET NULL

DELETE FROM users WHERE id = $1;
-- PostgreSQL CASCADE handles all child records
```

Tras la eliminacion:
- La cuenta del usuario, su progreso, skills, sesiones, feedback e historial de ejercicios desaparecen permanentemente.
- Los documentos que subio permanecen (pertenecen al org) pero `uploaded_by` se pone a NULL.
- Los cursos que creo permanecen pero `created_by` se pone a NULL.
- No hay borrado logico (soft delete). No hay columna `deleted_at`. Los datos son irrecuperables.

**Ruta B: anonimizacion (para estadisticas agregadas)**

```sql
-- Anonymize identity but preserve statistical data
UPDATE users SET
    email = 'anon-' || id::text || '@deleted.local',
    full_name = 'Former Employee #' || LEFT(id::text, 8),
    hashed_password = 'DELETED',
    accessibility = '{}',
    is_active = false,
    updated_at = now()
WHERE id = $1;

-- Delete all sessions (can't log in anymore)
DELETE FROM user_sessions WHERE user_id = $1;
```

El admin elige la ruta durante la eliminacion. La UI hace de la Ruta A la opcion por defecto con una advertencia clara.

**Limpieza de estado de LangGraph:** cuando se elimina un usuario, todos los checkpoints de LangGraph cuyo `thread_id` empiece con el ID de ese usuario tambien se purgan del almacen de checkpoints.

#### 7.4.2 Minimizacion de datos (art. 5(1)(c))

SkillNet recopila solo lo necesario para su funcionamiento:

| Dato recopilado | Por que es necesario | Medida de minimizacion |
|----------------|--------------------|--------------------|
| Email | Autenticacion, recuperacion de contrasena | Solo email corporativo. No se requiere email personal. |
| Nombre completo | Visualizacion en la UI, identificacion por el admin | Sin separacion de apellidos. Sin titulo/tratamiento. |
| Contrasena con hash | Autenticacion | Almacenada como hash bcrypt. La contrasena en crudo nunca se persiste. |
| Departamento (opcional) | Agrupacion organizativa para emparejamiento con mentor | No obligatorio. Puede quedar en blanco. |
| Respuestas de ejercicios | Evaluacion de skills, repeticion espaciada | Almacenadas como jsonb. Solo la respuesta y la puntuacion, no datos a nivel de pulsacion de tecla. |
| Niveles de skill | Matriz de skills, emparejamiento con mentor | Solo tres niveles (bajo/medio/alto). No puntuaciones granulares. |
| Perfil de aprendizaje | Adaptacion de la UI | Uno de tres presets (estandar/foco/rapido). Sin algoritmo de perfilado. Lo elige el empleado. |
| Flags de accesibilidad | Adaptacion del renderizado en frontend | Ver 7.4.3 mas abajo. |
| Marcas de tiempo | Repeticion espaciada, pista de auditoria | Necesidad funcional. Se recopilan automaticamente, no se solicitan. |

**Lo que SkillNet NO recopila:**
- Direcciones IP (mas alla de la seguridad de sesion — almacenadas en la tabla de sesiones, purgadas al expirar la sesion)
- Huellas digitales de navegador
- Geolocalizacion
- Identificadores de dispositivo
- Datos biometricos
- Datos politicos, religiosos o de salud (los flags de accesibilidad no son datos de salud — ver 7.4.3)
- Edad, fecha de nacimiento, DNI, domicilio
- Analitica de comportamiento (sin mapas de calor, seguimiento de clics, grabacion de sesion)

#### 7.4.3 Flags de accesibilidad: arquitectura de la privacidad

Los flags de accesibilidad (`{"tea": false, "tdah": true, "dislexia": false}`) se almacenan en la columna jsonb `users.accessibility`. Requieren un tratamiento especial porque revelan condicion de neurodivergencia, lo cual es sensible aunque el RGPD no lo clasifique como dato de "categoria especial" (art. 9) salvo que constituya dato de salud.

**Garantias de arquitectura:**

1. **Almacenados en PostgreSQL:** si, en la columna `users.accessibility`. Es necesario porque el frontend necesita leer los flags en cada carga de pagina para adaptar el renderizado.

2. **Devueltos por la API:** solo al usuario propietario, mediante un endpoint dedicado (`GET /api/v1/me`). El modelo Pydantic `UserSelfResponse` incluye `accessibility`. El modelo `UserAdminResponse` NO lo incluye. Ningun otro endpoint devuelve este campo.

3. **Nunca enviados al LLM:** el proceso de arranque del agente (`load_agent_context`) excluye explicitamente los datos de accesibilidad de todos los compartimentos. Incluso el compartimento `user_profile` devuelve solo `name` y `learning_profile` — nunca `accessibility`. El LLM nunca ve "este usuario tiene TDAH".

4. **Nunca visibles para el admin:** el panel de admin muestra los perfiles de empleado sin la columna de accesibilidad. El admin no puede consultar, filtrar ni ordenar por flags de accesibilidad. Ningun informe de admin incluye datos de accesibilidad. El endpoint de admin `GET /api/v1/admin/users` devuelve `UserAdminResponse` (sin accesibilidad). El endpoint de admin `GET /api/v1/admin/users/{id}` tambien devuelve `UserAdminResponse`.

5. **Nunca usados para logica de backend:** ninguna funcion de backend lee `accessibility` para ninguna decision. Ninguna consulta SQL filtra por ello. Ningun agente lo recibe. Solo lo lee el frontend de React para aplicar adaptaciones CSS (cambios de fuente para dislexia, movimiento reducido para el perfil de foco, navegacion paso a paso para TEA).

6. **El escaner de frontera detecta fugas:** si la salida de un agente menciona "TEA", "TDAH", "dislexia" o "neurodiverg", el escaner de frontera bloquea la respuesta entera (ver 7.3.3). Esto captura referencias alucinadas — el agente no deberia conocer estos flags, pero si de algun modo genera esos terminos, la salida se bloquea.

7. **Supresion:** cuando se elimina un usuario (Ruta A), la fila desaparece. Cuando se anonimiza (Ruta B), `accessibility` se pone a `'{}'`. No queda ningun registro historico de los flags.

#### 7.4.4 Exportacion de datos (art. 20 — Portabilidad)

**Endpoint:** `GET /api/v1/me/export`

Devuelve un archivo ZIP que contiene:

```
export_{user_id}_{date}/
├── profile.json          # name, email, role, learning_profile, accessibility, hired_at
├── skills.json           # current skill levels with dates
├── enrollments.json      # all enrollments with status, scores, dates
├── exercise_history.json # all exercise attempts with answers and scores
├── feedback.json         # course feedback submitted
└── documents/            # PDFs the user uploaded (if any)
    ├── manual_devolucion.pdf
    └── ...
```

- **Quien puede activarlo:** el empleado para sus propios datos (`GET /api/v1/me/export`). El admin para cualquier empleado del org (`GET /api/v1/admin/users/{id}/export`). Ambos devuelven los mismos datos.
- **Formato:** JSON (legible por maquina, como exige el RGPD art. 20).
- **Tiempo de respuesta:** sincrono para conjuntos de datos pequenos. Para historiales grandes, devuelve una entrada en `generation_jobs` y la exportacion es descargable cuando esta lista.

#### 7.4.5 Tratamiento de datos por el LLM

**Que se envia a LLM externos:**

| Dato | ¿Se envia al LLM? | Por que / por que no |
|------|--------------|---------------|
| Texto de documentos (chunks) | Si | Necesario para la recuperacion RAG y la generacion de cursos. El admin subio estos documentos sabiendo que serian procesados por IA. |
| Contenido de ejercicios (preguntas, opciones) | Si | Necesario para generar y evaluar ejercicios. |
| Respuestas de ejercicios del empleado | Si (solo al agente evaluador) | Necesario para calificar ejercicios practicos/de dialogo. Enviado dentro del alcance del mandato. |
| Nombre del empleado | Minimo | Incluido en el contexto del tutor para personalizacion ("Hola Maria"). Puede desactivarse en los ajustes del org. |
| Email del empleado | No | Nunca se envia al LLM. No hay motivo para ello. |
| Flags de accesibilidad | **Nunca** | Excluidos arquitectonicamente de todos los compartimentos de agente. |
| Niveles de skill | Solo en agregado (informes de admin) | Los niveles individuales se envian solo cuando el propio usuario solicita su tutor. |
| Contrasenas / tokens | **Nunca** | No se incluyen en ningun modelo de datos accesible a los agentes. |

**Lo que permanece local:**

- Todos los datos de autenticacion (contrasenas, sesiones, tokens)
- Todos los flags de accesibilidad
- Todos los metadatos de usuario (email, fecha de contratacion, pertenencia al org)
- Registros de sesion y pistas de auditoria
- La matriz de skills (permanece en PostgreSQL; solo el agente de informes del admin la consulta, y usa llamadas a herramientas, no relleno de contexto)

**Configuracion del proveedor:** la empresa que despliega elige su proveedor de LLM mediante variables de entorno. Si quieren que ningun dato salga de su red, pueden apuntar la API a una instancia local de Ollama/vLLM. SkillNet no impone ni recomienda ningun proveedor especifico.

---

### 7.5 Seguridad de la API

#### 7.5.1 Limitacion de tasa (rate limiting)

La limitacion de tasa usa `slowapi` (un wrapper nativo de FastAPI sobre `limits`), respaldado por almacenamiento en memoria para el MVP. Para despliegues multiproceso, se puede sustituir por Redis.

| Grupo de endpoints | Limite | Razon |
|---------------|-------|-----------|
| `POST /auth/login` | 5/minuto por IP | Proteccion contra fuerza bruta |
| `POST /auth/forgot-password` | 3/hora por IP | Prevencion de enumeracion de emails |
| `POST /auth/register` (si el autorregistro esta habilitado) | 3/hora por IP | Prevencion de abuso |
| `POST /api/v1/*/generate` (generacion de contenido) | 10/hora por usuario | Control de coste de LLM |
| `POST /api/v1/chat/*` (chat del tutor) | 30/minuto por usuario | Control de coste de LLM permitiendo conversacion natural |
| `GET /api/v1/*` (endpoints de lectura) | 120/minuto por usuario | Prevencion general de abuso |
| `POST/PUT/DELETE /api/v1/*` (endpoints de escritura) | 60/minuto por usuario | Prevencion general de abuso |
| `GET /api/v1/me/export` | 3/dia por usuario | Evita el abuso del endpoint de exportacion |

Los intentos de login fallidos se rastrean por IP Y por email. Tras 10 intentos fallidos para el mismo email en 1 hora, la cuenta se bloquea temporalmente durante 15 minutos (independientemente de la IP).

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginSchema):
    ...
```

#### 7.5.2 Validacion de entrada (Pydantic)

Cada cuerpo de peticion y parametro de ruta se valida con modelos Pydantic v2 con restricciones estrictas:

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class LoginSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class CreateUserSchema(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "employee"]
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        # Strip control characters
        return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v).strip()

class CreateCourseSchema(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)

class ExerciseAttemptSchema(BaseModel):
    answer: dict  # Validated further by exercise type logic
    # No arbitrary fields accepted

class DocumentUploadMeta(BaseModel):
    title: str = Field(min_length=1, max_length=500)
```

**Reglas clave:**
- Todos los campos de texto tienen restricciones `max_length`.
- Los UUID en parametros de ruta se validan automaticamente como tipo UUID por FastAPI.
- Los enums se validan contra los valores permitidos.
- No se aceptan dicts en crudo sin esquema — incluso los campos `jsonb` tienen subesquemas tipados.

#### 7.5.3 Seguridad en la subida de ficheros

Los documentos subidos para la generacion de cursos pasan por validacion:

```python
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "text/markdown",
    "text/plain",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

async def validate_upload(file: UploadFile) -> None:
    # 1. Check declared content type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"File type {file.content_type} not allowed")

    # 2. Check file size (read in chunks, don't load entire file into memory)
    size = 0
    while chunk := await file.read(8192):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise HTTPException(413, f"File exceeds {MAX_FILE_SIZE // 1024 // 1024}MB limit")
    await file.seek(0)  # Reset for actual processing

    # 3. Verify magic bytes (don't trust Content-Type header alone)
    header = await file.read(8)
    await file.seek(0)
    if file.content_type == "application/pdf" and not header.startswith(b"%PDF"):
        raise HTTPException(400, "File content does not match declared PDF type")

    # 4. Filename sanitization
    safe_name = secure_filename(file.filename)  # werkzeug.utils.secure_filename
    if not safe_name:
        raise HTTPException(400, "Invalid filename")
```

**Almacenamiento:** los ficheros subidos se guardan en el sistema de ficheros local, en un directorio fuera de la raiz web (`/data/uploads/{org_id}/{document_id}/`). Nunca los sirve directamente el servidor web — la descarga pasa por un endpoint de FastAPI que comprueba autenticacion y autorizacion antes de transmitir el fichero.

**Escaneo de malware:** no incluido en el MVP. La empresa autoalojada puede anadir ClamAV o similar a nivel de proxy inverso. SkillNet lo documenta como practica de despliegue recomendada, no como funcionalidad integrada.

#### 7.5.4 Prevencion de inyeccion SQL

SkillNet usa SQLAlchemy con sesiones asincronas. Todas las consultas usan sentencias parametrizadas. No hay concatenacion de cadenas SQL en crudo en ningun punto del codigo.

```python
# CORRECT — parameterized
result = await db.execute(
    select(User).where(User.email == email, User.org_id == org_id)
)

# NEVER — string concatenation
# result = await db.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

**Reforzado por:**
- Convencion de revision de codigo: cualquier uso de `text()` para SQL en crudo debe usar parametros vinculados (`text("SELECT ... WHERE id = :id").bindparams(id=value)`).
- Tanto el ORM como el Core de SQLAlchemy parametrizan por defecto.

#### 7.5.5 Prevencion de XSS

**Frontend (React):** React escapa por defecto todos los valores interpolados. SkillNet usa `dangerouslySetInnerHTML` solo para contenido de UI generativa de Nivel 3, que se renderiza dentro de un `<iframe sandbox>` o Shadow DOM — aislado del DOM y las cookies de la aplicacion principal.

**Backend (cabeceras de respuesta):**

```python
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"  # Deprecated, but explicit
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # CSP set by reverse proxy (nginx/Caddy) for flexibility
    return response
```

**Content-Security-Policy:** configurada a nivel de proxy inverso (no en FastAPI) porque los despliegues autoalojados pueden necesitar ajustar los origenes permitidos. La CSP recomendada en la documentacion de despliegue:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'self'; form-action 'self'
```

#### 7.5.6 Endurecimiento adicional de la API

- **CORS:** configurado para permitir solo el origen del frontend. En despliegues autoalojados, es el mismo dominio, asi que CORS no hace falta. Si la API y el frontend estan en subdominios distintos, CORS se restringe a ese origen concreto.
- **Limite de tamano de peticion:** 60 MB como maximo (para dar cabida a subidas de ficheros mas la sobrecarga de JSON). Configurado tanto en FastAPI como en el proxy inverso.
- **Sin endpoints de depuracion en produccion:** `FastAPI(debug=False)` en produccion. No se expone `/docs` ni `/redoc` salvo que se habilite explicitamente por variable de entorno (`ENABLE_API_DOCS=true`).
- **Registro de auditoria:** todas las acciones de admin (crear usuario, eliminar usuario, crear curso, cambiar rol) se registran en una tabla `audit_log` con `user_id`, `action`, `target`, `timestamp`, `ip_address`. Las acciones de empleado NO se registran (para evitar la percepcion de vigilancia — coherente con la filosofia de "SkillNet no es el Gran Hermano").

```sql
CREATE TABLE audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id),
    actor_id    uuid NOT NULL REFERENCES users(id),
    action      text NOT NULL,
    target_type text,
    target_id   uuid,
    details     jsonb,
    ip_address  inet,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_org ON audit_log(org_id, created_at DESC);
```

---

### 7.6 Gestion de secretos

SkillNet es autoalojado. Todos los secretos los gestiona la empresa que despliega mediante variables de entorno. SkillNet no incluye secretos de fabrica, no almacena secretos en el codigo y no tiene ningun servicio de configuracion remota.

#### 7.6.1 Variables de entorno requeridas

```bash
# === REQUIRED ===

# Database connection
DATABASE_URL=postgresql+asyncpg://skillnet:password@localhost:5432/skillnet

# Session signing (used to generate CSRF tokens and as HMAC key)
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<64-character-hex-string>

# LLM provider (OpenAI-compatible API)
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# === OPTIONAL ===

# Email (required for password recovery; if not set, admin resets passwords manually)
SMTP_HOST=smtp.empresa.com
SMTP_PORT=587
SMTP_USER=skillnet@empresa.com
SMTP_PASS=<smtp-password>
SMTP_FROM=skillnet@empresa.com

# Deployment
ENVIRONMENT=production          # "production" or "development"
ALLOWED_ORIGINS=https://formacion.empresa.com
ENABLE_API_DOCS=false           # Set to "true" to expose /docs in production
ENABLE_SELF_REGISTRATION=false  # Set to "true" to allow employees to self-register

# Embedding model (if different from chat model)
EMBEDDING_MODEL=multilingual-e5-small
EMBEDDING_API_KEY=              # Falls back to LLM_API_KEY if not set
EMBEDDING_BASE_URL=             # Falls back to LLM_BASE_URL if not set
```

#### 7.6.2 Reglas de tratamiento de secretos

| Regla | Implementacion |
|------|---------------|
| **Nunca en el codigo** | Ningun secreto en ficheros fuente, ficheros de configuracion ni valores por defecto. `.env.example` solo tiene valores de relleno. |
| **Nunca en la imagen Docker** | Los secretos se pasan via `env_file` o `environment` en `docker-compose.yml`, no se incrustan en la imagen. |
| **Nunca en los logs** | El registro de peticiones de FastAPI excluye cabeceras cuyo nombre contenga "authorization", "cookie" o "x-csrf". Las URL de base de datos se registran con la contrasena redactada. |
| **Nunca en las respuestas de error** | Las excepciones no gestionadas devuelven un 500 generico con `{"detail": "Internal server error"}`. Las trazas de pila van solo a los logs del servidor. |
| **`.env` en `.gitignore`** | Incluido en el `.gitignore` del repositorio. No se puede commitear por accidente. |
| **Rotacion de `SECRET_KEY`** | Cambiar `SECRET_KEY` invalida todos los tokens CSRF existentes. Las sesiones se almacenan en BD (no firmadas con SECRET_KEY), asi que sobreviven a la rotacion. |

#### 7.6.3 Despliegue con Docker Compose

```yaml
# docker-compose.yml (shipped with the project)
services:
  app:
    image: skillnet/skillnet:latest
    env_file: .env
    ports:
      - "3000:3000"
    depends_on:
      db:
        condition: service_healthy

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: skillnet
      POSTGRES_USER: skillnet
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skillnet"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

**La documentacion de despliegue recomienda:**
- Ejecutar detras de un proxy inverso (nginx, Caddy, Traefik) que gestione la terminacion TLS.
- Usar Let's Encrypt para la gestion automatica de certificados HTTPS.
- Fijar `POSTGRES_PASSWORD` a un valor aleatorio fuerte (el ejemplo en `.env.example` es deliberadamente invalido para forzar al admin a cambiarlo).
- Restringir el puerto de base de datos (5432) solo a localhost — sin acceso externo.
- Copias de seguridad automaticas y regulares del volumen de datos de PostgreSQL.

#### 7.6.4 Seguridad de la clave de API del LLM

La clave de API del LLM es el secreto mas sensible porque tiene implicaciones economicas (costes de uso).

- **Almacenada solo en `.env`** — nunca en la base de datos, nunca en configuracion visible para el usuario.
- **Nunca enviada al frontend** — el frontend llama a la API de SkillNet, que hace de proxy hacia el proveedor de LLM. La app de React nunca conoce la clave de API.
- **Usada solo por el backend** — el cliente del LLM se inicializa una vez al arrancar y se reutiliza.
- **La limitacion de tasa protege frente al abuso** — incluso si un atacante consigue acceso a una sesion, los limites de tasa en los endpoints de generacion acotan el dano (10 peticiones de generacion/hora, 30 mensajes de chat/minuto).
- **Clave separada para embeddings (opcional)** — si la empresa usa proveedores distintos para chat y embeddings, puede fijar `EMBEDDING_API_KEY` por separado. Esto permite usar un proveedor mas barato para los embeddings.

---

### 7.7 Resumen de la arquitectura de seguridad

```
                    ┌──────────────────────────────────────────────────┐
                    │                   CLIENT                        │
                    │  React SPA (no secrets, no tokens in JS)        │
                    │  Reads: skillnet_csrf cookie (for CSRF header)  │
                    │  Sends: skillnet_session cookie (httpOnly, auto)│
                    └────────────────────┬─────────────────────────────┘
                                         │ HTTPS (TLS via reverse proxy)
                    ┌────────────────────▼─────────────────────────────┐
                    │              REVERSE PROXY                       │
                    │  TLS termination, CSP headers, rate limiting     │
                    └────────────────────┬─────────────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────────────┐
                    │              FastAPI APPLICATION                  │
                    │                                                   │
                    │  ┌─────────────┐  ┌──────────────┐               │
                    │  │  CSRF       │  │  Session     │               │
                    │  │  Middleware │→ │  Middleware   │               │
                    │  └─────────────┘  └──────┬───────┘               │
                    │                          │                        │
                    │                  ┌───────▼───────┐               │
                    │                  │  Route Guards  │               │
                    │                  │  (Depends)     │               │
                    │                  │  get_current   │               │
                    │                  │  require_admin │               │
                    │                  └───────┬───────┘               │
                    │                          │                        │
                    │         ┌────────────────┼────────────────┐       │
                    │         ▼                ▼                ▼       │
                    │  ┌──────────┐   ┌──────────────┐  ┌──────────┐  │
                    │  │  CRUD    │   │  AGENT       │  │  AUTH    │  │
                    │  │  Routes  │   │  Routes      │  │  Routes  │  │
                    │  │  (data   │   │  (chat,      │  │  (login, │  │
                    │  │  scoped  │   │  generate)   │  │  logout) │  │
                    │  │  by user │   │              │  │          │  │
                    │  │  or org) │   │  ┌────────┐  │  │          │  │
                    │  │          │   │  │MANDATE │  │  │          │  │
                    │  │          │   │  │ boot   │  │  │          │  │
                    │  │          │   │  └───┬────┘  │  │          │  │
                    │  │          │   │      │       │  │          │  │
                    │  │          │   │  ┌───▼────┐  │  │          │  │
                    │  │          │   │  │ AGENT  │  │  │          │  │
                    │  │          │   │  │(LangG) │  │  │          │  │
                    │  │          │   │  └───┬────┘  │  │          │  │
                    │  │          │   │      │       │  │          │  │
                    │  │          │   │  ┌───▼────┐  │  │          │  │
                    │  │          │   │  │BOUNDARY│  │  │          │  │
                    │  │          │   │  │scanner │  │  │          │  │
                    │  │          │   │  └────────┘  │  │          │  │
                    │  └──────────┘   └──────────────┘  └──────────┘  │
                    │                          │                        │
                    └──────────────────────────┼────────────────────────┘
                                               │
                    ┌──────────────────────────▼────────────────────────┐
                    │              PostgreSQL                            │
                    │  users, sessions, courses, exercises, skills,     │
                    │  enrollments, attempts, spaced_repetition,        │
                    │  document_chunks (pgvector), audit_log            │
                    │  ─────────────────────────────────────            │
                    │  All queries scoped by user_id or org_id          │
                    │  No unscoped queries in the application           │
                    └──────────────────────────────────────────────────┘
```

### 7.8 Que esta decidido frente a que esta aplazado

| Decidido | Aplazado |
|---------|----------|
| Cookies de sesion (sin JWT en cookies) | Row-Level Security (RLS) en pgvector para dominios de acceso a documentos |
| Hashing de contrasena con bcrypt via fastapi-users | Agente de aduanas suave para la aplicacion de frontera |
| Almacenamiento de sesiones en PostgreSQL con tokens con hash | Integracion de escaneo de malware con ClamAV |
| Patron de doble cookie CSRF | 2FA / TOTP |
| Arranque de agente basado en compartimentos con mandatos inmutables | Integracion SSO / SAML / LDAP |
| Escaner de frontera en toda salida de agente | Notificacion al admin del bloqueo de cuenta |
| Los datos de accesibilidad nunca se envian al LLM ni son visibles para el admin | Limitacion de tasa respaldada por Redis para multiproceso |
| Eliminacion completa o anonimizacion para la supresion RGPD | Politica de retencion del registro de auditoria |
| Validacion Pydantic en todas las entradas | Ajuste fino de Content-Security-Policy por despliegue |
| Limitacion de tasa en endpoints de auth y de LLM | Documentacion de copias de seguridad cifradas |
| Registro de auditoria para acciones de admin | Documentacion de allowlist de IP / VPN |
| Validacion de subida de ficheros (tipo, tamano, magic bytes) | |
| Segmentacion por `org_id` en todas las consultas | |
| Clave de API del LLM aislada al backend | |

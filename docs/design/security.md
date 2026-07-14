## 7. Security & Access Control

> **Status: v1.** Complete security architecture for SkillNet MVP (self-hosted, one instance per company). Covers authentication, authorization, agent security, GDPR compliance, API hardening, and secrets management.

---

### 7.1 Authentication Flow

SkillNet uses **session-based authentication** via fastapi-users with `CookieTransport`. No JWTs in cookies, no token management in frontend code. The browser sends an httpOnly cookie automatically on every request.

#### 7.1.1 Login flow

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

#### 7.1.2 Session storage

Sessions live in PostgreSQL, not in memory. This survives server restarts and enables multi-process deployments.

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

**The session token is hashed before storage** (SHA-256). If the database is compromised, raw tokens are not exposed. The cookie holds the raw token; the database holds only its hash.

On each request:
1. Read `skillnet_session` cookie.
2. Hash the token with SHA-256.
3. Look up `user_sessions` by `token_hash`.
4. Check `expires_at > now()`.
5. Join `users` table to get `user_id`, `role`, `org_id`, `is_active`.
6. If valid and active: update `last_used`, attach user to request state.
7. If invalid/expired/inactive: return 401 and clear cookie.

#### 7.1.3 Session invalidation

| Trigger | What happens |
|---------|-------------|
| **Logout** | `DELETE FROM user_sessions WHERE token_hash = $1`. Clear cookie. |
| **Password change** | `DELETE FROM user_sessions WHERE user_id = $1 AND id != $current_session`. All other sessions for that user are killed. Current session stays (the user just changed their own password). |
| **Admin deactivates employee** | `UPDATE users SET is_active = false WHERE id = $1`. Next request with any of that user's sessions hits the `is_active` check and returns 401. Sessions are garbage-collected later. |
| **Session expiry** | A daily cron job runs `DELETE FROM user_sessions WHERE expires_at < now()`. |

#### 7.1.4 CSRF protection

SameSite=Lax blocks cross-origin POST requests from other sites. This is the primary CSRF defense. Additionally:

- **Double-submit cookie pattern** for state-changing operations. On login, the backend sets a second non-httpOnly cookie (`skillnet_csrf`) with a random token. The frontend reads this cookie and sends it as an `X-CSRF-Token` header on every POST/PUT/DELETE request. The backend verifies that the header value matches the cookie value.
- **Why both?** SameSite=Lax allows cross-origin GET. The CSRF token ensures that even GET-based state changes (which SkillNet avoids by convention, but defense-in-depth) are protected. SameSite=Lax also has limited browser support edge cases on very old browsers.

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

#### 7.1.5 Password hashing

- **Algorithm:** bcrypt via passlib (the default in fastapi-users).
- **Work factor:** 12 rounds (default). This produces ~250ms hash time on modern hardware, which is fast enough for login but slow enough to resist brute force.
- **No password rules enforced by the backend** beyond minimum 8 characters. The frontend can suggest complexity, but the backend does not reject passwords based on composition. Rationale: research shows length matters more than complexity rules, and this is an internal company tool where the admin creates accounts.

---

### 7.2 Authorization Model

Two roles: `admin` and `employee`. No intermediate roles (the early "jefe/responsable" role was removed for simplicity). The admin can delegate by assigning courses and viewing data; they don't need a separate role for that.

#### 7.2.1 Role permissions matrix

| Resource | Admin | Employee |
|----------|-------|----------|
| **Own profile** (view/edit) | Yes | Yes |
| **Own progress/skills** (view) | Yes | Yes |
| **Own accessibility flags** (view/edit) | Yes | Yes |
| **Other employees' profiles** (view) | Yes, all in org | No |
| **Other employees' progress/skills** (view) | Yes, all in org | No |
| **Other employees' accessibility flags** | **No** (private) | No |
| **Course content** (view) | All | Only enrolled courses |
| **Courses** (create/edit/publish) | Yes | No |
| **Documents** (upload/manage) | Yes | No |
| **Users** (create/deactivate/delete) | Yes | No |
| **Org settings** (edit) | Yes | No |
| **Skills taxonomy** (manage) | Yes | No |
| **Enrollments** (assign/manage) | Yes | No |
| **Export employee data** | Yes | Own data only |
| **Tutor chat** | Yes (admin context) | Yes (employee context) |

**Critical rule: accessibility flags are NEVER visible to admin.** The `users.accessibility` column is private. No API endpoint returns it to any user other than the owner. The admin panel shows employee profiles without the accessibility field. This is enforced at the serializer level (separate Pydantic response models for "self" vs "admin-viewing-employee").

#### 7.2.2 Route-level guards (FastAPI dependencies)

Three reusable dependencies that compose:

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

Usage on routes:

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

#### 7.2.3 Data-level scoping

Every database query is scoped. There are NO unscoped queries in the application.

**Employee queries always filter by `user_id`:**

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

**Admin queries filter by `org_id`:**

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

**Pydantic response models enforce field visibility:**

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

### 7.3 Agent Security (Compartment Model)

Agents in SkillNet are LangGraph state machines. They access user data and organizational knowledge. The security model ensures an agent can ONLY access data it needs for its specific task, and can ONLY emit information the requesting user is authorized to see.

The principle: **control at boot (what agent can see) and at boundary (what it can emit), never inside the agent.**

#### 7.3.1 Compartment definition

A compartment is a named scope of data access. Compartments are not hierarchical — having access to one does not imply access to any other.

For the MVP, compartments map directly to data types:

| Compartment | What it includes |
|-------------|-----------------|
| `user_profile:{user_id}` | Name, email, learning profile for one specific user |
| `user_progress:{user_id}` | Enrollments, exercise attempts, spaced repetition state for one user |
| `user_skills:{user_id}` | Skill levels for one user |
| `course_content:{course_id}` | Lessons, exercises, module structure for one course |
| `org_documents` | Document chunks available for RAG retrieval (scoped by org_id) |
| `org_skills_matrix` | Aggregated skills data across all employees (admin-only) |

Compartments are NOT stored in the database as rows. They are a naming convention used by the agent boot process to determine what queries to run.

#### 7.3.2 Boot-time filtering

When an agent is invoked for a task, the orchestrator constructs a **mandate** before booting the agent:

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

**The mandate is frozen** (`frozen=True` dataclass with frozensets). The agent cannot modify its own permissions at runtime.

**Example: tutor agent serving Employee A during course X:**

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

**What this mandate EXCLUDES:**
- Employee B's progress (no `user_progress:{employee_b_id}` compartment)
- Employee A's skill graph (no `user_skills:{employee_a_id}` — tutor doesn't need it)
- Other courses (no `course_content:{course_y_id}`)
- Org-wide documents not related to this course
- Admin-only data (skills matrix, other employees' profiles)

The **data loader** reads the mandate's compartments and runs ONLY the queries that match. Data outside the compartments is never fetched from the database, so it never enters the agent's context window.

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

#### 7.3.3 Boundary enforcement

After the agent generates a response, a **boundary scanner** inspects the output before it reaches the user. This is a hard, deterministic layer — not a prompt instruction.

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

**Two layers of boundary enforcement:**

1. **Hard scanner (deterministic):** The code above. Runs on every response. Cannot be bypassed. Checks for PII leakage, accessibility data, output size, known patterns.

2. **Soft customs agent (optional, post-MVP):** A separate, cheap LLM call that reviews the response against the mandate. "Does this response contain information about users other than the requesting user?" This catches semantic leakage that pattern matching misses. It is advisory — if uncertain, it flags for human review rather than blocking.

#### 7.3.4 Preventing cross-user data leakage

**Problem:** If two users ask the tutor questions sequentially, shared agent state could leak User A's exercise answers to User B.

**Solution: agents are stateless across users.** Each agent invocation gets:
- A fresh LangGraph state (no carry-over between requests from different users)
- Context loaded exclusively from the mandate's compartments
- No shared in-memory cache between user sessions

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

**For conversational continuity within the same user's session:** LangGraph checkpointing with a `thread_id` scoped to `{user_id}:{course_id}`. The thread_id is validated against the requesting user before loading — a user cannot load another user's thread.

```python
thread_id = f"{user.id}:{course_id}"
config = {"configurable": {"thread_id": thread_id}}

# Before loading a thread, verify ownership
if not thread_id.startswith(str(user.id)):
    raise HTTPException(status_code=403, detail="Access denied")
```

#### 7.3.5 Mandate examples by agent type

| Agent type | Principal | Compartments | Allowed tools | Notes |
|------------|-----------|-------------|---------------|-------|
| **Tutor** (employee asking question) | Employee A | `user_profile:A`, `user_progress:A`, `course_content:X` | `search_course_content`, `get_lesson` | Cannot see other users. Cannot see other courses. |
| **Tutor** (admin testing a course) | Admin B | `course_content:X` | `search_course_content`, `get_lesson` | Admin gets content-only access. No student data leaks into test. |
| **Content generator** (creating course from PDF) | Admin B | `org_documents`, `course_content:new` | `search_chunks`, `create_module`, `create_exercise` | No access to any user data. Operates only on documents. |
| **Evaluator** (grading practical case) | Employee A | `user_progress:A`, `course_content:X` | `get_exercise`, `get_rubric` | Sees the rubric and the student's answer. Nothing else. |
| **Skills reporter** (generating matrix report) | Admin B | `org_skills_matrix` | `query_skills` | Sees aggregated skills. No individual exercise attempts. No accessibility data. |

---

### 7.4 GDPR Compliance

SkillNet is self-hosted. The company deploying it is the **data controller** (GDPR Art. 4(7)). SkillNet is the software — like installing any open-source tool, the responsibility for lawful processing lies with the deploying organization. SkillNet provides the mechanisms to comply; the company must use them correctly.

#### 7.4.1 Right to erasure (Art. 17)

When an admin triggers "Delete employee", the system offers two paths:

**Path A: Full deletion (CASCADE)**

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

After deletion:
- The user's account, progress, skills, sessions, feedback, exercise history are permanently gone.
- Documents they uploaded remain (they belong to the org) but `uploaded_by` is set to NULL.
- Courses they created remain but `created_by` is set to NULL.
- No soft delete. No `deleted_at` column. The data is irrecoverable.

**Path B: Anonymization (for aggregate statistics)**

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

The admin chooses which path during deletion. The UI makes Path A the default with clear warning.

**LangGraph state cleanup:** When a user is deleted, all LangGraph checkpoints with `thread_id` starting with that user's ID are also purged from the checkpoint store.

#### 7.4.2 Data minimization (Art. 5(1)(c))

SkillNet collects only what is necessary for its function:

| Data collected | Why it is necessary | Minimization measure |
|----------------|--------------------|--------------------|
| Email | Authentication, password recovery | Only corporate email. No personal email required. |
| Full name | Display in UI, admin identification | No surname separation. No title/salutation. |
| Hashed password | Authentication | Stored as bcrypt hash. Raw password never persisted. |
| Department (optional) | Organizational grouping for mentor matching | Not required. Can be blank. |
| Exercise answers | Skill assessment, spaced repetition | Stored as jsonb. Only the answer and score, not keystroke-level data. |
| Skill levels | Skills matrix, mentor matching | Three levels only (low/medium/high). Not granular scores. |
| Learning profile | UI adaptation | One of three presets (standard/focus/fast). No profiling algorithm. Employee chooses. |
| Accessibility flags | Frontend rendering adaptation | See 7.4.3 below. |
| Timestamps | Spaced repetition, audit trail | Functional necessity. Auto-collected, not solicited. |

**What SkillNet does NOT collect:**
- IP addresses (beyond session security — stored in sessions table, purged on session expiry)
- Browser fingerprints
- Geolocation
- Device identifiers
- Biometric data
- Political, religious, or health data (accessibility flags are not health data — see 7.4.3)
- Age, date of birth, national ID, home address
- Behavioral analytics (no heat maps, click tracking, session recording)

#### 7.4.3 Accessibility flags: architecture of privacy

Accessibility flags (`{"tea": false, "tdah": true, "dislexia": false}`) are stored in the `users.accessibility` jsonb column. They require special handling because they reveal neurodivergence status, which is sensitive even though GDPR does not classify it as "special category" data (Art. 9) unless it constitutes health data.

**Architectural guarantees:**

1. **Stored in PostgreSQL:** Yes, in the `users.accessibility` column. This is necessary because the frontend needs to read the flags on every page load to adapt rendering.

2. **Returned by the API:** Only to the owning user, via a dedicated endpoint (`GET /api/v1/me`). The `UserSelfResponse` Pydantic model includes `accessibility`. The `UserAdminResponse` model does NOT. No other endpoint returns this field.

3. **Never sent to LLM:** The agent boot process (`load_agent_context`) explicitly excludes accessibility data from every compartment. Even the `user_profile` compartment returns only `name` and `learning_profile` — never `accessibility`. The LLM never sees "this user has TDAH."

4. **Never visible to admin:** The admin panel shows employee profiles without the accessibility column. The admin cannot query, filter, or sort by accessibility flags. No admin report includes accessibility data. The admin endpoint `GET /api/v1/admin/users` returns `UserAdminResponse` (without accessibility). The admin endpoint `GET /api/v1/admin/users/{id}` also returns `UserAdminResponse`.

5. **Never used for backend logic:** No backend function reads `accessibility` for any decision. No SQL query filters by it. No agent receives it. It is read ONLY by the React frontend to apply CSS adaptations (font changes for dyslexia, reduced motion for focus profile, step-by-step navigation for TEA).

6. **Boundary scanner catches leakage:** If an agent's output mentions "TEA", "TDAH", "dislexia", or "neurodiverg", the boundary scanner blocks the entire response (see 7.3.3). This catches hallucinated references — the agent should not know about these flags, but if it somehow generates such terms, the output is blocked.

7. **Erasure:** When a user is deleted (Path A), the row is gone. When anonymized (Path B), `accessibility` is set to `'{}'`. No historical record of the flags remains.

#### 7.4.4 Data export (Art. 20 — Portability)

**Endpoint:** `GET /api/v1/me/export`

Returns a ZIP file containing:

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

- **Who can trigger it:** The employee for their own data (`GET /api/v1/me/export`). The admin for any employee in the org (`GET /api/v1/admin/users/{id}/export`). Both return the same data.
- **Format:** JSON (machine-readable, as required by GDPR Art. 20).
- **Response time:** Synchronous for small datasets. For large histories, returns a `generation_jobs` entry and the export is downloadable when ready.

#### 7.4.5 LLM data handling

**What goes to external LLMs:**

| Data | Sent to LLM? | Why / why not |
|------|--------------|---------------|
| Document text (chunks) | Yes | Required for RAG retrieval and course generation. The admin uploaded these documents knowing they'd be processed by AI. |
| Exercise content (questions, options) | Yes | Required for generating and evaluating exercises. |
| Employee's exercise answers | Yes (to evaluator agent only) | Required to grade practical/dialogue exercises. Sent within the mandate scope. |
| Employee name | Minimal | Included in tutor context for personalization ("Hi Maria"). Can be disabled in org settings. |
| Employee email | No | Never sent to LLM. No reason to. |
| Accessibility flags | **Never** | Architecturally excluded from all agent compartments. |
| Skill levels | Only in aggregate (admin reports) | Individual levels sent only when the specific user requests their own tutor. |
| Passwords / tokens | **Never** | Not included in any data model accessible to agents. |

**What stays local:**

- All authentication data (passwords, sessions, tokens)
- All accessibility flags
- All user metadata (email, hire date, org membership)
- Session logs and audit trails
- The skills matrix (stays in PostgreSQL; only the admin reporting agent queries it, and it uses tool calls, not context stuffing)

**Provider configuration:** The deploying company chooses their LLM provider via environment variables. If they want zero data leaving their network, they can point the API at a local Ollama/vLLM instance. SkillNet does not enforce or recommend any specific provider.

---

### 7.5 API Security

#### 7.5.1 Rate limiting

Rate limiting uses `slowapi` (a FastAPI-native wrapper around `limits`), backed by in-memory storage for MVP. For multi-process deployments, Redis can be substituted.

| Endpoint group | Limit | Rationale |
|---------------|-------|-----------|
| `POST /auth/login` | 5/minute per IP | Brute force protection |
| `POST /auth/forgot-password` | 3/hour per IP | Email enumeration prevention |
| `POST /auth/register` (if self-registration enabled) | 3/hour per IP | Abuse prevention |
| `POST /api/v1/*/generate` (content generation) | 10/hour per user | LLM cost control |
| `POST /api/v1/chat/*` (tutor chat) | 30/minute per user | LLM cost control while allowing natural conversation |
| `GET /api/v1/*` (read endpoints) | 120/minute per user | General abuse prevention |
| `POST/PUT/DELETE /api/v1/*` (write endpoints) | 60/minute per user | General abuse prevention |
| `GET /api/v1/me/export` | 3/day per user | Prevents abuse of export endpoint |

Failed login attempts are tracked per IP AND per email. After 10 failed attempts for the same email within 1 hour, the account is temporarily locked for 15 minutes (regardless of IP).

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginSchema):
    ...
```

#### 7.5.2 Input validation (Pydantic)

Every request body and path parameter is validated by Pydantic v2 models with strict constraints:

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

**Key rules:**
- All string fields have `max_length` constraints.
- UUIDs in path parameters are validated as UUID type by FastAPI automatically.
- Enums are validated against allowed values.
- No raw dicts accepted without schema — even `jsonb` fields have typed sub-schemas.

#### 7.5.3 File upload security

Documents uploaded for course generation pass through validation:

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

**Storage:** Uploaded files are stored on the local filesystem in a directory outside the web root (`/data/uploads/{org_id}/{document_id}/`). They are never served directly by the web server — download goes through a FastAPI endpoint that checks authentication and authorization before streaming the file.

**Malware scanning:** Not included in the MVP. The self-hosting company can add ClamAV or similar at the reverse proxy level. SkillNet documents this as a recommended deployment practice, not a built-in feature.

#### 7.5.4 SQL injection prevention

SkillNet uses SQLAlchemy with async sessions. All queries use parameterized statements. No raw SQL string concatenation anywhere in the codebase.

```python
# CORRECT — parameterized
result = await db.execute(
    select(User).where(User.email == email, User.org_id == org_id)
)

# NEVER — string concatenation
# result = await db.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

**Enforced by:**
- Code review convention: any use of `text()` for raw SQL must use bound parameters (`text("SELECT ... WHERE id = :id").bindparams(id=value)`).
- SQLAlchemy's ORM and Core both parameterize by default.

#### 7.5.5 XSS prevention

**Frontend (React):** React escapes all interpolated values by default. SkillNet uses `dangerouslySetInnerHTML` only for Level 3 generative UI content, which is rendered inside an `<iframe sandbox>` or Shadow DOM — isolated from the main application DOM and cookies.

**Backend (response headers):**

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

**Content-Security-Policy:** Configured at the reverse proxy level (not in FastAPI) because self-hosted deployments may need to adjust allowed sources. The recommended CSP in the deployment docs:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'self'; form-action 'self'
```

#### 7.5.6 Additional API hardening

- **CORS:** Configured to allow only the frontend origin. In self-hosted deployments, this is the same domain, so CORS is not needed. If the API and frontend are on different subdomains, CORS is restricted to that specific origin.
- **Request size limit:** 60 MB maximum (to accommodate file uploads + JSON overhead). Set at both FastAPI and reverse proxy level.
- **No debug endpoints in production:** `FastAPI(debug=False)` in production. No `/docs` or `/redoc` exposed unless explicitly enabled via environment variable (`ENABLE_API_DOCS=true`).
- **Audit logging:** All admin actions (create user, delete user, create course, change role) are logged to a `audit_log` table with `user_id`, `action`, `target`, `timestamp`, `ip_address`. Employee actions are NOT logged (to avoid surveillance perception — consistent with the "SkillNet is not Big Brother" philosophy).

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

### 7.6 Secrets Management

SkillNet is self-hosted. All secrets are managed by the deploying company through environment variables. SkillNet ships no secrets, stores no secrets in code, and has no remote configuration service.

#### 7.6.1 Required environment variables

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

#### 7.6.2 Secret handling rules

| Rule | Implementation |
|------|---------------|
| **Never in code** | No secrets in source files, config files, or defaults. `.env.example` has placeholder values only. |
| **Never in Docker image** | Secrets are passed via `env_file` or `environment` in `docker-compose.yml`, not baked into the image. |
| **Never in logs** | FastAPI request logging excludes headers with "authorization", "cookie", or "x-csrf" in the name. Database URLs are logged with password redacted. |
| **Never in error responses** | Unhandled exceptions return generic 500 with `{"detail": "Internal server error"}`. Stack traces go to server logs only. |
| **`.env` in `.gitignore`** | Shipped in the repository's `.gitignore`. Cannot be accidentally committed. |
| **`SECRET_KEY` rotation** | Changing `SECRET_KEY` invalidates all existing CSRF tokens. Sessions are stored in DB (not signed with SECRET_KEY), so they survive rotation. |

#### 7.6.3 Docker Compose deployment

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

**Deployment documentation recommends:**
- Running behind a reverse proxy (nginx, Caddy, Traefik) that handles TLS termination.
- Using Let's Encrypt for automatic HTTPS certificate management.
- Setting `POSTGRES_PASSWORD` to a strong random value (the example in `.env.example` is deliberately invalid to force the admin to change it).
- Restricting database port (5432) to localhost only — no external access.
- Regular automated backups of the PostgreSQL data volume.

#### 7.6.4 LLM API key security

The LLM API key is the most sensitive secret because it has financial implications (usage costs).

- **Stored only in `.env`** — never in the database, never in user-facing config.
- **Never sent to the frontend** — the frontend calls SkillNet's API, which proxies to the LLM provider. The React app never knows the API key.
- **Used only by the backend** — the LLM client is initialized once at startup and reused.
- **Rate limiting protects against abuse** — even if an attacker gains session access, rate limits on generation endpoints cap the damage (10 generation requests/hour, 30 chat messages/minute).
- **Separate key for embeddings (optional)** — if the company uses different providers for chat and embeddings, they can set `EMBEDDING_API_KEY` separately. This allows using a cheaper provider for embeddings.

---

### 7.7 Security Architecture Summary

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

### 7.8 What's decided vs what's deferred

| Decided | Deferred |
|---------|----------|
| Session cookies (not JWT in cookies) | Row-Level Security (RLS) on pgvector for document access domains |
| bcrypt password hashing via fastapi-users | Soft customs agent for boundary enforcement |
| Session storage in PostgreSQL with hashed tokens | ClamAV/malware scanning integration |
| CSRF double-submit cookie pattern | 2FA / TOTP |
| Compartment-based agent boot with frozen mandates | SSO / SAML / LDAP integration |
| Boundary scanner on all agent output | Account lockout notification to admin |
| Accessibility data never sent to LLM, never visible to admin | Redis-backed rate limiting for multi-process |
| Full deletion or anonymization for GDPR erasure | Audit log retention policy |
| Pydantic validation on all inputs | Content-Security-Policy fine-tuning per deployment |
| Rate limiting on auth and LLM endpoints | Encrypted backups documentation |
| Audit logging for admin actions | IP allowlisting / VPN documentation |
| File upload validation (type, size, magic bytes) | |
| `org_id` scoping on all queries | |
| LLM API key isolated to backend | |

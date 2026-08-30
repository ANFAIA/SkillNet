# Screens

> Screen specs for implementation. Each screen defines route, purpose, sections, data, states, and actions.

---

## Auth

### Login

**Route:** `/login`
**Role:** public

Email + password form. On success, backend sets session cookie and redirects to `/dashboard` (employee) or `/admin` (admin).

**Sections:**
- Logo + app name
- Email field
- Password field
- Submit button
- Error message (wrong credentials, account disabled)

**States:**
- Default: form ready
- Loading: submitting credentials
- Error: inline message below form

**Actions:**
- Submit -> `POST /api/v1/auth/login` -> redirect by role

---

## Employee

### Dashboard

**Route:** `/empleado`
**Role:** employee

The main screen. Not a course catalog. A daily plan: what to do today, how things are going, what you know.

**Sections:**
- **Greeting** — "Hola, Laura" + "Lo que toca hoy"
- **Today's actions** (max 3) — urgent review (spaced repetition), assigned course to continue, recommendation. Each with one-click start
- **Courses in progress** — progress bar, current module, last activity with result
- **Skill map** — 3 columns: mastered / in progress / pending. Auto-updated from exercise results
- **Recent activity** — chronological list of last actions (exercise results, lessons completed)

**Data:**
- `GET /api/v1/users/me/today` — reviews due, next course action, recommendation
- `GET /api/v1/enrollments?status=in_progress` — active courses with progress
- `GET /api/v1/users/me/skills` — skill levels
- `GET /api/v1/users/me/activity` — recent exercise attempts

**States:**
- Empty: no courses assigned -> prompt to wait for admin or explore available content
- Loading: skeleton layout matching section structure
- Populated: full dashboard

**Actions:**
- Click today action -> navigate to course/exercise
- Click course -> `/courses/:id`
- Click skill -> show detail (exercises that contributed to level)

---

### My Courses

**Route:** `/empleado/cursos`
**Role:** employee

List of all courses assigned to the employee.

**Sections:**
- **Filter tabs** — All / In progress / Completed / Not started
- **Course cards** — title, progress bar, module count, deadline (if set), last activity

**Data:**
- `GET /api/v1/enrollments` — all enrollments with course details and progress

**States:**
- Empty: no courses assigned
- Populated: card grid/list

**Actions:**
- Click course -> `/courses/:id`
- Filter by status

---

### Course View

**Route:** `/empleado/curso/:id`
**Role:** employee

The course experience. Module list -> lesson content -> exercises. Sequential navigation.

**Sections:**
- **Course header** — title, outcome, progress, total modules
- **Module sidebar/list** — modules with completion status, current module highlighted
- **Lesson content** — text content of the current lesson
- **Exercise** — rendered by type (test, true/false, fill blank, order steps, practical case, dialogue). Shows question, accepts answer, gives immediate feedback with source citation
- **Navigation** — previous/next buttons, progress indicator

**Data:**
- `GET /api/v1/courses/:id` — course with modules, lessons, exercises
- `POST /api/v1/exercises/:id/attempt` — submit answer, receive score + feedback
- `GET /api/v1/enrollments/:id` — current progress

**States:**
- Loading: skeleton
- Lesson: reading content
- Exercise: answering question
- Feedback: showing result (correct/incorrect + explanation)
- Module complete: celebration message + next module prompt
- Course complete: final score + certificate + feedback survey prompt

**Actions:**
- Navigate between lessons/exercises
- Submit exercise answer
- Continue to next module
- On course complete -> trigger feedback survey

---

### Chat Tutor

**Route:** `/empleado/chat`
**Role:** employee

AI tutor trained on company documents. The employee asks questions, gets answers grounded in internal knowledge with source citations.

**Sections:**
- **Message list** — conversation history, user messages right-aligned, tutor left-aligned
- **Input** — text field + send button
- **Citations** — each tutor response shows source document and section
- **Suggested prompts** — contextual suggestions based on current course ("Want to know more about X?")

**Data:**
- `POST /api/v1/chat` — send message, receive streamed response via SSE
- Response includes `citations: [{document, section, page}]`

**States:**
- Empty: welcome message + suggested first questions
- Streaming: tutor response appearing word by word (SSE)
- Error: model unavailable message

**Actions:**
- Send message
- Click citation -> open source document/section
- Click suggested prompt -> auto-send

---

### Skill Map

**Route:** `/empleado/skillmap`
**Role:** employee

Visual map of what the employee knows.

**Sections:**
- **Skills by category** — grouped by skill category (Ventas, Tecnologia, etc.)
- **Each skill** — name, level (low/medium/high), source (checkpoint vs manual), last assessed date
- **Progress indicators** — visual level representation per skill

**Data:**
- `GET /api/v1/users/me/skills` — skills with levels and categories

**States:**
- Empty: no skills tracked yet
- Populated: skills grouped by category

**Actions:**
- Click skill -> show history (which exercises/checkpoints contributed)

---

### Manual Viewer

**Route:** *not implemented* — there is no manual viewer page and no route for one
**Role:** employee

Reference material. Employees consult when they need to look something up.

**Sections:**
- **Table of contents** — navigable section list
- **Content** — manual content rendered by section
- **Search** — search within the manual

**Data:**
- `GET /api/v1/manuals/:id` — manual content

**States:**
- Loading: skeleton
- Populated: content with TOC

**Actions:**
- Navigate by section (TOC click)
- Search within manual
- Link to related course if exists

---

### Employee Settings

**Route:** `/empleado/ajustes`. El menú de cuenta y la navegación lateral enlazan esta pantalla
como «Preferencias de aprendizaje». El empleado puede cambiar presentación, detalle, tratamiento
de imágenes y accesibilidad sin repetir el onboarding.
**Role:** employee

**Sections:**
- **Profile** — name, email (read-only), change password
- **Learning profile** — select: Standard / Focus / Fast. One click, no configuration. Private (no one else sees it)
- **Accessibility** — optional presentation preferences stored in `users.accessibility`. Neutral, behavioural settings only ("shorter blocks of text", and similar): what the reader wants on screen, never a diagnosis. **No neurotype labels are collected, stored or offered.** Private, and never sent to the LLM — `short_blocks` reaches generation only as a smaller `effective_density`

**Data:**
- `GET /api/v1/users/me` — current profile
- `PUT /api/v1/users/me` — update profile, learning profile, accessibility

**States:**
- Form with current values pre-filled

**Actions:**
- Change learning profile -> immediate save
- Toggle accessibility flags -> immediate save
- Change password -> confirm current password first

---

## Admin

### Admin Dashboard

**Route:** `/admin`
**Role:** admin

Map of who knows what. Not a metrics dashboard. A talent map with action suggestions.

**Sections:**
- **Summary stats** — total employees, active courses, critical gaps count, employees needing attention
- **Skills matrix** — table: rows = skills, columns = employees, cells = level (color coded: green/yellow/red). Filterable by category, searchable
- **Alerts** — max 5, only actionable: deadline approaching with 0% progress, consecutive failures, certificate expiring, new employee with no courses, skill decay. Each alert has suggested action
- **Mentorship suggestions** — auto-detected: "Laura knows X (high). Carlos needs X (low). Pair them?"

**Data:**
- `GET /api/v1/skills/matrix` — full skills matrix
- `GET /api/v1/alerts` — active alerts
- `GET /api/v1/skills/mentorship-suggestions` — matching suggestions
- `GET /api/v1/stats` — summary numbers

**States:**
- Empty: no employees yet -> onboarding wizard (invite employees, create first course, assign)
- Populated: full dashboard with matrix, alerts, suggestions

**Actions:**
- Click cell in matrix -> see employee skill detail
- Click alert -> navigate to relevant action
- Accept/dismiss mentorship suggestion
- Navigate to employee detail, course creation, content management

---

### Employees

**Route:** `/admin/empleados`
**Role:** admin

List and manage employees.

**Sections:**
- **Employee list** — name, email, role, active courses count, skill coverage %, last active
- **Search and filter** — by name, role
- **Employee detail** (expandable or separate view) — skills, enrolled courses, activity history

**Data:**
- `GET /api/v1/users` — employee list with summary stats

**States:**
- Empty: no employees -> prompt to invite
- Populated: list/table

**Actions:**
- Click employee -> detail view
- Invite new employees -> in place on this screen (see *Invite Employees* below; there is no separate route)
- Deactivate employee
- Assign course to employee

---

### Invite Employees

**Route:** *not implemented as its own route* — inviting happens inside `/admin/empleados`
**Role:** admin

**Sections:**
- **Single invite** — name + email form
- **Bulk invite** — CSV upload (name, email columns)
- **Pending invitations** — list of sent invitations with status

**Data:**
- `POST /api/v1/users/invite` — send invitation
- `POST /api/v1/users/invite/bulk` — CSV upload
- `GET /api/v1/users/invitations` — pending invitations

**Actions:**
- Send single invitation
- Upload CSV
- Resend / cancel pending invitation

---

### Content Management ("Biblioteca")

**Route:** `/admin/contenido`
**Role:** admin

Overview of all content (courses + manuals).

**The user-facing name is "Biblioteca" / "Library" everywhere.** The route, `Content.tsx` and the
`content.*` message namespace keep the old name deliberately: renaming them touches bookmarks,
the onboarding tour and every screen that links here, and buys the user nothing. Only the visible
strings were unified — they used to say six different things.

**Sections:**
- **Content list** — title, type (course/manual), status (draft/published/archived), creation date, source document
- **Filter** — by type, by status
- **Create new** button -> `/admin/crear-curso`
- **Esquema** button per course -> `/admin/curso/:id/ajustes`

**Data:**
- `GET /api/v1/courses` — all courses
- `GET /api/v1/manuals` — all manuals

**Actions:**
- Click content -> edit/view
- Create new -> content creation flow
- Publish / archive / **unarchive**. Archiving hides a published course from learners and leaves
  every enrollment alone; unarchive puts it back to `published` with progress intact
- Move a course between folders; assign a whole folder to people

---

### Content Creation Flow

Multi-step flow for creating a course or manual.

**Route:** `/admin/crear-curso` — **one route, not five.** The steps below are internal state of
`CreateCourse.tsx` driven by a `StepIndicator`, so there is no per-step URL and no deep link into
a step. When the v2 flag allows it, step 1 gains an optional "define the schema" path; the v1
path stays available.

**Step 1 — Type selection**

Choose output: course + manual, or manual only. Upload source document (PDF) or start from scratch.

**Step 2 — Input**

If document uploaded: show processing status. If from scratch: title + topic + outcome fields.

**Step 3 — Preview**

Generated content preview. Modules, lessons, exercises listed. Admin reviews.

**Step 4 — Edit**

Admin can edit generated content: reorder modules, edit lesson text, modify exercises, remove/add content.

**Step 5 — Publish**

Set metadata: title, description, outcome, skills taught, assign to employees (optional). Publish.

**Data:**
- `POST /api/v1/documents` — upload source document
- `POST /api/v1/documents/:id/process` — trigger ingestion
- `POST /api/v1/courses/:id/generate` — trigger generation (deferred)
- `POST /api/v1/courses/:id/publish` — publish
- `PUT /api/v1/courses/:id` — edit content

---

### Admin Chat

**Route:** `/admin/chat`
**Role:** admin

AI assistant for admin tasks. Different from tutor — this one helps manage the platform.

**Sections:**
- Same layout as Chat Tutor
- Different context: knows about employees, courses, skills, content

**Data:**
- `POST /api/v1/chat/admin` — send message, SSE response

**Actions:**
- Same as Chat Tutor but with admin-scoped responses

---

### Admin Settings

**Route:** `/admin/ajustes`
**Role:** admin

**Sections:**
- **Company** — name, logo
- **Skills taxonomy** — manage categories and skills (add, rename, reorder, delete)
- **LLM configuration** — API endpoint, API key, model name (masked input for key)
- **User management defaults** — self-registration on/off, default learning profile

**Data:**
- `GET /api/v1/organizations/me` — current org settings
- `PUT /api/v1/organizations/me` — update settings
- `GET /api/v1/skills/categories` — taxonomy
- `POST/PUT/DELETE /api/v1/skills/categories` and `/api/v1/skills` — manage taxonomy

**Actions:**
- Update company info
- Add/edit/delete skill categories and skills
- Configure LLM provider
- Toggle self-registration

---

## Shared

### Layout

All authenticated screens share:

- **Sidebar** — navigation links grouped by role. Employee: Dashboard, My Courses, Skills, Chat, Manuals, Settings. Admin: Dashboard, Employees, Content, Chat, Settings. Collapsible
- **Header** — current page title, user name + avatar, role indicator, logout
- **Main content** — the screen content

Sidebar collapses to icons on mobile. Header stays fixed.

---

## Route Summary

**Routes are in Spanish.** The code is the source of truth here (`apps/skillnet-web/src/App.tsx`)
and the English paths this document used to list never existed. Decided in
`v2-dynamic-courses.md` §14.2 #8: follow the code; switching to English would be a mechanical
rename of `App.tsx` and the `Link`s, with no effect on the API.

| Route | Screen | Role |
|-------|--------|------|
| `/` | Redirect by role | public |
| `/login` | Login | public |
| `/setup` | First-run setup wizard | public |
| `/onboarding` | Learner profile wizard (v2) | employee |
| `/empleado/ajustes` | Preferencias de aprendizaje y accesibilidad | employee |
| `/empleado` | Employee Dashboard | employee |
| `/empleado/cursos` | My Courses | employee |
| `/empleado/curso/:id` | Course View | employee |
| `/empleado/curso/:id/nodo/:nodeId` | Node View (v2 dynamic course) | employee |
| `/empleado/skillmap` | Skill Map | employee |
| `/empleado/chat` | Chat Tutor | employee |
| `/admin` | Admin Dashboard | admin |
| `/admin/demo` | Showcase lesson | admin |
| `/admin/empleados` | Employees (invite lives inside) | admin |
| `/admin/talento` | Talent | admin |
| `/admin/contenido` | Content Management — "Biblioteca" in the UI | admin |
| `/admin/crear-curso` | Content Creation (all 5 steps, one route) | admin |
| `/admin/curso/:id` | Course Preview | admin |
| `/admin/curso/:id/ajustes` | Course Schema (v2) | admin |
| `/admin/curso/:id/esquema` | Redirects to `/admin/curso/:id/ajustes` | admin |
| `/admin/curso/:id/estudio` | Redirects to `/admin/probar-curso/:id` | admin |
| `/admin/probar-curso/:id` | Course View — the admin's test drive | admin |
| `/admin/probar-curso/:id/nodo/:nodeId` | Node View — the admin's test drive | admin |
| `/admin/chat` | Admin Chat | admin |
| `/admin/ajustes` | Admin Settings | admin |
| `/dev/motion` | Motion demo (development only) | public |
| `/dev/didact` | Didact component lab (development only) | admin |

Three of these belong to v2: `/onboarding`, `/empleado/curso/:id/nodo/:nodeId` and
`/admin/curso/:id/ajustes`. They are always mounted; whether they show v2 content depends on
the course, not on any global setting — a course that is not `dynamic`+`validated` is served in
its v1 format instead (`resolve_delivery`, see `v2-dynamic-courses.md` §10).

**A course is read from two of these, not one.** `/admin/probar-curso/:id` mounts the very
components the learner uses — `CourseView` and `NodeView` — inside `AdminLayout`, so the admin
tries the course without leaving their context. Anything inside a course therefore has to work
under both prefixes, and nothing inside one should rebuild the course URL by trimming the
current one: `src/lib/courseRoutes.ts` owns that shape and answers it from any depth. Written
down because the code did the trimming in four places, and the copy in the course map produced
`/…/curso/A/nodo/B/nodo/C` when it was opened from inside a lesson — no route matched, the
catch-all sent the learner to their dashboard, and clicking a lesson looked like clicking Home.

There is no employee settings page and no manual viewer page; both are specified above but
unbuilt.

### v2 entry points

Navigation into the v2 surfaces, all of it gated so nothing appears with the flag off:

| Where | What | Gate |
|---|---|---|
| `pages/admin/Content.tsx` | Per-course "Esquema" link | flag is `shadow` or `on` |
| `pages/admin/CoursePreview.tsx` | "Esquema" link | flag is `shadow` or `on` |
| `pages/admin/CourseSchema.tsx` | "← Volver al curso" back-link | always (it is inside the screen) |
| `pages/employee/MyCourses.tsx` | "Por nodos" badge on dynamic courses | `enrollment.delivery_mode` |
| `pages/employee/Dashboard.tsx` | "Por nodos" badge on dynamic courses | `enrollment.delivery_mode` |
| `components/layout/Header.tsx` | "Preferencias de aprendizaje" account-menu item, abre `/empleado/ajustes` | employee |

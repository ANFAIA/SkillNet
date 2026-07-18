# Frontend — AGENTS.md

## Overview

React SPA for SkillNet. Two roles: employee (learns, practices) and admin (manages content, employees, skills).

## Stack

React 19 + Vite + Tailwind v4 + React Router + TanStack Query + Lucide icons.

## Project structure

```
src/
├── main.tsx
├── App.tsx                    # Router setup
├── api/                       # API client and TanStack Query hooks
│   ├── client.ts              # Base fetch wrapper (handles cookies automatically)
│   ├── courses.ts             # useCourses, useCourse, useEnrollments...
│   ├── users.ts               # useMe, useUsers, useInvite...
│   ├── skills.ts              # useSkills, useSkillMatrix...
│   ├── exercises.ts           # useSubmitAttempt...
│   └── chat.ts                # useChat (SSE streaming)
├── components/
│   ├── layout/                # AppLayout, Sidebar, Header
│   ├── courses/               # CourseCard, ModuleList, LessonContent
│   ├── exercises/             # ExerciseRenderer, TestExercise, FillBlank...
│   ├── skills/                # SkillMatrix, SkillMap, SkillBadge
│   └── ui/                    # Button, Input, Card, Modal, Skeleton, EmptyState
├── pages/
│   ├── auth/                  # Login
│   ├── employee/              # Dashboard, MyCourses, CourseView, Chat, Skills, Settings
│   └── admin/                 # Dashboard, Employees, Invite, Content, Chat, Settings
├── hooks/                     # useAuth, useRole, useSSE
├── types/                     # TypeScript types matching data model
└── styles/
    └── index.css              # Tailwind imports + CSS variable tokens
```

## Routing

Fixed routes. Full list in `docs/design/screens.md`.

```tsx
// Public
/login

// Employee (requires auth, role=employee)
/dashboard
/courses
/courses/:id
/chat
/skills
/manuals/:id
/settings

// Admin (requires auth, role=admin)
/admin
/admin/users
/admin/users/invite
/admin/content
/admin/content/new          // 5-step flow: new, input, preview, edit, publish
/admin/chat
/admin/settings
```

## Data fetching

All server data through TanStack Query. No raw fetch in components.

```tsx
// Example: fetching courses
function MyCourses() {
  const { data: enrollments, isLoading } = useEnrollments()
  if (isLoading) return <Skeleton />
  return <CourseList enrollments={enrollments} />
}
```

API client is a thin fetch wrapper. No token headers — the browser sends the session cookie automatically.

```ts
// api/client.ts
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    credentials: 'include',  // sends cookie
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new ApiError(res.status, await res.json())
  return res.json()
}
```

## SSE streaming (chat)

Chat uses Server-Sent Events for streaming responses.

```ts
// api/chat.ts — pattern for SSE
function useChat() {
  const sendMessage = async (message: string, onToken: (token: string) => void) => {
    const res = await fetch('/api/v1/chat', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      onToken(decoder.decode(value))
    }
  }
  return { sendMessage }
}
```

## Component conventions

- One component per file. File name = component name
- Functional components only. No class components
- Props as destructured object, typed inline or with a `Props` type
- No `export default` on components — use named exports
- Colocate component-specific logic. Extract shared logic to `hooks/`

## Exercise rendering

Exercises have different types. One renderer component dispatches to type-specific components:

```tsx
function ExerciseRenderer({ exercise }: { exercise: Exercise }) {
  switch (exercise.type) {
    case 'test': return <TestExercise exercise={exercise} />
    case 'true_false': return <TrueFalseExercise exercise={exercise} />
    case 'fill_blank': return <FillBlankExercise exercise={exercise} />
    case 'order_steps': return <OrderStepsExercise exercise={exercise} />
    case 'practical_case': return <PracticalCaseExercise exercise={exercise} />
    case 'dialogue': return <DialogueExercise exercise={exercise} />
  }
}
```

## States every screen must handle

1. **Loading** — Skeleton matching the layout shape. No spinners
2. **Empty** — Helpful message + action. Not just "No data"
3. **Error** — Inline message. No full-page errors for API failures
4. **Populated** — Normal view

## Design

Follow `docs/design/design-system.md` strictly. Key rules:

- Use design tokens (CSS variables), not arbitrary Tailwind values
- No gratuitous gradients, rounded-2xl everywhere, or pastel icon backgrounds
- Visual hierarchy through spacing and weight, not color and decoration
- Consistent border radius, shadows, and spacing across all components

## Motion & Animations

Read `docs/design/motion-system.md` for the complete spec — it explains what we want, why, and has a prioritized backlog with context for each task.

**Key files:**
- `src/lib/motion.ts` — centralized presets (easing curves, durations, springs, variants). Import from here, never hardcode animation values inline
- `docs/design/motion-system.md` — full spec, research findings, and what needs to be done
- `src/pages/dev/MotionDemo.tsx` — interactive demo of all patterns at `/dev/motion`, use as visual reference

**What we're going for:** The app should feel like a native iOS app — transitions that flow, elements that morph into each other, physical feedback when you tap things. Not a website that loads pages.

**The L-frame layout:** The sidebar + header are blue (`frame-surface`) and the main content is white with `rounded-tl-xl`. The active nav item has a white pill that bleeds into the main content (no gap on the right edge). This fusion between the nav pill and the content area is a signature visual effect — the AdminSidebar currently breaks it with `right-4`, and the employee Sidebar has no animated pill at all.

## Mock data

During development without backend, use mock data files:

```
src/mocks/
├── courses.ts
├── users.ts
├── skills.ts
└── exercises.ts
```

TanStack Query hooks should work with both real API and mock data — swap the data source, not the hooks.

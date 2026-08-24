---
title: "Frontend-backend integration"
order: 23
section: "core"
---

## 10. Frontend-Backend Integration

> **Status: Draft.** Complete integration architecture for React frontend to FastAPI backend communication.

---

### 10.1 API Client Layer

#### Base client

A single fetch wrapper in `src/api/client.ts`. No token management -- the browser sends the `httpOnly` session cookie on every request via `credentials: 'include'`.

```ts
// src/api/client.ts

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: { detail: string; code?: string },
  ) {
    super(body.detail)
  }
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })

  if (res.status === 401) {
    // Session expired or not authenticated.
    // Do NOT redirect here -- let the global handler do it.
    throw new ApiError(401, { detail: 'Unauthorized' })
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(res.status, body)
  }

  // 204 No Content (e.g. DELETE responses)
  if (res.status === 204) return undefined as T

  return res.json()
}

// Convenience methods
export const get = <T>(path: string) => api<T>(path)

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) })

export const del = <T>(path: string) =>
  api<T>(path, { method: 'DELETE' })

// Multipart upload (no Content-Type -- browser sets boundary)
export const upload = <T>(path: string, formData: FormData) =>
  api<T>(path, {
    method: 'POST',
    headers: {},  // override Content-Type removal
    body: formData,
  })
```

The `upload` function intentionally omits `Content-Type` so the browser can set `multipart/form-data` with the correct boundary.

#### Query key conventions

All query keys follow a hierarchical array pattern. This makes invalidation predictable.

```ts
// Pattern: [domain, resource?, id?, sub-resource?]

// Lists
['users']                              // all users
['courses']                            // all courses
['enrollments']                        // my enrollments
['skills']                             // all skills

// Single entities
['courses', courseId]                   // one course with modules/lessons/exercises
['manuals', manualId]                  // one manual
['users', userId]                      // one user detail

// Sub-resources
['users', 'me']                        // current user
['users', 'me', 'today']              // today's actions (dashboard)
['users', 'me', 'skills']             // my skill levels
['users', 'me', 'activity']           // my recent activity
['enrollments', enrollmentId]          // one enrollment

// Admin-specific
['skills', 'matrix']                   // skills matrix
['skills', 'mentorship-suggestions']   // mentor matching
['alerts']                             // admin alerts
['stats']                              // summary stats
['organizations', 'me']               // org settings
['generation-jobs', jobId]             // generation job status

// Filtered lists use object in key
['enrollments', { status: 'in_progress' }]
['courses', { status: 'published' }]
```

Invalidation examples:
- After creating a course: invalidate `['courses']`
- After submitting an exercise: invalidate `['enrollments', enrollmentId]`, `['users', 'me', 'skills']`, `['users', 'me', 'activity']`
- After updating org settings: invalidate `['organizations', 'me']`

#### Hook organization (by domain)

Each file in `src/api/` exports TanStack Query hooks for one domain. All hooks return standard TanStack Query objects (`{ data, isLoading, error }`).

```
src/api/
├── client.ts          # Base fetch wrapper (above)
├── auth.ts            # useLogin, useLogout, useMe
├── courses.ts         # useCourses, useCourse, useCreateCourse, usePublishCourse
├── enrollments.ts     # useEnrollments, useEnrollment
├── exercises.ts       # useSubmitAttempt
├── skills.ts          # useSkills, useMySkills, useSkillMatrix, useMentorshipSuggestions
├── users.ts           # useUsers, useInvite, useBulkInvite
├── documents.ts       # useUploadDocument, useProcessDocument
├── manuals.ts         # useManual, useManuals
├── chat.ts            # useChat, useAdminChat (SSE -- different pattern)
├── generation.ts      # useGenerationJob (polling)
├── settings.ts        # useOrgSettings, useUpdateOrgSettings, useUpdateProfile
└── stats.ts           # useStats, useAlerts
```

**auth.ts** example:

```ts
// src/api/auth.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { User } from '../types'

export function useMe() {
  return useQuery({
    queryKey: ['users', 'me'],
    queryFn: () => get<User>('/users/me'),
    retry: false,        // don't retry 401s
    staleTime: 5 * 60_000,  // 5 minutes -- user data rarely changes mid-session
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      post<User>('/auth/login', credentials),
    onSuccess: (user) => {
      queryClient.setQueryData(['users', 'me'], user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post('/auth/logout'),
    onSuccess: () => {
      queryClient.clear()  // wipe all cached data on logout
      window.location.href = '/login'
    },
  })
}
```

**courses.ts** example (with optimistic update on publish):

```ts
// src/api/courses.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { Course, CourseDetail } from '../types'

export function useCourses(filters?: { status?: string }) {
  return useQuery({
    queryKey: ['courses', filters ?? {}],
    queryFn: () => get<Course[]>(`/courses${filters?.status ? `?status=${filters.status}` : ''}`),
  })
}

export function useCourse(id: string) {
  return useQuery({
    queryKey: ['courses', id],
    queryFn: () => get<CourseDetail>(`/courses/${id}`),
    enabled: !!id,
  })
}

export function usePublishCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: string) => post(`/courses/${courseId}/publish`),
    onMutate: async (courseId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['courses', courseId] })

      // Snapshot previous value
      const previous = queryClient.getQueryData<CourseDetail>(['courses', courseId])

      // Optimistically update status
      if (previous) {
        queryClient.setQueryData(['courses', courseId], {
          ...previous,
          status: 'published',
        })
      }

      return { previous }
    },
    onError: (_err, courseId, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(['courses', courseId], context.previous)
      }
    },
    onSettled: (_data, _err, courseId) => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ['courses', courseId] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}
```

#### Mutation patterns

Not every mutation needs optimistic updates. The rule:

| Action | Optimistic? | Why |
|--------|-------------|-----|
| Submit exercise attempt | **No** | Score comes from server. Can't predict it |
| Publish/archive course | **Yes** | Status change is predictable. Instant UI feedback matters |
| Update user profile | **Yes** | User typed the value, it's what they expect to see |
| Invite employee | **No** | Server validates email, may reject |
| Delete content | **Yes** | Immediate removal from list, rollback if fails |
| Upload document | **No** | Server processes file, status is server-determined |

Standard mutation pattern (no optimistic update):

```ts
export function useSubmitAttempt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ exerciseId, answer }: { exerciseId: string; answer: unknown }) =>
      post<AttemptResult>(`/exercises/${exerciseId}/attempt`, { answer }),
    onSuccess: (_data, { exerciseId }) => {
      // Invalidate related queries so dashboard/skills/enrollment update
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['users', 'me', 'skills'] })
      queryClient.invalidateQueries({ queryKey: ['users', 'me', 'activity'] })
    },
  })
}
```

#### Error handling and retry

Global configuration in the `QueryClient`:

```ts
// src/main.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Never retry 401, 403, 404
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          return false
        }
        // Retry network errors and 5xx up to 3 times
        return failureCount < 3
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      staleTime: 30_000,        // 30 seconds default
      gcTime: 5 * 60_000,       // 5 minutes garbage collection
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: false,  // mutations are never retried automatically
    },
  },
})
```

#### Authentication: 401 handling

A global query callback redirects to login on 401. This lives in the QueryClient config, not in individual hooks.

```ts
// src/main.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status === 401) return false
        return failureCount < 3
      },
    },
  },
})

// Global error handler via QueryCache
queryClient.getQueryCache().config.onError = (error) => {
  if (error instanceof ApiError && error.status === 401) {
    // Clear all cached data and redirect
    queryClient.clear()
    window.location.href = '/login'
  }
}

queryClient.getMutationCache().config.onError = (error) => {
  if (error instanceof ApiError && error.status === 401) {
    queryClient.clear()
    window.location.href = '/login'
  }
}
```

The `useMe()` query is called once in the root layout. If it returns 401, the redirect fires. Every subsequent query inherits this behavior. No auth logic in page components.

#### Route protection

A wrapper component checks auth before rendering protected pages:

```ts
// src/hooks/useAuth.ts
export function useAuth() {
  const { data: user, isLoading, error } = useMe()
  return { user, isLoading, isAuthenticated: !!user, error }
}
```

```tsx
// src/components/layout/ProtectedRoute.tsx
function ProtectedRoute({ role, children }: { role?: 'admin' | 'employee'; children: ReactNode }) {
  const { user, isLoading } = useAuth()

  if (isLoading) return <AppSkeleton />
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to="/dashboard" replace />

  return children
}
```

---

### 10.2 SSE Integration for Chat

#### Architecture

Chat uses `fetch` with `ReadableStream`, not `EventSource`. Reasons:
- `EventSource` only supports GET. Chat needs to POST the message body
- `fetch` with streaming lets us send the message and read the response in a single request
- AbortController gives clean cancellation

#### SSE event format from backend

The backend sends SSE-formatted events through a `StreamingResponse`:

```
event: token
data: {"content": "El plazo"}

event: token
data: {"content": " de devolucion"}

event: token
data: {"content": " es de 30 dias"}

event: citations
data: {"citations": [{"document": "Manual Devoluciones", "section": "Plazos", "page": 3}]}

event: suggestions
data: {"prompts": ["What exceptions exist?", "Can returns be done online?"]}

event: done
data: {}

event: error
data: {"detail": "Model unavailable"}
```

Event types:
- `token` -- incremental text fragment
- `citation` -- source reference (emitted after relevant text)
- `done` -- stream complete
- `error` -- generation failed

#### Chat hook

```ts
// src/api/chat.ts

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  suggestions?: string[]
  isStreaming?: boolean
}

interface Citation {
  document: string
  section: string
  page?: number
}

export function useChat(endpoint: '/chat' | '/chat/admin' = '/chat') {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (text: string) => {
    // Add user message immediately
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])

    // Create placeholder for assistant response
    const assistantId = crypto.randomUUID()
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      citations: [],
      isStreaming: true,
    }
    setMessages((prev) => [...prev, assistantMsg])
    setIsStreaming(true)

    // Create abort controller for cancellation
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch(`/api/v1${endpoint}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      })

      if (!res.ok) {
        throw new Error(`Chat request failed: ${res.status}`)
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''  // keep incomplete line in buffer

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (eventType === 'token') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + data.content }
                    : m,
                ),
              )
            } else if (eventType === 'citation') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, citations: [...(m.citations ?? []), data] }
                    : m,
                ),
              )
            } else if (eventType === 'citations') {
              // Batch citations event: data is an array of citation objects
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, citations: [...(m.citations ?? []), ...data] }
                    : m,
                ),
              )
            } else if (eventType === 'suggestions') {
              // Batch suggestions event: data is an array of follow-up suggestions
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, suggestions: data }
                    : m,
                ),
              )
            } else if (eventType === 'error') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: data.detail, isStreaming: false }
                    : m,
                ),
              )
            }

            eventType = ''
          }
        }
      }

      // Mark streaming complete
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false } : m,
        ),
      )
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // User cancelled -- mark the partial response as complete
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m,
          ),
        )
      } else {
        // Real error -- show error in the assistant message
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: 'Error connecting to the assistant. Try again.', isStreaming: false }
              : m,
          ),
        )
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }, [endpoint])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(() => {
    setMessages([])
  }, [])

  return { messages, sendMessage, cancel, clear, isStreaming }
}
```

#### Cancellation

The user can cancel a streaming response in two ways:
1. Click a "Stop" button that appears during streaming (calls `cancel()`)
2. Navigate away from the chat page (component unmount aborts via cleanup)

```tsx
// In the Chat page component
useEffect(() => {
  return () => {
    // If unmounting while streaming, abort
    cancel()
  }
}, [cancel])
```

#### Reconnection

SSE reconnection does not apply here because each message is a separate `POST` + stream. If the stream drops mid-response:
- The partial response stays visible in the UI
- The `isStreaming` flag is cleared
- An error message appears below the partial response: "Response interrupted. Send your question again."
- No automatic retry -- the user decides whether to resend

#### Chat component consumption

```tsx
// src/pages/employee/Chat.tsx

function Chat() {
  const { messages, sendMessage, cancel, isStreaming } = useChat()
  const [input, setInput] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return
    sendMessage(input.trim())
    setInput('')
  }

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && <ChatWelcome />}
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-[--color-border] p-4 flex gap-3">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          disabled={isStreaming}
          className="flex-1"
        />
        {isStreaming ? (
          <Button variant="secondary" onClick={cancel} type="button">Stop</Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>Send</Button>
        )}
      </form>
    </div>
  )
}
```

---

### 10.3 Real-Time Progress for Generation Jobs

#### The problem

Content generation is a multi-step pipeline (pending -> extracting -> structuring -> generating -> reviewing -> published/failed). Each step takes seconds to minutes. The admin needs to see where the pipeline is right now.

#### Approach: SSE for generation progress

The content creation flow opens an SSE connection after triggering generation. This reuses the same SSE infrastructure from chat, with a different event format.

**Triggering generation:**

```ts
// src/api/generation.ts
export function useGenerateContent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: { courseId: string; documentId?: string; outputType: 'course_and_manual' | 'manual_only'; title?: string }) =>
      post<{ jobId: string }>(`/courses/${params.courseId}/generate`, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}
```

**Tracking progress via SSE:**

```ts
// src/api/generation.ts

type GenerationStep = 'pending' | 'extracting' | 'structuring' | 'generating' | 'reviewing' | 'published' | 'failed'

interface GenerationProgress {
  step: GenerationStep
  message?: string       // human-readable status ("Extracting key topics...")
  courseId?: string       // set when published
  manualId?: string       // set when published
  error?: string          // set when failed
}

export function useGenerationProgress(jobId: string | null) {
  const [progress, setProgress] = useState<GenerationProgress>({ step: 'pending' })
  const [isActive, setIsActive] = useState(false)

  useEffect(() => {
    if (!jobId) return

    setIsActive(true)
    const controller = new AbortController()

    async function connect() {
      try {
        const res = await fetch(`/api/v1/generation-jobs/${jobId}/progress`, {
          credentials: 'include',
          signal: controller.signal,
        })

        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              const data = JSON.parse(line.slice(6))

              if (eventType === 'progress') {
                setProgress(data)
              } else if (eventType === 'completed') {
                setProgress(data)
                setIsActive(false)
              } else if (eventType === 'error') {
                setProgress({ step: 'failed', error: data.detail })
                setIsActive(false)
              }

              eventType = ''
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setProgress({ step: 'failed', error: 'Connection lost. Refresh to check status.' })
          setIsActive(false)
        }
      }
    }

    connect()
    return () => controller.abort()
  }, [jobId])

  return { progress, isActive }
}
```

**Fallback polling (if SSE connection drops):**

If the SSE connection fails or drops, the UI falls back to polling. The generation job's current step is always available via REST:

```ts
// Fallback: poll generation status
export function useGenerationJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['generation-jobs', jobId],
    queryFn: () => get<GenerationProgress>(`/generation-jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const step = query.state.data?.step
      // Stop polling when terminal
      if (step === 'published' || step === 'failed') return false
      return 3000  // poll every 3 seconds while active
    },
  })
}
```

The UI component tries SSE first and only uses polling as fallback.

#### SSE event format from backend

```
event: progress
data: {"step": "extracting", "message": "Extracting key topics from the document..."}

event: progress
data: {"step": "structuring", "message": "Organizing into 4 modules..."}

event: progress
data: {"step": "generating", "message": "Writing content for module 1 of 4..."}

event: progress
data: {"step": "reviewing", "message": "Checking quality and coverage..."}

event: completed
data: {"step": "published", "courseId": "uuid", "manualId": "uuid"}

event: error
data: {"step": "failed", "detail": "LLM provider returned an error. Check your API key."}
```

#### Progress visualization

A step indicator component shows the pipeline state:

```tsx
// src/components/generation/GenerationProgress.tsx

const STEPS: { key: GenerationStep; label: string }[] = [
  { key: 'pending', label: 'Queued' },
  { key: 'extracting', label: 'Extracting topics' },
  { key: 'structuring', label: 'Designing structure' },
  { key: 'generating', label: 'Writing content' },
  { key: 'reviewing', label: 'Quality review' },
  { key: 'published', label: 'Published' },
]

const STEP_ORDER = STEPS.map((s) => s.key)

function GenerationProgress({ progress }: { progress: GenerationProgress }) {
  const currentIndex = STEP_ORDER.indexOf(progress.step)
  const isFailed = progress.step === 'failed'

  return (
    <div className="space-y-4">
      {/* Step indicators */}
      <div className="flex items-center gap-2">
        {STEPS.map((step, i) => {
          const isCompleted = i < currentIndex
          const isCurrent = i === currentIndex && !isFailed
          const isPending = i > currentIndex

          return (
            <Fragment key={step.key}>
              {i > 0 && (
                <div className={`flex-1 h-0.5 ${isCompleted ? 'bg-[--color-primary]' : 'bg-[--color-bg-muted]'}`} />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                    isCompleted
                      ? 'bg-[--color-primary] text-white'
                      : isCurrent
                        ? 'border-2 border-[--color-primary] text-[--color-primary]'
                        : 'border border-[--color-border] text-[--color-text-muted]'
                  }`}
                >
                  {isCompleted ? <Check className="w-4 h-4" /> : i + 1}
                </div>
                <span className={`text-xs ${isCurrent ? 'text-[--color-text] font-medium' : 'text-[--color-text-muted]'}`}>
                  {step.label}
                </span>
              </div>
            </Fragment>
          )
        })}
      </div>

      {/* Status message */}
      {progress.message && (
        <p className="text-sm text-[--color-text-secondary]">{progress.message}</p>
      )}

      {/* Error state */}
      {isFailed && progress.error && (
        <div className="text-sm text-[--color-danger] border border-red-200 rounded-md p-3">
          {progress.error}
        </div>
      )}
    </div>
  )
}
```

The step indicator is a horizontal connected line with numbered circles. Completed steps fill with the primary color. The current step has an outlined circle. Pending steps are muted. On failure, the current step shows red and displays the error message.

#### Integration with the content creation flow

Step 3 of the creation flow (`/admin/content/new/preview`) triggers generation and shows the progress component. When the pipeline reaches `published`, the page transitions to step 4 (edit) with the generated content loaded.

```tsx
// In ContentCreationPreview page
const { mutate: generate, data: job } = useGenerateContent()
const { progress, isActive } = useGenerationProgress(job?.jobId ?? null)

// When user clicks "Generate":
generate({ documentId, outputType: 'course_and_manual' })

// Show progress while active:
{isActive && <GenerationProgress progress={progress} />}

// When published, navigate to edit step:
useEffect(() => {
  if (progress.step === 'published' && progress.courseId) {
    navigate(`/admin/content/new/edit?courseId=${progress.courseId}`)
  }
}, [progress])
```

---

### 10.4 Level 2 (Declarative UI) Integration

#### How it works

The backend (or agent) emits a compact spec describing *what* to show. The frontend has a renderer component that maps the spec to React components. The user never knows the UI was described by a spec -- it looks like any other screen.

#### Spec format

The backend returns the spec as a JSON structure (not raw A2TL-Web text). The JSON format is the transport layer; the A2TL-Web text format exists for the LLM authoring side.

```json
{
  "version": "1",
  "layout": "stack",
  "children": [
    { "type": "heading", "level": 1, "text": "Training Dashboard" },
    { "type": "text", "text": "Week 2 progress for kitchen team", "variant": "dim" },
    {
      "type": "metrics",
      "columns": 3,
      "items": [
        { "label": "Completed", "value": "12/20", "color": "green", "detail": "On track" },
        { "label": "Avg Score", "value": "87%", "color": "primary", "detail": "+5% vs last week" },
        { "label": "Time Spent", "value": "4.2h", "color": "warning", "detail": "Below target" }
      ]
    },
    {
      "type": "table",
      "title": "Pending Exercises",
      "columns": ["Module", "Exercise", "Due"],
      "rows": [
        ["Safety", "Fire extinguisher drill", "Tomorrow"],
        ["Service", "Customer complaint handling", "Friday"]
      ]
    }
  ]
}
```

#### Renderer component

The renderer walks the spec tree and maps each node to a React component from the design system.

```tsx
// src/components/renderer/SpecRenderer.tsx

interface SpecNode {
  type: string
  [key: string]: unknown
}

interface RendererSpec {
  version: string
  layout: 'stack' | 'grid'
  children: SpecNode[]
}

const NODE_RENDERERS: Record<string, (node: SpecNode) => ReactNode> = {
  heading: (node) => {
    const Tag = `h${node.level}` as keyof JSX.IntrinsicElements
    const className = node.level === 1
      ? 'text-2xl font-semibold text-[--color-text]'
      : 'text-lg font-semibold text-[--color-text]'
    return <Tag className={className}>{node.text as string}</Tag>
  },

  text: (node) => (
    <p className={`text-sm ${node.variant === 'dim' ? 'text-[--color-text-muted]' : 'text-[--color-text-secondary]'}`}>
      {node.text as string}
    </p>
  ),

  metrics: (node) => {
    const items = node.items as Array<{ label: string; value: string; color: string; detail: string }>
    return (
      <div className={`grid grid-cols-${node.columns ?? 3} gap-4`}>
        {items.map((item, i) => (
          <MetricCard key={i} label={item.label} value={item.value} detail={item.detail} />
        ))}
      </div>
    )
  },

  table: (node) => {
    const columns = node.columns as string[]
    const rows = node.rows as string[][]
    return (
      <div>
        {node.title && <h3 className="text-base font-medium text-[--color-text] mb-3">{node.title as string}</h3>}
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[--color-border]">
              {columns.map((col) => (
                <th key={col} className="text-left py-2 px-3 text-xs text-[--color-text-secondary] font-medium">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-[--color-border]">
                {row.map((cell, j) => (
                  <td key={j} className="py-2 px-3">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  },

  // Additional node types: progress_bar, skill_chart, alert_list, etc.
  // Each maps to existing design system components.
}

export function SpecRenderer({ spec }: { spec: RendererSpec }) {
  return (
    <div className={spec.layout === 'grid' ? 'grid grid-cols-2 gap-6' : 'space-y-6'}>
      {spec.children.map((node, i) => {
        const render = NODE_RENDERERS[node.type]
        if (!render) {
          console.warn(`Unknown spec node type: ${node.type}`)
          return null
        }
        return <Fragment key={i}>{render(node)}</Fragment>
      })}
    </div>
  )
}
```

#### Use cases

Level 2 applies where content varies but structure is predictable:

| Screen | What the spec describes |
|--------|------------------------|
| Admin Dashboard widgets | Skills matrix summary, alerts list, stats cards. The agent decides what metrics to highlight based on current data |
| Progress reports | Employee progress visualization customized by what the admin asked for ("Show me who's behind") |
| Skill gap visualizations | Charts and tables adapted to the specific skills and employees in question |
| Course summaries | Generated overview of a course's content, adapted to who's viewing it |

#### How the backend sends specs

The spec comes as part of the regular API response. No special transport needed:

```ts
// Example: admin dashboard might include declarative widgets
interface DashboardResponse {
  stats: SummaryStats           // Level 1: static data for pre-built components
  matrix: SkillMatrixData       // Level 1: static data
  alerts: Alert[]               // Level 1: static data
  agentWidget?: RendererSpec    // Level 2: agent-generated spec (optional)
}
```

When the agent generates a spec, the frontend checks if `agentWidget` is present and renders it with `SpecRenderer`. If not, the page renders only the static Level 1 sections.

---

### 10.5 Level 3 (Generative UI) Isolation

#### When Level 3 is used

Only for personalized lessons where content, context, and user variability are all high. Specifically:
- Adaptive lesson content generated for a specific learner at a specific skill level
- Interactive tutoring responses that include diagrams, visual explanations, or custom layouts
- Agent responses that go beyond text (generated interactive widgets, step-by-step walkthroughs)

Most of SkillNet is Level 1 and 2. Level 3 is the exception.

#### Isolation method: iframe with srcdoc

`iframe` with `srcdoc`, not shadow DOM. Reasons:
- **Complete CSS isolation.** Shadow DOM still inherits some CSS (font, color). An iframe is a fully separate document
- **Script isolation.** Agent-generated JS cannot access the parent window's DOM, variables, or cookies
- **Security.** The `sandbox` attribute restricts capabilities to exactly what's needed
- **Simpler error containment.** If generated code crashes, only the iframe breaks

```tsx
// src/components/renderer/GeneratedContent.tsx

interface GeneratedContentProps {
  html: string
  onEvent?: (event: GeneratedContentEvent) => void
}

interface GeneratedContentEvent {
  type: string
  payload: unknown
}

export function GeneratedContent({ html, onEvent }: GeneratedContentProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  // Listen for messages from generated content
  useEffect(() => {
    if (!onEvent) return

    const handleMessage = (event: MessageEvent) => {
      // Only accept messages from our iframe
      if (event.source !== iframeRef.current?.contentWindow) return

      // Validate message shape
      if (event.data?.source === 'skillnet-generated' && event.data?.type) {
        onEvent({
          type: event.data.type,
          payload: event.data.payload,
        })
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [onEvent])

  // Inject communication bridge into HTML
  const wrappedHtml = wrapWithBridge(html)

  return (
    <iframe
      ref={iframeRef}
      srcDoc={wrappedHtml}
      sandbox="allow-scripts"
      className="w-full border-0"
      style={{ minHeight: '400px' }}
      title="Generated content"
    />
  )
}
```

#### Sandbox restrictions

The iframe `sandbox` attribute is set to `allow-scripts` only. This means:
- Scripts can run (needed for interactive exercises)
- No form submission to external URLs
- No popups
- No access to parent page cookies, localStorage, or DOM
- No navigation of the parent page
- No same-origin access to the parent document

If generated content needs to submit an exercise answer, it uses `postMessage`.

#### Sanitization

HTML sanitization happens server-side before sending to the frontend. The backend uses a whitelist approach:

**Allowed:** Standard HTML elements, CSS (inline styles and `<style>` blocks), Chart.js / vanilla JS for interactivity.

**Stripped:** `<script src="external">` (no external script loading), `<iframe>` (no nested iframes), `<form action="...">` (no form submissions), `<a href="javascript:">` (no JS in links), any `on*` attributes except through the bridge.

The frontend adds a second layer by using `srcdoc` in a sandboxed iframe, which prevents any remaining attack vectors.

#### Communication: postMessage bridge

The generated HTML includes a tiny bridge script that lets it send events to the parent app:

```ts
// src/components/renderer/bridge.ts

function wrapWithBridge(html: string): string {
  const bridge = `
<script>
  window.skillnet = {
    emit(type, payload) {
      window.parent.postMessage(
        { source: 'skillnet-generated', type, payload },
        '*'
      );
    }
  };
</script>`

  // Inject bridge before closing </head> or at the start of <body>
  if (html.includes('</head>')) {
    return html.replace('</head>', `${bridge}</head>`)
  }
  return `${bridge}${html}`
}
```

Usage in generated HTML (the agent includes these calls):

```html
<!-- Inside generated lesson content -->
<button onclick="skillnet.emit('exercise-answer', { questionId: 'q1', answer: 2 })">
  Submit Answer
</button>

<button onclick="skillnet.emit('navigate', { to: 'next-lesson' })">
  Next Lesson
</button>
```

The parent app handles these events:

```tsx
// In CourseView page
<GeneratedContent
  html={lessonHtml}
  onEvent={(event) => {
    if (event.type === 'exercise-answer') {
      submitAttempt.mutate(event.payload)
    } else if (event.type === 'navigate' && event.payload.to === 'next-lesson') {
      navigateToNextLesson()
    }
  }}
/>
```

#### Iframe height auto-resize

Generated content varies in length. The iframe should resize to fit:

```ts
// Added to the bridge script
const resizeObserver = new ResizeObserver(() => {
  window.parent.postMessage(
    { source: 'skillnet-generated', type: 'resize', payload: { height: document.body.scrollHeight } },
    '*'
  );
});
resizeObserver.observe(document.body);
```

The parent component handles the resize event:

```tsx
// In GeneratedContent component
const [height, setHeight] = useState(400)

// In the message handler:
if (event.data.type === 'resize') {
  setHeight(event.data.payload.height)
}

// On the iframe:
style={{ height: `${height}px` }}
```

---

### 10.6 File Upload

#### Upload flow

File upload is used in two places:
1. **Content creation** -- admin uploads PDFs to generate courses/manuals
2. **Employee invite** -- admin uploads CSV for bulk invite

Both use the same underlying upload component and API pattern.

#### Upload component

```tsx
// src/components/ui/FileUploadZone.tsx

interface FileUploadZoneProps {
  accept: string                    // e.g. '.pdf,.docx' or '.csv'
  maxFiles?: number                 // default 1
  maxSizeMB?: number                // default 20
  onFilesSelected: (files: File[]) => void
  children?: ReactNode              // custom drop zone content
}

export function FileUploadZone({
  accept,
  maxFiles = 1,
  maxSizeMB = 20,
  onFilesSelected,
  children,
}: FileUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFiles = (files: FileList | File[]): File[] => {
    const valid: File[] = []
    const newErrors: string[] = []
    const fileArray = Array.from(files)

    if (fileArray.length > maxFiles) {
      newErrors.push(`Maximum ${maxFiles} file${maxFiles > 1 ? 's' : ''} allowed`)
      setErrors(newErrors)
      return []
    }

    const allowedExtensions = accept.split(',').map((ext) => ext.trim().toLowerCase())

    for (const file of fileArray) {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()

      if (!allowedExtensions.includes(ext)) {
        newErrors.push(`${file.name}: unsupported file type`)
        continue
      }

      if (file.size > maxSizeMB * 1024 * 1024) {
        newErrors.push(`${file.name}: exceeds ${maxSizeMB}MB limit`)
        continue
      }

      valid.push(file)
    }

    setErrors(newErrors)
    return valid
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const valid = validateFiles(e.dataTransfer!.files)
    if (valid.length) onFilesSelected(valid)
  }

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return
    const valid = validateFiles(e.target.files)
    if (valid.length) onFilesSelected(valid)
    e.target.value = ''  // reset so same file can be selected again
  }

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          isDragOver
            ? 'border-[--color-primary] bg-[--color-primary-subtle]'
            : 'border-[--color-border] hover:border-[--color-border-strong]'
        }`}
      >
        {children ?? (
          <div className="space-y-2">
            <Upload className="w-5 h-5 mx-auto text-[--color-text-muted]" />
            <p className="text-sm text-[--color-text-secondary]">
              Drop files here or click to browse
            </p>
            <p className="text-xs text-[--color-text-muted]">
              {accept.replace(/\./g, '').toUpperCase()} up to {maxSizeMB}MB
            </p>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={maxFiles > 1}
          onChange={handleChange}
          className="hidden"
        />
      </div>

      {/* Validation errors */}
      {errors.length > 0 && (
        <div className="mt-2 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-xs text-[--color-danger]">{err}</p>
          ))}
        </div>
      )}
    </div>
  )
}
```

#### Upload with progress tracking

```ts
// src/api/documents.ts

interface UploadProgress {
  file: File
  progress: number        // 0-100
  status: 'uploading' | 'processing' | 'ready' | 'error'
  documentId?: string
  error?: string
}

export function useUploadDocument() {
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const queryClient = useQueryClient()

  const uploadFile = useCallback(async (file: File) => {
    const entry: UploadProgress = { file, progress: 0, status: 'uploading' }
    setUploads((prev) => [...prev, entry])

    const formData = new FormData()
    formData.append('file', file)

    try {
      // Use XMLHttpRequest for progress events (fetch doesn't support upload progress)
      const result = await new Promise<{ id: string }>((resolve, reject) => {
        const xhr = new XMLHttpRequest()

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100)
            setUploads((prev) =>
              prev.map((u) => u.file === file ? { ...u, progress: pct } : u),
            )
          }
        })

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText))
          } else {
            reject(new Error(JSON.parse(xhr.responseText).detail ?? 'Upload failed'))
          }
        })

        xhr.addEventListener('error', () => reject(new Error('Network error')))

        xhr.open('POST', '/api/v1/documents')
        xhr.withCredentials = true
        xhr.send(formData)
      })

      setUploads((prev) =>
        prev.map((u) =>
          u.file === file
            ? { ...u, progress: 100, status: 'processing', documentId: result.id }
            : u,
        ),
      )

      queryClient.invalidateQueries({ queryKey: ['documents'] })
      return result

    } catch (err) {
      setUploads((prev) =>
        prev.map((u) =>
          u.file === file
            ? { ...u, status: 'error', error: (err as Error).message }
            : u,
        ),
      )
      throw err
    }
  }, [queryClient])

  const uploadFiles = useCallback(async (files: File[]) => {
    // Upload sequentially to avoid overwhelming the server
    const results = []
    for (const file of files) {
      results.push(await uploadFile(file))
    }
    return results
  }, [uploadFile])

  const clearUploads = useCallback(() => setUploads([]), [])

  return { uploadFile, uploadFiles, uploads, clearUploads }
}
```

#### Upload progress display

```tsx
// src/components/upload/UploadList.tsx

function UploadList({ uploads }: { uploads: UploadProgress[] }) {
  return (
    <div className="space-y-2">
      {uploads.map((upload, i) => (
        <div key={i} className="flex items-center gap-3 text-sm">
          <FileText className="w-4 h-4 text-[--color-text-muted] shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="truncate text-[--color-text]">{upload.file.name}</p>
            {upload.status === 'uploading' && (
              <ProgressBar value={upload.progress} />
            )}
            {upload.status === 'processing' && (
              <p className="text-xs text-[--color-text-muted]">Processing...</p>
            )}
            {upload.status === 'error' && (
              <p className="text-xs text-[--color-danger]">{upload.error}</p>
            )}
          </div>
          {upload.status === 'ready' && (
            <Check className="w-4 h-4 text-[--color-success] shrink-0" />
          )}
        </div>
      ))}
    </div>
  )
}
```

#### Validation summary

| Check | Client-side | Server-side |
|-------|-------------|-------------|
| File extension | `.pdf`, `.docx`, `.md`, `.txt` | Same check + magic bytes verification |
| File size | 20MB max per file | Same limit enforced |
| File count | Max 5 files per upload batch | Same limit |
| MIME type | Not checked (unreliable) | Checked via `python-magic` |
| Content scan | Not possible | Malware scan if available |
| CSV format (invite) | Extension only | Column validation (name, email required) |

The server rejects files that pass client validation but fail server checks (e.g., a `.pdf` that is actually a `.exe`). The client shows the server error message inline.

---

### 10.7 Offline Considerations

#### What works offline

SkillNet is primarily an online tool. The self-hosted deployment runs on the company's network, so "offline" means the server is unreachable (network issue, server down).

| Feature | Offline behavior |
|---------|-----------------|
| **Catalog courses (already installed)** | Content is in PostgreSQL on the local server. If the server is up but internet is down, courses work. If the server itself is down, nothing works |
| **AI features (chat, generation)** | Require LLM API access. Offline only if using local model (Ollama). Otherwise, show "AI features require internet connection" |
| **Static pages (login, settings, nav)** | Served from the frontend. If the frontend bundle is cached, the shell loads. But API calls will fail |

#### Service worker strategy

A minimal service worker for the frontend shell. The goal is not full offline support -- it is fast repeat loads and graceful degradation when the backend is temporarily unreachable.

```ts
// src/service-worker.ts

// Cache the app shell (HTML, CSS, JS, fonts, icons)
const SHELL_CACHE = 'skillnet-shell-v1'
const SHELL_URLS = [
  '/',
  '/index.html',
  // Vite generates hashed filenames -- these are cached on first load
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  // API calls: network-only. Never serve stale API data from cache.
  if (request.url.includes('/api/')) {
    event.respondWith(fetch(request))
    return
  }

  // App shell: stale-while-revalidate.
  // Serve cached version immediately, fetch fresh version in background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const fetchPromise = fetch(request).then((response) => {
        const cache = caches.open(SHELL_CACHE)
        cache.then((c) => c.put(request, response.clone()))
        return response
      })
      return cached || fetchPromise
    }),
  )
})
```

Strategy:
- **App shell (HTML/CSS/JS):** Stale-while-revalidate. The app loads instantly from cache even if the server is slow. The fresh version downloads in the background for next visit
- **API calls:** Network-only. Never serve cached API data. If the network is down, TanStack Query shows the error state
- **No API response caching in service worker.** TanStack Query already caches API responses in memory with configurable stale times. Duplicating this in the service worker creates consistency problems

#### TanStack Query cache strategy

```ts
// Default stale times by data type

// Rarely changes during a session
{ staleTime: 5 * 60_000 }   // 5 min: user profile, org settings, skill categories

// Changes on user action
{ staleTime: 30_000 }        // 30 sec: enrollments, course list, skills

// Changes frequently
{ staleTime: 0 }             // always refetch: dashboard "today" widget, alerts, stats
```

`gcTime` (garbage collection) is set to 5 minutes globally. This means cached data is kept for 5 minutes after the last component using it unmounts. If the user navigates away from a course list and comes back within 5 minutes, the cached data shows instantly while a background refetch runs.

`refetchOnWindowFocus: true` is enabled globally. When the user tabs back to SkillNet, all active queries refetch. This keeps data current without polling.

#### Network status indicator

When the backend is unreachable, show a small banner at the top of the page:

```tsx
// src/components/layout/NetworkStatus.tsx

function NetworkStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  if (isOnline) return null

  return (
    <div className="bg-[--color-warning] text-white text-xs text-center py-1.5 px-4">
      Connection lost. Some features may not work.
    </div>
  )
}
```

This banner appears above the header. It does not block the UI -- the user can still interact with any cached data that TanStack Query has in memory.

---

### Summary: what goes where

| Concern | Solution | Where it lives |
|---------|----------|----------------|
| API calls | `fetch` wrapper with session cookies | `src/api/client.ts` |
| Server state | TanStack Query hooks by domain | `src/api/*.ts` |
| Local UI state | `useState` in components | Component files |
| Auth redirect | Global 401 handler on QueryCache | `src/main.tsx` |
| Chat streaming | `fetch` + `ReadableStream` + `AbortController` | `src/api/chat.ts` |
| Generation progress | SSE with polling fallback | `src/api/generation.ts` |
| Level 2 rendering | `SpecRenderer` maps JSON spec to React components | `src/components/renderer/` |
| Level 3 isolation | `iframe` with `srcdoc` + `sandbox` + `postMessage` | `src/components/renderer/` |
| File upload | `XMLHttpRequest` for progress, `FormData` for multipart | `src/api/documents.ts` |
| Offline shell | Service worker (stale-while-revalidate for assets only) | `src/service-worker.ts` |
| Network status | `navigator.onLine` + event listeners | `src/components/layout/` |

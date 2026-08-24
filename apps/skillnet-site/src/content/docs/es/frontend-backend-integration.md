---
title: "Integración frontend-backend"
order: 23
section: "core"
---

## 10. Integración Frontend-Backend

> **Estado: Borrador.** Arquitectura completa de integración entre el frontend en React y el backend en FastAPI.

---

### 10.1 Capa de cliente API

#### Cliente base

Un único wrapper de fetch en `src/api/client.ts`. Sin gestión de tokens -- el navegador envía la cookie de sesión `httpOnly` en cada petición vía `credentials: 'include'`.

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
    // Sesion expirada o no autenticado.
    // NO redirigir aqui -- deja que lo haga el gestor global.
    throw new ApiError(401, { detail: 'Unauthorized' })
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(res.status, body)
  }

  // 204 No Content (p.ej. respuestas de DELETE)
  if (res.status === 204) return undefined as T

  return res.json()
}

// Metodos de conveniencia
export const get = <T>(path: string) => api<T>(path)

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) })

export const del = <T>(path: string) =>
  api<T>(path, { method: 'DELETE' })

// Subida multipart (sin Content-Type -- el navegador fija el boundary)
export const upload = <T>(path: string, formData: FormData) =>
  api<T>(path, {
    method: 'POST',
    headers: {},  // anula la eliminacion de Content-Type
    body: formData,
  })
```

La funcion `upload` omite deliberadamente `Content-Type` para que el navegador pueda fijar `multipart/form-data` con el boundary correcto.

#### Convenciones de query keys

Todas las query keys siguen un patron de array jerarquico. Esto hace que la invalidacion sea predecible.

```ts
// Patron: [dominio, recurso?, id?, sub-recurso?]

// Listas
['users']                              // todos los usuarios
['courses']                            // todos los cursos
['enrollments']                        // mis matriculas
['skills']                             // todas las skills

// Entidades individuales
['courses', courseId]                   // un curso con modulos/lecciones/ejercicios
['manuals', manualId]                  // un manual
['users', userId]                      // el detalle de un usuario

// Sub-recursos
['users', 'me']                        // usuario actual
['users', 'me', 'today']              // acciones de hoy (dashboard)
['users', 'me', 'skills']             // mis niveles de skill
['users', 'me', 'activity']           // mi actividad reciente
['enrollments', enrollmentId]          // una matricula

// Especificos de admin
['skills', 'matrix']                   // matriz de skills
['skills', 'mentorship-suggestions']   // emparejamiento de mentores
['alerts']                             // alertas de admin
['stats']                              // estadisticas resumen
['organizations', 'me']               // ajustes de la org
['generation-jobs', jobId]             // estado de un job de generacion

// Las listas filtradas usan un objeto en la key
['enrollments', { status: 'in_progress' }]
['courses', { status: 'published' }]
```

Ejemplos de invalidacion:
- Tras crear un curso: invalidar `['courses']`
- Tras enviar un ejercicio: invalidar `['enrollments', enrollmentId]`, `['users', 'me', 'skills']`, `['users', 'me', 'activity']`
- Tras actualizar los ajustes de la org: invalidar `['organizations', 'me']`

#### Organizacion de hooks (por dominio)

Cada fichero en `src/api/` exporta hooks de TanStack Query para un dominio. Todos los hooks devuelven los objetos estandar de TanStack Query (`{ data, isLoading, error }`).

```
src/api/
├── client.ts          # Wrapper de fetch base (arriba)
├── auth.ts            # useLogin, useLogout, useMe
├── courses.ts         # useCourses, useCourse, useCreateCourse, usePublishCourse
├── enrollments.ts     # useEnrollments, useEnrollment
├── exercises.ts       # useSubmitAttempt
├── skills.ts          # useSkills, useMySkills, useSkillMatrix, useMentorshipSuggestions
├── users.ts           # useUsers, useInvite, useBulkInvite
├── documents.ts       # useUploadDocument, useProcessDocument
├── manuals.ts         # useManual, useManuals
├── chat.ts            # useChat, useAdminChat (SSE -- patron distinto)
├── generation.ts      # useGenerationJob (polling)
├── settings.ts        # useOrgSettings, useUpdateOrgSettings, useUpdateProfile
└── stats.ts           # useStats, useAlerts
```

Ejemplo de **auth.ts**:

```ts
// src/api/auth.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { User } from '../types'

export function useMe() {
  return useQuery({
    queryKey: ['users', 'me'],
    queryFn: () => get<User>('/users/me'),
    retry: false,        // no reintentar en 401
    staleTime: 5 * 60_000,  // 5 minutos -- los datos del usuario rara vez cambian en sesion
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
      queryClient.clear()  // borra todo el cache al cerrar sesion
      window.location.href = '/login'
    },
  })
}
```

Ejemplo de **courses.ts** (con actualizacion optimista al publicar):

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
      // Cancela refetches en curso
      await queryClient.cancelQueries({ queryKey: ['courses', courseId] })

      // Guarda el valor anterior
      const previous = queryClient.getQueryData<CourseDetail>(['courses', courseId])

      // Actualiza el estado de forma optimista
      if (previous) {
        queryClient.setQueryData(['courses', courseId], {
          ...previous,
          status: 'published',
        })
      }

      return { previous }
    },
    onError: (_err, courseId, context) => {
      // Revertir en caso de error
      if (context?.previous) {
        queryClient.setQueryData(['courses', courseId], context.previous)
      }
    },
    onSettled: (_data, _err, courseId) => {
      // Refetch para asegurar consistencia
      queryClient.invalidateQueries({ queryKey: ['courses', courseId] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}
```

#### Patrones de mutacion

No toda mutacion necesita actualizaciones optimistas. La regla:

| Accion | ¿Optimista? | Por que |
|--------|-------------|---------|
| Enviar intento de ejercicio | **No** | La puntuacion viene del servidor. No se puede predecir |
| Publicar/archivar curso | **Si** | El cambio de estado es predecible. La respuesta instantanea de la UI importa |
| Actualizar perfil de usuario | **Si** | El usuario escribio el valor, es lo que espera ver |
| Invitar empleado | **No** | El servidor valida el email, puede rechazarlo |
| Eliminar contenido | **Si** | Eliminacion inmediata de la lista, revertir si falla |
| Subir documento | **No** | El servidor procesa el fichero, el estado lo determina el servidor |

Patron de mutacion estandar (sin actualizacion optimista):

```ts
export function useSubmitAttempt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ exerciseId, answer }: { exerciseId: string; answer: unknown }) =>
      post<AttemptResult>(`/exercises/${exerciseId}/attempt`, { answer }),
    onSuccess: (_data, { exerciseId }) => {
      // Invalida las queries relacionadas para que dashboard/skills/matricula se actualicen
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['users', 'me', 'skills'] })
      queryClient.invalidateQueries({ queryKey: ['users', 'me', 'activity'] })
    },
  })
}
```

#### Manejo de errores y reintentos

Configuracion global en el `QueryClient`:

```ts
// src/main.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Nunca reintentar 401, 403, 404
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          return false
        }
        // Reintenta errores de red y 5xx hasta 3 veces
        return failureCount < 3
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      staleTime: 30_000,        // 30 segundos por defecto
      gcTime: 5 * 60_000,       // recoleccion de basura a los 5 minutos
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: false,  // las mutaciones nunca se reintentan automaticamente
    },
  },
})
```

#### Autenticacion: manejo de 401

Un callback global de query redirige al login en 401. Esto vive en la configuracion del QueryClient, no en hooks individuales.

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

// Gestor de errores global via QueryCache
queryClient.getQueryCache().config.onError = (error) => {
  if (error instanceof ApiError && error.status === 401) {
    // Borra todos los datos en cache y redirige
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

La query `useMe()` se llama una vez en el layout raiz. Si devuelve 401, se dispara la redirecion. Cada query posterior hereda este comportamiento. No hay logica de autenticacion en los componentes de pagina.

#### Proteccion de rutas

Un componente wrapper comprueba la autenticacion antes de renderizar paginas protegidas:

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

### 10.2 Integracion de SSE para el chat

#### Arquitectura

El chat usa `fetch` con `ReadableStream`, no `EventSource`. Razones:
- `EventSource` solo soporta GET. El chat necesita hacer POST del cuerpo del mensaje
- `fetch` con streaming permite enviar el mensaje y leer la respuesta en una unica peticion
- `AbortController` da una cancelacion limpia

#### Formato de eventos SSE desde el backend

El backend envia eventos con formato SSE a traves de un `StreamingResponse`:

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

Tipos de evento:
- `token` -- fragmento incremental de texto
- `citation` -- referencia a una fuente (emitido despues del texto relevante)
- `done` -- stream completo
- `error` -- fallo en la generacion

#### Hook de chat

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
    // Anade el mensaje del usuario inmediatamente
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])

    // Crea el placeholder para la respuesta del asistente
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

    // Crea el abort controller para la cancelacion
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

        // Parsea los eventos SSE del buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''  // guarda la linea incompleta en el buffer

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
              // Evento por lote de citas: data es un array de objetos cita
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, citations: [...(m.citations ?? []), ...data] }
                    : m,
                ),
              )
            } else if (eventType === 'suggestions') {
              // Evento por lote de sugerencias: data es un array de sugerencias de seguimiento
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

      // Marca el streaming como completo
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false } : m,
        ),
      )
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // El usuario cancelo -- marca la respuesta parcial como completa
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m,
          ),
        )
      } else {
        // Error real -- muestra el error en el mensaje del asistente
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

#### Cancelacion

El usuario puede cancelar una respuesta en streaming de dos formas:
1. Pulsando un boton "Stop" que aparece durante el streaming (llama a `cancel()`)
2. Navegando fuera de la pagina de chat (el desmontaje del componente aborta via cleanup)

```tsx
// En el componente de la pagina de Chat
useEffect(() => {
  return () => {
    // Si se desmonta mientras hace streaming, aborta
    cancel()
  }
}, [cancel])
```

#### Reconexion

La reconexion de SSE no aplica aqui porque cada mensaje es un `POST` + stream independiente. Si el stream se corta a mitad de la respuesta:
- La respuesta parcial permanece visible en la UI
- El flag `isStreaming` se limpia
- Aparece un mensaje de error debajo de la respuesta parcial: "Response interrupted. Send your question again."
- Sin reintento automatico -- el usuario decide si reenvia

#### Consumo del componente de chat

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
      {/* Lista de mensajes */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && <ChatWelcome />}
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Entrada */}
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

### 10.3 Progreso en tiempo real para los jobs de generacion

#### El problema

La generacion de contenido es un pipeline multi-paso (pending -> extracting -> structuring -> generating -> reviewing -> published/failed). Cada paso tarda de segundos a minutos. El admin necesita ver en que punto del pipeline esta ahora mismo.

#### Enfoque: SSE para el progreso de la generacion

El flujo de creacion de contenido abre una conexion SSE tras disparar la generacion. Esto reutiliza la misma infraestructura de SSE del chat, con un formato de evento distinto.

**Disparo de la generacion:**

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

**Seguimiento del progreso via SSE:**

```ts
// src/api/generation.ts

type GenerationStep = 'pending' | 'extracting' | 'structuring' | 'generating' | 'reviewing' | 'published' | 'failed'

interface GenerationProgress {
  step: GenerationStep
  message?: string       // estado legible por humanos ("Extracting key topics...")
  courseId?: string       // se fija cuando se publica
  manualId?: string       // se fija cuando se publica
  error?: string          // se fija si falla
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

**Polling de respaldo (si la conexion SSE se cae):**

Si la conexion SSE falla o se cae, la UI recurre al polling. El paso actual del job de generacion siempre esta disponible via REST:

```ts
// Respaldo: sondear el estado de la generacion
export function useGenerationJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['generation-jobs', jobId],
    queryFn: () => get<GenerationProgress>(`/generation-jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const step = query.state.data?.step
      // Detiene el polling cuando es terminal
      if (step === 'published' || step === 'failed') return false
      return 3000  // sondea cada 3 segundos mientras esta activo
    },
  })
}
```

El componente de UI prueba SSE primero y solo usa el polling como respaldo.

#### Formato de eventos SSE desde el backend

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

#### Visualizacion del progreso

Un componente de indicador de pasos muestra el estado del pipeline:

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
      {/* Indicadores de paso */}
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

      {/* Mensaje de estado */}
      {progress.message && (
        <p className="text-sm text-[--color-text-secondary]">{progress.message}</p>
      )}

      {/* Estado de error */}
      {isFailed && progress.error && (
        <div className="text-sm text-[--color-danger] border border-red-200 rounded-md p-3">
          {progress.error}
        </div>
      )}
    </div>
  )
}
```

El indicador de pasos es una linea horizontal conectada con circulos numerados. Los pasos completados se rellenan con el color primario. El paso actual tiene un circulo con contorno. Los pasos pendientes estan atenuados. En caso de fallo, el paso actual se muestra en rojo y despliega el mensaje de error.

#### Integracion con el flujo de creacion de contenido

El paso 3 del flujo de creacion (`/admin/content/new/preview`) dispara la generacion y muestra el componente de progreso. Cuando el pipeline llega a `published`, la pagina transiciona al paso 4 (edicion) con el contenido generado ya cargado.

```tsx
// En la pagina ContentCreationPreview
const { mutate: generate, data: job } = useGenerateContent()
const { progress, isActive } = useGenerationProgress(job?.jobId ?? null)

// Cuando el usuario pulsa "Generate":
generate({ documentId, outputType: 'course_and_manual' })

// Muestra el progreso mientras esta activo:
{isActive && <GenerationProgress progress={progress} />}

// Cuando se publica, navega al paso de edicion:
useEffect(() => {
  if (progress.step === 'published' && progress.courseId) {
    navigate(`/admin/content/new/edit?courseId=${progress.courseId}`)
  }
}, [progress])
```

---

### 10.4 Integracion de Nivel 2 (UI declarativa)

#### Como funciona

El backend (o el agente) emite una especificacion compacta que describe *que* mostrar. El frontend tiene un componente renderizador que mapea la especificacion a componentes React. El usuario nunca sabe que la UI fue descrita por una especificacion -- se ve como cualquier otra pantalla.

#### Formato de la especificacion

El backend devuelve la especificacion como una estructura JSON (no texto A2TL-Web crudo). El formato JSON es la capa de transporte; el formato de texto A2TL-Web existe para el lado de autoria del LLM.

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

#### Componente renderizador

El renderizador recorre el arbol de la especificacion y mapea cada nodo a un componente React del sistema de diseno.

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

  // Tipos de nodo adicionales: progress_bar, skill_chart, alert_list, etc.
  // Cada uno mapea a componentes existentes del sistema de diseno.
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

#### Casos de uso

El Nivel 2 aplica donde el contenido varia pero la estructura es predecible:

| Pantalla | Que describe la especificacion |
|--------|------------------------|
| Widgets del Dashboard de admin | Resumen de la matriz de skills, lista de alertas, tarjetas de estadisticas. El agente decide que metricas destacar segun los datos actuales |
| Informes de progreso | Visualizacion del progreso del empleado personalizada segun lo que el admin pidio ("Show me who's behind") |
| Visualizaciones de brechas de skill | Graficos y tablas adaptados a las skills y empleados especificos en cuestion |
| Resumenes de curso | Vision general generada del contenido de un curso, adaptada a quien lo esta viendo |

#### Como envia el backend las especificaciones

La especificacion llega como parte de la respuesta normal de la API. No hace falta transporte especial:

```ts
// Ejemplo: el dashboard de admin podria incluir widgets declarativos
interface DashboardResponse {
  stats: SummaryStats           // Nivel 1: datos estaticos para componentes ya construidos
  matrix: SkillMatrixData       // Nivel 1: datos estaticos
  alerts: Alert[]               // Nivel 1: datos estaticos
  agentWidget?: RendererSpec    // Nivel 2: especificacion generada por el agente (opcional)
}
```

Cuando el agente genera una especificacion, el frontend comprueba si `agentWidget` esta presente y la renderiza con `SpecRenderer`. Si no, la pagina renderiza solo las secciones estaticas de Nivel 1.

---

### 10.5 Aislamiento del Nivel 3 (UI generativa)

#### Cuando se usa el Nivel 3

Solo para lecciones personalizadas donde el contenido, el contexto y la variabilidad del usuario son todos altos. Especificamente:
- Contenido de leccion adaptativo generado para un alumno especifico en un nivel de skill concreto
- Respuestas de tutoria interactiva que incluyen diagramas, explicaciones visuales o layouts personalizados
- Respuestas del agente que van mas alla del texto (widgets interactivos generados, guias paso a paso)

La mayor parte de SkillNet es Nivel 1 y 2. El Nivel 3 es la excepcion.

#### Metodo de aislamiento: iframe con srcdoc

`iframe` con `srcdoc`, no shadow DOM. Razones:
- **Aislamiento CSS completo.** El shadow DOM todavia hereda algo de CSS (fuente, color). Un iframe es un documento completamente separado
- **Aislamiento de scripts.** El JS generado por el agente no puede acceder al DOM, variables o cookies de la ventana padre
- **Seguridad.** El atributo `sandbox` restringe las capacidades exactamente a lo necesario
- **Contencion de errores mas simple.** Si el codigo generado falla, solo se rompe el iframe

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

  // Escucha mensajes del contenido generado
  useEffect(() => {
    if (!onEvent) return

    const handleMessage = (event: MessageEvent) => {
      // Solo acepta mensajes de nuestro iframe
      if (event.source !== iframeRef.current?.contentWindow) return

      // Valida la forma del mensaje
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

  // Inyecta el puente de comunicacion en el HTML
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

#### Restricciones del sandbox

El atributo `sandbox` del iframe se fija solo a `allow-scripts`. Esto significa:
- Los scripts pueden ejecutarse (necesario para ejercicios interactivos)
- Sin envio de formularios a URLs externas
- Sin popups
- Sin acceso a las cookies, localStorage o DOM de la pagina padre
- Sin navegacion de la pagina padre
- Sin acceso same-origin al documento padre

Si el contenido generado necesita enviar la respuesta de un ejercicio, usa `postMessage`.

#### Sanitizacion

La sanitizacion de HTML ocurre en el servidor antes de enviarse al frontend. El backend usa un enfoque de lista blanca:

**Permitido:** Elementos HTML estandar, CSS (estilos en linea y bloques `<style>`), Chart.js / JS vanilla para interactividad.

**Eliminado:** `<script src="external">` (sin carga de scripts externos), `<iframe>` (sin iframes anidados), `<form action="...">` (sin envios de formulario), `<a href="javascript:">` (sin JS en enlaces), cualquier atributo `on*` excepto a traves del puente.

El frontend anade una segunda capa usando `srcdoc` en un iframe con sandbox, lo que previene cualquier vector de ataque restante.

#### Comunicacion: puente postMessage

El HTML generado incluye un pequeno script puente que le permite enviar eventos a la app padre:

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

  // Inyecta el puente antes del cierre de </head> o al inicio de <body>
  if (html.includes('</head>')) {
    return html.replace('</head>', `${bridge}</head>`)
  }
  return `${bridge}${html}`
}
```

Uso en el HTML generado (el agente incluye estas llamadas):

```html
<!-- Dentro del contenido de leccion generado -->
<button onclick="skillnet.emit('exercise-answer', { questionId: 'q1', answer: 2 })">
  Submit Answer
</button>

<button onclick="skillnet.emit('navigate', { to: 'next-lesson' })">
  Next Lesson
</button>
```

La app padre gestiona estos eventos:

```tsx
// En la pagina CourseView
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

#### Auto-redimensionado de la altura del iframe

El contenido generado varia en longitud. El iframe debe redimensionarse para ajustarse:

```ts
// Anadido al script puente
const resizeObserver = new ResizeObserver(() => {
  window.parent.postMessage(
    { source: 'skillnet-generated', type: 'resize', payload: { height: document.body.scrollHeight } },
    '*'
  );
});
resizeObserver.observe(document.body);
```

El componente padre gestiona el evento de resize:

```tsx
// En el componente GeneratedContent
const [height, setHeight] = useState(400)

// En el manejador de mensajes:
if (event.data.type === 'resize') {
  setHeight(event.data.payload.height)
}

// En el iframe:
style={{ height: `${height}px` }}
```

---

### 10.6 Subida de ficheros

#### Flujo de subida

La subida de ficheros se usa en dos sitios:
1. **Creacion de contenido** -- el admin sube PDFs para generar cursos/manuales
2. **Invitacion de empleados** -- el admin sube un CSV para la invitacion masiva

Ambos usan el mismo componente de subida y patron de API subyacentes.

#### Componente de subida

```tsx
// src/components/ui/FileUploadZone.tsx

interface FileUploadZoneProps {
  accept: string                    // p.ej. '.pdf,.docx' o '.csv'
  maxFiles?: number                 // por defecto 1
  maxSizeMB?: number                // por defecto 20
  onFilesSelected: (files: File[]) => void
  children?: ReactNode              // contenido personalizado de la zona de drop
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
    e.target.value = ''  // resetea para que se pueda seleccionar el mismo fichero de nuevo
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

      {/* Errores de validacion */}
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

#### Subida con seguimiento de progreso

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
      // Usa XMLHttpRequest para eventos de progreso (fetch no soporta progreso de subida)
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
    // Sube de forma secuencial para no saturar el servidor
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

#### Visualizacion del progreso de subida

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

#### Resumen de validacion

| Comprobacion | Cliente | Servidor |
|-------|-------------|-------------|
| Extension de fichero | `.pdf`, `.docx`, `.md`, `.txt` | Misma comprobacion + verificacion de magic bytes |
| Tamano de fichero | 20MB max por fichero | Mismo limite aplicado |
| Numero de ficheros | Max 5 ficheros por lote de subida | Mismo limite |
| Tipo MIME | No se comprueba (poco fiable) | Se comprueba via `python-magic` |
| Escaneo de contenido | No es posible | Escaneo de malware si esta disponible |
| Formato CSV (invitacion) | Solo la extension | Validacion de columnas (name, email requeridos) |

El servidor rechaza ficheros que pasan la validacion del cliente pero fallan las comprobaciones del servidor (p.ej., un `.pdf` que en realidad es un `.exe`). El cliente muestra el mensaje de error del servidor en linea.

---

### 10.7 Consideraciones sobre el modo offline

#### Que funciona sin conexion

SkillNet es principalmente una herramienta online. El despliegue autohospedado corre en la red de la empresa, asi que "sin conexion" significa que el servidor es inalcanzable (problema de red, servidor caido).

| Funcionalidad | Comportamiento sin conexion |
|---------|-----------------|
| **Cursos del catalogo (ya instalados)** | El contenido esta en PostgreSQL en el servidor local. Si el servidor esta activo pero internet esta caido, los cursos funcionan. Si el propio servidor esta caido, nada funciona |
| **Funciones de IA (chat, generacion)** | Requieren acceso a la API del LLM. Sin conexion solo si se usa un modelo local (Ollama). En otro caso, muestra "AI features require internet connection" |
| **Paginas estaticas (login, ajustes, nav)** | Servidas desde el frontend. Si el bundle del frontend esta en cache, el shell carga. Pero las llamadas a la API fallaran |

#### Estrategia de service worker

Un service worker minimo para el shell del frontend. El objetivo no es soporte offline completo -- es una carga rapida en visitas repetidas y una degradacion elegante cuando el backend esta temporalmente inalcanzable.

```ts
// src/service-worker.ts

// Cachea el app shell (HTML, CSS, JS, fuentes, iconos)
const SHELL_CACHE = 'skillnet-shell-v1'
const SHELL_URLS = [
  '/',
  '/index.html',
  // Vite genera nombres de fichero con hash -- se cachean en la primera carga
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  // Llamadas a la API: solo red. Nunca sirvas datos de API obsoletos desde la cache.
  if (request.url.includes('/api/')) {
    event.respondWith(fetch(request))
    return
  }

  // App shell: stale-while-revalidate.
  // Sirve la version en cache de inmediato, obtiene la version fresca en segundo plano.
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

Estrategia:
- **App shell (HTML/CSS/JS):** Stale-while-revalidate. La app carga al instante desde la cache incluso si el servidor va lento. La version fresca se descarga en segundo plano para la proxima visita
- **Llamadas a la API:** Solo red. Nunca se sirven datos de API en cache. Si la red esta caida, TanStack Query muestra el estado de error
- **Sin cache de respuestas de API en el service worker.** TanStack Query ya cachea las respuestas de la API en memoria con tiempos de caducidad configurables. Duplicar esto en el service worker crea problemas de consistencia

#### Estrategia de cache de TanStack Query

```ts
// Tiempos de caducidad por defecto segun tipo de dato

// Cambia raramente durante una sesion
{ staleTime: 5 * 60_000 }   // 5 min: perfil de usuario, ajustes de la org, categorias de skill

// Cambia por accion del usuario
{ staleTime: 30_000 }        // 30 seg: matriculas, lista de cursos, skills

// Cambia frecuentemente
{ staleTime: 0 }             // siempre refetch: widget "hoy" del dashboard, alertas, estadisticas
```

`gcTime` (recoleccion de basura) se fija a 5 minutos globalmente. Esto significa que los datos en cache se mantienen 5 minutos despues de que el ultimo componente que los usaba se desmonte. Si el usuario navega fuera de una lista de cursos y vuelve dentro de 5 minutos, los datos en cache se muestran al instante mientras corre un refetch en segundo plano.

`refetchOnWindowFocus: true` esta activado globalmente. Cuando el usuario vuelve a la pestana de SkillNet, todas las queries activas se refrescan. Esto mantiene los datos actualizados sin necesidad de polling.

#### Indicador de estado de red

Cuando el backend es inalcanzable, se muestra un pequeno banner en la parte superior de la pagina:

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

Este banner aparece encima de la cabecera. No bloquea la UI -- el usuario puede seguir interactuando con cualquier dato en cache que TanStack Query tenga en memoria.

---

### Resumen: que va donde

| Aspecto | Solucion | Donde vive |
|---------|----------|----------------|
| Llamadas a la API | Wrapper de `fetch` con cookies de sesion | `src/api/client.ts` |
| Estado del servidor | Hooks de TanStack Query por dominio | `src/api/*.ts` |
| Estado local de UI | `useState` en los componentes | Ficheros de componentes |
| Redireccion de auth | Gestor global de 401 en QueryCache | `src/main.tsx` |
| Streaming de chat | `fetch` + `ReadableStream` + `AbortController` | `src/api/chat.ts` |
| Progreso de generacion | SSE con respaldo de polling | `src/api/generation.ts` |
| Renderizado de Nivel 2 | `SpecRenderer` mapea la especificacion JSON a componentes React | `src/components/renderer/` |
| Aislamiento de Nivel 3 | `iframe` con `srcdoc` + `sandbox` + `postMessage` | `src/components/renderer/` |
| Subida de ficheros | `XMLHttpRequest` para el progreso, `FormData` para multipart | `src/api/documents.ts` |
| Shell offline | Service worker (stale-while-revalidate solo para assets) | `src/service-worker.ts` |
| Estado de red | `navigator.onLine` + event listeners | `src/components/layout/` |
</content>

/**
 * SSE client for the two-phase streaming schema proposal.
 *
 * Phase 1 ("structure"): the backend returns node titles, criticality, and
 * prerequisites in a single event. The UI renders the tree immediately.
 *
 * Phase 2 ("node_detail"): one event per node with summary, outcome, estimated
 * minutes, and default format. Each node fills in progressively as it arrives.
 *
 * Terminal events: "done" (all enrichments complete) and "error".
 */

const BASE = '/api/v1'

export interface StructureNode {
  title: string
  criticality: string
  prerequisites: number[]
}

export interface NodeDetail {
  index: number
  detail: {
    summary?: string
    outcome?: string
    default_ui_format?: string
  }
  error?: string
}

export interface SchemaStreamCallbacks {
  onStructure: (nodes: StructureNode[], skills: string[]) => void
  onNodeDetail: (detail: NodeDetail) => void
  onDone: () => void
  onError: (message: string) => void
}

/**
 * Connect to `POST /ai/schema-propose-stream` via fetch + ReadableStream.
 *
 * Returns an AbortController so the caller can cancel mid-stream (e.g. when
 * the user changes density before the previous proposal finishes).
 */
export function streamSchemaProposal(
  payload: { title: string; description?: string; intent_density: number },
  callbacks: SchemaStreamCallbacks,
  signal?: AbortSignal,
): AbortController {
  const controller = new AbortController()

  // Merge external signal if provided
  const combinedSignal = signal
    ? AbortSignal.any([controller.signal, signal])
    : controller.signal

  ;(async () => {
    try {
      const res = await fetch(`${BASE}/ai/schema-propose-stream`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: combinedSignal,
      })

      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({ detail: 'Unknown error' }))
        callbacks.onError(body.detail ?? `HTTP ${res.status}`)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventType = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const raw = line.slice(5).trim()
            if (!raw) continue
            let data: Record<string, unknown>
            try {
              data = JSON.parse(raw)
            } catch {
              continue
            }

            if (eventType === 'structure') {
              const nodes = (data.nodes as StructureNode[]) ?? []
              const skills = Array.isArray(data.skills) ? data.skills.map(String) : []
              callbacks.onStructure(nodes, skills)
            } else if (eventType === 'node_detail') {
              callbacks.onNodeDetail(data as unknown as NodeDetail)
            } else if (eventType === 'done') {
              callbacks.onDone()
            } else if (eventType === 'error') {
              callbacks.onError((data.message as string) ?? 'Schema proposal failed')
            }

            eventType = ''
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError((err as Error).message ?? 'Connection failed')
      }
    }
  })()

  return controller
}

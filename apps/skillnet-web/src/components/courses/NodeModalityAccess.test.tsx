import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NodeModalityAccess } from './NodeModalityAccess'

const messages = {
  'node.modalities': 'También disponible',
  'node.modality.audio': 'Audio',
  'node.modality.video': 'Vídeo',
  'node.modality.pending': 'aún no preparado',
}

function artifact(kind: string, nodeId: string | null = null) {
  return {
    id: `${kind}-1`, course_id: 'course-1', node_id: nodeId, kind, status: 'done',
    spec_json: {}, has_asset: true, content_hash: null, error: null,
    created_at: '2026-08-14T10:00:00Z', updated_at: '2026-08-14T10:00:00Z',
  }
}

function renderAccess(preferred: Array<'audio' | 'video'>, artifacts: unknown[]) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => artifacts,
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <IntlProvider locale="es" messages={messages}>
      <QueryClientProvider client={client}>
        <NodeModalityAccess courseId="course-1" nodeId="node-1" preferred={preferred} />
      </QueryClientProvider>
    </IntlProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('NodeModalityAccess', () => {
  it('keeps a requested modality visible while its artifact is not prepared', async () => {
    renderAccess(['audio'], [])
    const audio = await screen.findByRole('button', { name: /Audio.*aún no preparado/ })
    expect(audio).toBeDisabled()
  })

  it('offers every selected modality independently of the OpenUI lesson', async () => {
    renderAccess(['audio', 'video'], [artifact('podcast'), artifact('video', 'node-1')])
    expect(await screen.findByRole('button', { name: 'Audio' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Vídeo' })).toBeEnabled()
    expect(screen.getByRole('navigation', { name: 'También disponible' })).toBeInTheDocument()
  })
})

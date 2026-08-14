import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NodeModalityAccess } from './NodeModalityAccess'

const messages = {
  'node.modalities': 'Formatos',
  'node.modality.web': 'Web',
  'node.modality.audio': 'Audio',
  'node.modality.video': 'Vídeo',
  'node.modality.preparing': 'Preparando {modality} para este contenido…',
  'node.modality.onDemand': 'Se genera ahora.',
  'node.modality.failed': 'No se pudo preparar esta modalidad.',
  'node.modality.retry': 'Reintentar',
  'podcast.title': 'Audio del curso',
  'podcast.transcript': 'Transcripción',
  'podcast.sources': 'Fuentes',
  'podcast.noSources': 'Sin fuentes',
}

function json(body: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body })
}

function renderAccess(preferred: Array<'audio' | 'video'>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <IntlProvider locale="es" messages={messages}>
      <QueryClientProvider client={client}>
        <NodeModalityAccess nodeId="node-1" preferred={preferred}>
          <div data-testid="web-lesson">Lección OpenUI con estado</div>
        </NodeModalityAccess>
      </QueryClientProvider>
    </IntlProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('NodeModalityAccess', () => {
  it('generates a preferred modality only when the learner activates it', async () => {
    const fetchMock = vi.fn((input: string, options?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/nodes/node-1/modalities/audio') && options?.method === 'POST') {
        return json({ artifact_id: 'audio-1', status: 'pending' })
      }
      if (url.endsWith('/media/artifacts/audio-1')) {
        return json({
          id: 'audio-1', course_id: 'course-1', node_id: 'node-1', kind: 'podcast',
          status: 'pending', spec_json: {}, has_asset: false, content_hash: null,
          error: null, created_at: '2026-08-14T10:00:00Z', updated_at: '2026-08-14T10:00:00Z',
        })
      }
      return json({ detail: 'Not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderAccess(['audio', 'video'])

    expect(screen.getByTestId('web-lesson')).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Audio' }))

    expect(await screen.findByText('Preparando Audio para este contenido…')).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/nodes/node-1/modalities/audio',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('course_id='))).toBe(false)
    expect(screen.getByTestId('web-lesson')).not.toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Web' }))
    expect(screen.getByTestId('web-lesson')).toBeVisible()
  })

  it('does not expose modalities the learner did not select', () => {
    vi.stubGlobal('fetch', vi.fn())
    renderAccess(['video'])

    expect(screen.getByRole('button', { name: 'Web' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vídeo' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Audio' })).not.toBeInTheDocument()
  })

  it('can request audio and video independently while the other request is pending', async () => {
    const pending: Array<(value: Awaited<ReturnType<typeof json>>) => void> = []
    const fetchMock = vi.fn((_input: string, _options?: RequestInit) =>
      new Promise<Awaited<ReturnType<typeof json>>>((resolve) => pending.push(resolve)),
    )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderAccess(['audio', 'video'])

    await user.click(screen.getByRole('button', { name: 'Audio' }))
    await user.click(screen.getByRole('button', { name: 'Vídeo' }))

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/modalities/audio')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/modalities/video')
    pending.forEach((resolve, index) => resolve({
      ok: true,
      status: 202,
      json: async () => ({ artifact_id: index === 0 ? 'audio-1' : 'video-1', status: 'pending' }),
    }))
  })
})

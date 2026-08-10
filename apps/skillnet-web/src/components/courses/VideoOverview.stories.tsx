import type { Meta } from '@storybook/react-vite'
import { VideoOverview } from './VideoOverview'

/**
 * The per-slide clips need a live API + auth, so these stories exercise the slide stage,
 * the captions line and the parallel citations panel (the interesting part). Without a
 * backend the clips simply fail to load and the player shows its "unavailable" state, which
 * is the honest offline behaviour — the transport still walks the slides manually.
 */
const meta: Meta<typeof VideoOverview> = {
  title: 'Courses/VideoOverview',
  component: VideoOverview,
  parameters: { a11y: { test: 'error' } },
}
export default meta

const citations = [
  {
    citation_id: 'c1',
    document: 'Manual de atención al cliente',
    section: 'Devoluciones',
    page: 12,
  },
  {
    citation_id: 'c2',
    document: 'Manual de atención al cliente',
    section: 'Productos defectuosos',
    page: 13,
  },
]

const slides = [
  {
    title: 'Política de devoluciones',
    subtitle: 'Lo esencial en un vistazo',
    blocks: [
      {
        type: 'text' as const,
        text: 'Aceptamos devoluciones dentro de un plazo determinado y en condiciones concretas.',
        variant: 'lead' as const,
      },
      { type: 'callout' as const, tone: 'info' as const, text: 'Siempre con el ticket de compra.' },
    ],
    citation_ids: ['c1'],
    narration:
      'Las devoluciones se aceptan durante treinta días naturales desde la compra, siempre con el producto en su estado original y el ticket.',
    narration_citation_ids: ['c1'],
    audio_ref: 'a'.repeat(64),
    audio_ext: 'mp3',
  },
  {
    title: 'Productos defectuosos',
    blocks: [
      {
        type: 'chart' as const,
        kind: 'bar' as const,
        title: 'Días de plazo por caso',
        labels: ['Normal', 'Defectuoso'],
        values: [30, 60],
      },
    ],
    citation_ids: ['c2'],
    narration:
      'Si el producto llegó defectuoso, la devolución es gratuita y el plazo se amplía a sesenta días.',
    narration_citation_ids: ['c2'],
    audio_ref: 'b'.repeat(64),
    audio_ext: 'mp3',
  },
]

export const Narrado = () => (
  <div className="max-w-2xl">
    <VideoOverview artifactId="demo-artifact-id" slides={slides} citations={citations} />
  </div>
)

export const SinFuentes = () => (
  <div className="max-w-2xl">
    <VideoOverview
      artifactId="demo-artifact-id"
      slides={[
        {
          title: 'Introducción',
          blocks: [{ type: 'text' as const, text: 'Sin material de origen, hablamos en general.' }],
          citation_ids: [],
          narration: 'En este resumen no hay pasajes de origen que citar.',
          narration_citation_ids: [],
          audio_ref: 'c'.repeat(64),
          audio_ext: 'mp3',
        },
      ]}
      citations={[]}
    />
  </div>
)

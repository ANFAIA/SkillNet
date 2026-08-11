import type { Meta } from '@storybook/react-vite'
import { PodcastPlayer } from './PodcastPlayer'

/**
 * The asset route needs a live API + auth, so these stories exercise the transcript and the
 * parallel citations panel (the interesting part). The <audio> element will simply show its
 * "unavailable" state without a backend, which is the honest offline behaviour.
 */
const meta: Meta<typeof PodcastPlayer> = {
  title: 'Courses/PodcastPlayer',
  component: PodcastPlayer,
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

const turns = [
  {
    speaker: 'A' as const,
    text: '¿Qué plazo tiene un cliente para devolver un producto que compró la semana pasada?',
    citation_ids: ['c1'],
  },
  {
    speaker: 'B' as const,
    text: 'Treinta días naturales desde la compra, siempre que el producto esté en su estado original y con el ticket.',
    citation_ids: ['c1'],
  },
  {
    speaker: 'A' as const,
    text: '¿Y si llegó defectuoso?',
    citation_ids: [],
  },
  {
    speaker: 'B' as const,
    text: 'Entonces la devolución es gratuita y el plazo se amplía a sesenta días.',
    citation_ids: ['c2'],
  },
]

export const DeepDive = () => (
  <div className="max-w-2xl">
    <PodcastPlayer
      artifactId="demo-artifact-id"
      format="deep_dive"
      turns={turns}
      citations={citations}
    />
  </div>
)

export const TheBrief = () => (
  <div className="max-w-2xl">
    <PodcastPlayer
      artifactId="demo-artifact-id"
      format="the_brief"
      turns={[
        {
          speaker: 'A' as const,
          text: 'Resumen: las devoluciones se aceptan en treinta días; si el producto es defectuoso, la devolución es gratuita y el plazo sube a sesenta.',
          citation_ids: ['c1', 'c2'],
        },
      ]}
      citations={citations}
    />
  </div>
)

export const SinFuentes = () => (
  <div className="max-w-2xl">
    <PodcastPlayer
      artifactId="demo-artifact-id"
      format="debate"
      turns={[
        { speaker: 'A' as const, text: 'Sin material de origen, hablamos en general.', citation_ids: [] },
        { speaker: 'B' as const, text: 'Exacto, no hay pasajes que citar aquí.', citation_ids: [] },
      ]}
      citations={[]}
    />
  </div>
)

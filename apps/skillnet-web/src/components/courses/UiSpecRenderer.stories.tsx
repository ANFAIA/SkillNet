import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UiSpecRenderer } from './UiSpecRenderer'
import { brokenSpecs, goldenSpecs } from '../../test/fixtures/ui-specs'

const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })

const meta: Meta<typeof UiSpecRenderer> = {
  title: 'Courses/UiSpecRenderer',
  component: UiSpecRenderer,
  parameters: { a11y: { test: 'error' } },
  decorators: [
    (Story) => (
      <QueryClientProvider client={client}>
        <div className="max-w-2xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
}
export default meta

/** The ten golden specs, one per frozen kit component — the same JSON the backend tests use. */
export const SpecsGolden = () => (
  <div className="space-y-10">
    {Object.entries(goldenSpecs).map(([name, spec]) => (
      <section key={name}>
        <p className="text-xs font-mono text-text-muted mb-3">
          {name} · format={spec.format}
        </p>
        <UiSpecRenderer spec={spec} nodeId="node-demo" renderId="render-demo" />
      </section>
    ))}
  </div>
)

/**
 * What a broken spec looks like. None of these can reach a real learner — the
 * backend validator rejects them — but the renderer degrades instead of
 * blanking the screen, and that is the behaviour worth being able to see.
 */
export const SpecsRotos = () => (
  <div className="space-y-10">
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        referencia colgante · el hijo inexistente se omite
      </p>
      <UiSpecRenderer spec={brokenSpecs.danglingRef} nodeId="node-demo" />
    </section>
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        ciclo · se corta al detectarlo, los hermanos siguen
      </p>
      <UiSpecRenderer spec={brokenSpecs.cycle} nodeId="node-demo" />
    </section>
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        tipo desconocido · el bloque se cae, la pantalla no
      </p>
      <UiSpecRenderer spec={brokenSpecs.unknownType} nodeId="node-demo" />
    </section>
  </div>
)

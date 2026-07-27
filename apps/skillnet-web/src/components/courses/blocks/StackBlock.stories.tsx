import type { Meta } from '@storybook/react-vite'
import { StackBlock } from './StackBlock'
import { TextContentBlock } from './TextContentBlock'

const meta: Meta<typeof StackBlock> = {
  title: 'Courses/Blocks/StackBlock',
  component: StackBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

const Sample = () => (
  <>
    <TextContentBlock text="Primer bloque de la pantalla." variant="lead" />
    <TextContentBlock text="Segundo bloque, cuerpo de la explicacion." variant="body" />
    <TextContentBlock text="Manual de atencion al cliente, pagina 3." variant="caption" />
  </>
)

export const Separaciones = () => (
  <div className="space-y-8 max-w-2xl">
    {(['sm', 'md', 'lg'] as const).map((gap) => (
      <div key={gap}>
        <p className="text-xs text-text-muted mb-2">gap=&quot;{gap}&quot;</p>
        <StackBlock gap={gap}>
          <Sample />
        </StackBlock>
      </div>
    ))}
  </div>
)

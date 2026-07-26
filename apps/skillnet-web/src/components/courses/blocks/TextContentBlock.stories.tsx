import type { Meta } from '@storybook/react-vite'
import { TextContentBlock } from './TextContentBlock'

const meta: Meta<typeof TextContentBlock> = {
  title: 'Courses/Blocks/TextContentBlock',
  component: TextContentBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Variantes = () => (
  <div className="space-y-6 max-w-2xl">
    <div>
      <p className="text-xs text-text-muted mb-1">lead — el hueco de &quot;esto te sirve para X&quot;</p>
      <TextContentBlock
        text="Esto te sirve para resolver una devolucion en el mostrador sin llamar al encargado."
        variant="lead"
      />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">body — prosa por defecto</p>
      <TextContentBlock
        text="Las devoluciones se aceptan durante 30 dias naturales desde la fecha del ticket."
        variant="body"
      />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">caption — procedencia, notas</p>
      <TextContentBlock text="Manual de atencion al cliente, pagina 3." variant="caption" />
    </div>
  </div>
)

export const MarkdownInline = () => (
  <div className="max-w-2xl">
    <TextContentBlock
      text="Pasado el plazo aplica la **garantia del fabricante**, que cubre *defectos de fabricacion*. El codigo interno es `GAR-FAB` y esta en el [manual](https://example.com)."
      variant="body"
    />
  </div>
)

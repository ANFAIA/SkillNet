import type { Meta } from '@storybook/react-vite'
import { MarkdownBlock } from './MarkdownBlock'

const meta: Meta<typeof MarkdownBlock> = {
  title: 'Courses/Blocks/MarkdownBlock',
  component: MarkdownBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const FallbackSeed = () => (
  <div className="max-w-2xl">
    <MarkdownBlock
      content={
        '## Plazo de devolucion\n\n' +
        'Las devoluciones se aceptan durante **30 dias naturales** desde la fecha del ticket.\n\n' +
        '- El producto debe estar sin usar.\n' +
        '- El embalaje original es obligatorio.\n\n' +
        '| Caso | Plazo |\n| --- | --- |\n| Devolucion | 30 dias |\n| Cambio | 15 dias |\n\n' +
        'Pasado el plazo aplica la garantia del fabricante.\n'
      }
    />
  </div>
)

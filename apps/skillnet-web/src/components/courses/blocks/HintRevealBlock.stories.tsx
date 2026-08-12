import type { Meta } from '@storybook/react-vite'
import { HintRevealBlock } from './HintRevealBlock'

const meta: Meta<typeof HintRevealBlock> = {
  title: 'Courses/Blocks/Didact/HintRevealBlock',
  component: HintRevealBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const AyudaProgresiva = () => (
  <div className="max-w-lg">
    <HintRevealBlock
      title="Una comanda incluye una alergia al marisco. ¿Cómo debe registrarse?"
      hints={[
        'No basta con avisarlo verbalmente.',
        'Piensa dónde debe quedar visible para cocina y para el pase.',
      ]}
      solution="Registra el alérgeno en la propia línea del plato y avisa también al pase antes de enviar la comanda."
    />
  </div>
)

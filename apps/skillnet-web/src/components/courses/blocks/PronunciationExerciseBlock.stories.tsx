import type { Meta } from '@storybook/react-vite'
import { PronunciationExerciseBlock } from './PronunciationExerciseBlock'

const meta: Meta<typeof PronunciationExerciseBlock> = {
  title: 'Courses/Blocks/PronunciationExerciseBlock',
  component: PronunciationExerciseBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const SaludoBasico = () => (
  <div className="max-w-lg">
    <PronunciationExerciseBlock
      targetText="Buenos dias, bienvenido a la tienda. En que puedo ayudarle?"
      language="es"
    />
  </div>
)

export const FraseIngles = () => (
  <div className="max-w-lg">
    <PronunciationExerciseBlock
      targetText="Good morning. How can I help you today?"
      language="en"
    />
  </div>
)

export const FraseLarga = () => (
  <div className="max-w-lg">
    <PronunciationExerciseBlock
      targetText="Le informo de que su devolucion ha sido procesada correctamente. El reembolso aparecera en su cuenta en un plazo de tres a cinco dias habiles."
      language="es"
    />
  </div>
)

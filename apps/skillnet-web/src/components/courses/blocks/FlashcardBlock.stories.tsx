import type { Meta } from '@storybook/react-vite'
import { FlashcardBlock } from './FlashcardBlock'

const meta: Meta<typeof FlashcardBlock> = {
  title: 'Courses/Blocks/Didact/FlashcardBlock',
  component: FlashcardBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const RecuerdoAntesDeRevelar = () => (
  <div className="max-w-lg">
    <FlashcardBlock
      front="¿Cuándo debe registrarse una diferencia en el fondo de caja?"
      back="Antes de abrir el turno: primero se completa el fondo y se registra la diferencia."
    />
  </div>
)

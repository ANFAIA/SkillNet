import type { Meta } from '@storybook/react-vite'
import { BeforeAfterBlock } from './BeforeAfterBlock'

const meta: Meta<typeof BeforeAfterBlock> = {
  title: 'Courses/Blocks/BeforeAfterBlock',
  component: BeforeAfterBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const CodigoRefactorizado = () => (
  <div className="max-w-lg">
    <BeforeAfterBlock
      title="Refactorizacion: extraccion de metodo"
      beforeLabel="Antes"
      beforeContent={"```js\nfunction process(data) {\n  let total = 0;\n  for (let i = 0; i < data.length; i++) {\n    total += data[i].price * data[i].qty;\n  }\n  return total;\n}\n```"}
      afterLabel="Despues"
      afterContent={"```js\nfunction lineTotal(item) {\n  return item.price * item.qty;\n}\n\nfunction process(data) {\n  return data.reduce((sum, item) => sum + lineTotal(item), 0);\n}\n```"}
    />
  </div>
)

export const ConceptoSimple = () => (
  <div className="max-w-lg">
    <BeforeAfterBlock
      title="Impacto de la normalizacion"
      beforeLabel="Sin normalizar"
      beforeContent="Tabla unica con datos repetidos: nombre del cliente aparece en cada fila de pedido."
      afterLabel="Normalizado (3FN)"
      afterContent="Tabla de clientes separada. Cada pedido referencia al cliente por ID. Sin redundancia."
    />
  </div>
)

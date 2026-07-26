import type { Meta } from '@storybook/react-vite'
import { CodeBlockBlock } from './CodeBlockBlock'

const meta: Meta<typeof CodeBlockBlock> = {
  title: 'Courses/Blocks/CodeBlockBlock',
  component: CodeBlockBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const ComandosDeTerminal = () => (
  <div className="max-w-2xl">
    <CodeBlockBlock
      language="text"
      code={'DEV --ticket 2026-000431 --motivo talla\nDEV --confirmar\nDEV --reembolso tarjeta'}
    />
  </div>
)

export const LineaLarga = () => (
  <div className="max-w-sm">
    <p className="text-xs text-text-muted mb-2">
      Contenedor estrecho: el bloque scrollea, la pagina no
    </p>
    <CodeBlockBlock
      language="sql"
      code="SELECT ticket_id, importe, motivo FROM devoluciones WHERE fecha >= current_date - interval '30 days' ORDER BY importe DESC;"
    />
  </div>
)

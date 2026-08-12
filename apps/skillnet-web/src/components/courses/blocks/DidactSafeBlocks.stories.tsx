import type { Meta, StoryObj } from '@storybook/react-vite'

import { DidactGlossaryBlock } from './DidactGlossaryBlock'
import { DidactSelfExplanationBlock } from './DidactSelfExplanationBlock'
import { DidactTimelineBlock } from './DidactTimelineBlock'
import { DidactWorkedExampleBlock } from './DidactWorkedExampleBlock'

const meta = { title: 'Courses/Didact/Safe OpenUI adapters', component: DidactGlossaryBlock } satisfies Meta<typeof DidactGlossaryBlock>
export default meta
type Story = StoryObj<typeof meta>

export const Glossary: Story = { args: { title: 'Conceptos', terms: ['SLA', 'Escalado'], definitions: ['Acuerdo de servicio', 'Transferencia especializada'] } }
export const Timeline = { render: () => <DidactTimelineBlock label="Proceso" steps={['Registrar', 'Clasificar', 'Resolver']} details={['Capturar datos', 'Impacto y urgencia', 'Cerrar o escalar']} /> }
export const WorkedExample = { render: () => <DidactWorkedExampleBlock problem="Clasificar una incidencia" steps={['Comprobar impacto', 'Comprobar urgencia']} summary="Combina ambas señales" /> }
export const SelfExplanation = { render: () => <DidactSelfExplanationBlock prompt="¿Por qué escalarías este caso?" scaffold={['Identifica el riesgo', 'Relaciona la regla']} model="Un ejemplo se revela después del intento." /> }

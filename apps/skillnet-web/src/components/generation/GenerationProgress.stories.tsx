import { useEffect, useState } from 'react'
import type { Meta } from '@storybook/react-vite'
import { GenerationProgress } from './GenerationProgress'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
import type { GenerationProgress as GenerationProgressData } from '../../types'

/**
 * The screen exists to be looked at while nothing else happens, so the story that
 * matters is `Recorrido`: a still frame cannot show whether the wait reads as work in
 * progress or as a hung request.
 */
const meta: Meta<typeof GenerationProgress> = {
  title: 'Generation/GenerationProgress',
  component: GenerationProgress,
}
export default meta

/** The wizard column, so the block is judged at the width it actually gets. */
function Frame({ children }: { children: React.ReactNode }) {
  return <div className="max-w-2xl py-6">{children}</div>
}

export const EnCurso = () => (
  <Frame>
    <GenerationProgress progress={{ step: 'generating', message: 'Escribiendo la leccion 3 de 5' }} />
  </Frame>
)

export const PrimerPaso = () => (
  <Frame>
    <GenerationProgress progress={{ step: 'pending', message: 'El trabajo esta en la cola' }} />
  </Frame>
)

export const Publicado = () => (
  <Frame>
    <GenerationProgress progress={{ step: 'published' }} />
  </Frame>
)

/**
 * Mounted on `reviewing` and flipped on the next tick, because that is the only way
 * the failure is ever seen: the `failed` event carries no step name, so which node
 * gets the cross comes from the last one the component saw. Handed `failed` cold —
 * a reload, never the wizard — it honestly marks nothing.
 */
export const Fallo = () => {
  const [progress, setProgress] = useState<GenerationProgressData>({ step: 'reviewing' })

  useEffect(() => {
    setProgress({ step: 'failed', error: 'El proveedor devolvio 429 y se agotaron los reintentos.' })
  }, [])

  return (
    <Frame>
      <GenerationProgress progress={progress} />
    </Frame>
  )
}

const SCRIPT: GenerationProgressData[] = [
  { step: 'pending', message: 'El trabajo esta en la cola' },
  { step: 'extracting', message: 'Leyendo 3 documentos' },
  { step: 'structuring', message: 'Agrupando los temas en modulos' },
  { step: 'generating', message: 'Escribiendo la leccion 1 de 5' },
  { step: 'generating', message: 'Escribiendo la leccion 4 de 5' },
  { step: 'reviewing', message: 'Comprobando que cada leccion cita el manual' },
  { step: 'published' },
]

/**
 * The pipeline as the operator sees it, at roughly the cadence Groq gives (a few
 * seconds per phase). Watch the segment under the active step: the sweep travelling
 * down it is what says "forward", and it keeps going between events.
 */
export const Recorrido = () => {
  const [i, setI] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % (SCRIPT.length + 2)), 2600)
    return () => clearInterval(id)
  }, [])

  return (
    <Frame>
      <GenerationProgress progress={SCRIPT[Math.min(i, SCRIPT.length - 1)]} />
    </Frame>
  )
}

const FAIL_SCRIPT: GenerationProgressData[] = [
  ...SCRIPT.slice(0, 5),
  { step: 'failed', error: 'El proveedor devolvio 429 y se agotaron los reintentos.' },
]

/** Same run, ending in the error the retry button below it belongs to. */
export const RecorridoHastaElFallo = () => {
  const [i, setI] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % (FAIL_SCRIPT.length + 2)), 2600)
    return () => clearInterval(id)
  }, [])

  return (
    <Frame>
      <GenerationProgress progress={FAIL_SCRIPT[Math.min(i, FAIL_SCRIPT.length - 1)]} />
    </Frame>
  )
}

/**
 * The declared preference (`users.accessibility.reduce_motion`), which is the half an
 * OS media query cannot see. The halo and the sweep are not slowed down, they are not
 * rendered; the dots stay put but stop bouncing. The rail still says the same thing.
 */
export const MovimientoReducido = () => (
  <declaredReducedMotionContext.Provider value={true}>
    <Frame>
      <GenerationProgress progress={{ step: 'generating', message: 'Escribiendo la leccion 3 de 5' }} />
    </Frame>
  </declaredReducedMotionContext.Provider>
)

import type { ComponentType } from 'react'

export type DidactLabFixture = {
  props: Readonly<Record<string, unknown>>
  note: string
}

export type DidactLabComponent = ComponentType<Record<string, unknown>>

/**
 * Controlled, non-production fixtures for APIs which can render honestly without a
 * SkillNet host port. Components absent from this map still appear in the lab with
 * their exact port requirements and can have their module inspected lazily.
 */
export const DIDACT_LAB_FIXTURES: Readonly<Record<string, DidactLabFixture>> = {
  'didact.flashcard': {
    props: {
      front: '¿Qué debe ocurrir antes de revelar una respuesta?',
      back: 'La persona intenta recuperarla de memoria.',
    },
    note: 'Interacción local; no persiste la valoración.',
  },
  'didact.glossary-term': {
    props: {
      entries: [
        { id: 'sla', term: 'SLA', definition: 'Tiempo acordado para responder o resolver.' },
        { id: 'escalado', term: 'Escalado', definition: 'Transferencia a un nivel especializado.' },
      ],
    },
    note: 'Contenido estático controlado.',
  },
  'didact.hint-reveal': {
    props: {
      hints: ['Busca primero el nivel de impacto.', 'Después comprueba la urgencia.'],
      solution: 'Escala cuando impacto y urgencia superan el umbral acordado.',
    },
    note: 'Pistas locales; la solución es ficticia y exclusiva del laboratorio.',
  },
  'didact.timeline-steps': {
    props: {
      steps: [
        { id: 'receive', title: 'Recibir', description: 'Registrar la solicitud.' },
        { id: 'classify', title: 'Clasificar', description: 'Comprobar impacto y urgencia.' },
        { id: 'resolve', title: 'Resolver', description: 'Aplicar o escalar la solución.' },
      ],
      currentStep: 1,
    },
    note: 'Secuencia estática de demostración.',
  },
  'didact.self-explanation-prompt': {
    props: {
      prompt: 'Explica por qué clasificarías este caso como urgente.',
      defaultValue: '',
    },
    note: 'Respuesta local descartable; no se evalúa ni persiste.',
  },
  'didact.worked-example': {
    props: {
      problem: 'Clasificar una incidencia de acceso bloqueado.',
      steps: [
        { id: 'impact', title: 'Impacto', explanation: 'Afecta a una persona.' },
        { id: 'urgency', title: 'Urgencia', explanation: 'Impide continuar su trabajo.' },
      ],
      summary: 'La prioridad combina impacto y urgencia.',
      mode: 'progressive',
    },
    note: 'Ejemplo elaborado con divulgación progresiva.',
  },
  'didact.data-explorer': {
    props: { streaming: true },
    note: 'Estado de streaming real; no inventa una serie de datos.',
  },
} satisfies Readonly<Record<string, DidactLabFixture>>

export function asLabComponent(value: unknown): DidactLabComponent {
  return value as DidactLabComponent
}

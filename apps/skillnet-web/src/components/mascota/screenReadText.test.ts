import { describe, expect, it } from 'vitest'
import { screenReadText } from './screenReadText'

/**
 * The mascot's read/speak text must follow the CURRENT screen of a paginated
 * episode. `screenReadText` is what makes that per-page: it indexes the root
 * `Stack`'s children exactly as `EpisodeStack` does and pulls out the screen's
 * own text.
 */
describe('screenReadText', () => {
  const episode = [
    'root = Stack([p0, p1, p2], "md")',
    'p0 = Stack([t0], "md")',
    't0 = TextContent("Bienvenido a la primera pantalla.", "lead")',
    'p1 = Stack([t1], "md")',
    't1 = TextContent("Ahora vamos con la segunda pantalla.", "body")',
    'p2 = Stack([c2], "md")',
    'c2 = Callout("info", "Recuerda esto en la tercera pantalla.")',
  ].join('\n')

  it('reads the text of the screen the learner is on', () => {
    expect(screenReadText(episode, 0)).toBe('Bienvenido a la primera pantalla.')
    expect(screenReadText(episode, 1)).toBe('Ahora vamos con la segunda pantalla.')
    expect(screenReadText(episode, 2)).toBe('Recuerda esto en la tercera pantalla.')
  })

  it('clamps an out-of-range screen to the last one', () => {
    expect(screenReadText(episode, 99)).toBe('Recuerda esto en la tercera pantalla.')
    expect(screenReadText(episode, -5)).toBe('Bienvenido a la primera pantalla.')
  })

  it('prefers an AudioExplanation — the text meant to be read aloud — over prose', () => {
    const program = [
      'root = Stack([p0], "md")',
      'p0 = Stack([t0, a0], "md")',
      't0 = TextContent("Un parrafo de introduccion en pantalla.", "lead")',
      'a0 = AudioExplanation("Esto es lo que se lee en voz alta.", "warm")',
    ].join('\n')
    expect(screenReadText(program, 0)).toBe('Esto es lo que se lee en voz alta.')
  })

  it('falls back to a titled block when a screen has no prose', () => {
    const program = [
      'root = Stack([p0], "md")',
      'p0 = Stack([q0], "md")',
      'q0 = QuizItem("q1", "single", "recordar", "¿Cual es la respuesta correcta?", ["A", "B"])',
    ].join('\n')
    expect(screenReadText(program, 0)).toBe('¿Cual es la respuesta correcta?')
  })

  it('returns null with no program or nothing readable, so the caller can fall back', () => {
    expect(screenReadText(null, 0)).toBeNull()
    expect(screenReadText('', 0)).toBeNull()
    expect(screenReadText('   ', 0)).toBeNull()
  })
})

import { describe, it, expect } from 'vitest'
import { tokenize, STOPWORDS_EN, STOPWORDS_ES } from './tokenize'

const join = (input: string) =>
  tokenize(input)
    .map((token) => token.text)
    .join('')

const clickableWords = (input: string) =>
  tokenize(input)
    .filter((token) => token.clickable)
    .map((token) => token.text)

describe('tokenize', () => {
  describe('verbatim re-render', () => {
    // The invariant everything else rests on: if a character can be lost, prose
    // silently changes when it becomes clickable.
    it.each([
      'El plazo de devolucion es de 30 dias.',
      '  espacios   raros\ty tabuladores\n\nsaltos  ',
      'Ninos, ninas y ninos: la accion ya esta hecha.',
      'Emoji intercalado 🙂 y otro 👩‍🚀 al final.',
      '¿Cuanto tarda? ¡Muy poco! (unos 3 dias)',
      'guion-medio, apostrofo d’acord, comillas "asi"',
      '',
      '   ',
      '...',
      '2026-07-25 · 15 %',
    ])('preserves every character of %j', (input) => {
      expect(join(input)).toBe(input)
    })
  })

  describe('word detection', () => {
    it('keeps accents and diaeresis inside a single token', () => {
      expect(clickableWords('La informacion telemática es útil')).toEqual([
        'informacion',
        'telemática',
        'útil',
      ])
    })

    it('keeps an internal apostrophe or hyphen inside one token', () => {
      expect(clickableWords("l'entrepot y el auto-servicio")).toEqual([
        "l'entrepot",
        'auto-servicio',
      ])
    })

    it('accepts the typographic apostrophe too', () => {
      expect(clickableWords('d’acord amb la norma')).toEqual(['d’acord', 'amb', 'norma'])
    })

    it('never marks punctuation or whitespace clickable', () => {
      const tokens = tokenize('Hola, mundo. ¿Que tal?')
      const glue = tokens.filter((token) => !/[\p{L}\p{N}]/u.test(token.text))
      expect(glue.length).toBeGreaterThan(0)
      expect(glue.every((token) => !token.clickable)).toBe(true)
    })

    it('never marks an emoji clickable', () => {
      expect(clickableWords('mercurio 🙂')).toEqual(['mercurio'])
    })

    it('leaves single characters inert', () => {
      expect(clickableWords('a b 7 mercurio')).toEqual(['mercurio'])
    })

    it('treats digit runs longer than one character as clickable', () => {
      // A figure is often exactly what a learner wants explained ("30 dias").
      expect(clickableWords('el plazo es 30 dias')).toEqual(['plazo', '30', 'dias'])
    })
  })

  describe('stopwords', () => {
    // The first mandatory correction of §8.2: the original list was English only, so
    // in a Spanish lesson `de`, `la` and `que` were clickable.
    it('excludes Spanish function words', () => {
      const words = clickableWords(
        'La devolucion de un producto que no se ha usado se hace en la tienda',
      )
      expect(words).toEqual(['devolucion', 'producto', 'usado', 'hace', 'tienda'])
    })

    it('excludes English function words in the same sentence', () => {
      expect(clickableWords('the return of an unused item')).toEqual(['return', 'unused', 'item'])
    })

    it('excludes both lists at once, because a course mixes languages', () => {
      expect(clickableWords('el stock of the almacen')).toEqual(['stock', 'almacen'])
    })

    it('is case insensitive', () => {
      expect(clickableWords('DE La QUE')).toEqual([])
    })

    it('covers the accented and unaccented spelling of the same word', () => {
      for (const word of ['mas', 'más', 'solo', 'sólo', 'esta', 'está', 'si', 'sí']) {
        expect(clickableWords(`xx ${word} xx`)).toEqual(['xx', 'xx'])
      }
    })

    it('has both lists populated and non-overlapping in intent', () => {
      expect(STOPWORDS_ES.size).toBeGreaterThan(100)
      expect(STOPWORDS_EN.size).toBeGreaterThan(50)
      expect(STOPWORDS_ES.has('de')).toBe(true)
      expect(STOPWORDS_EN.has('of')).toBe(true)
    })

    it('does not swallow content words that merely look short', () => {
      expect(clickableWords('IVA SKU EPI')).toEqual(['IVA', 'SKU', 'EPI'])
    })
  })
})

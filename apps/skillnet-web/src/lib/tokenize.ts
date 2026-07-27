/**
 * Word tokenizer for click-to-explain (§8.1). Pure, no dependencies.
 *
 * Ported from Curio with the first mandatory correction of §8.2: the original
 * stopword list was **English only**, so in a Spanish lesson `de`, `la` and `que`
 * were clickable while `the` and `of` were not. Here the list is the union of a
 * Spanish and an English set, because a SkillNet course can mix both.
 *
 * Two invariants the tests pin down:
 *
 * 1. `tokens.map(t => t.text).join('') === input` — every character survives, so
 *    prose re-renders verbatim and no whitespace or punctuation is invented or lost.
 * 2. Clickability is permissive by design. It only gates *decoration*: a word that
 *    slips through and gets a hover cue costs nothing, whereas a word wrongly marked
 *    inert can never be asked about.
 */

/** A single piece of text: either a clickable word or inert glue (spaces, punctuation). */
export interface Token {
  text: string
  clickable: boolean
}

/** Runs of letters/digits (with internal apostrophes/hyphens) OR runs of everything else. */
export const TOKEN_RE = /[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*|[^\p{L}\p{N}]+/gu

const WORD_RE = /[\p{L}\p{N}]/u

/**
 * Spanish function words: determiners, prepositions, conjunctions, pronouns,
 * demonstratives, relatives, high-frequency adverbs and the auxiliary/modal verbs.
 * Accented and unaccented spellings are both listed (`mas`/`más`, `solo`/`sólo`)
 * because learners' prose and generated prose disagree about accents constantly.
 */
export const STOPWORDS_ES: ReadonlySet<string> = new Set([
  // Determiners
  'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'lo', 'al', 'del',
  // Prepositions
  'ante', 'bajo', 'con', 'contra', 'de', 'desde', 'durante', 'en', 'entre',
  'hacia', 'hasta', 'mediante', 'para', 'por', 'segun', 'según', 'sin', 'sobre',
  'tras', 'via', 'vía',
  // Conjunctions
  'ni', 'pero', 'mas', 'más', 'sino', 'porque', 'pues', 'que', 'si', 'aunque',
  'como', 'cuando', 'mientras', 'ademas', 'además',
  // Pronouns
  'yo', 'tu', 'tú', 'él', 'ella', 'ello', 'nosotros', 'nosotras', 'vosotros',
  'vosotras', 'ellos', 'ellas', 'me', 'te', 'se', 'nos', 'os', 'le', 'les',
  'mi', 'mis', 'tus', 'su', 'sus', 'nuestro', 'nuestra', 'nuestros', 'nuestras',
  'vuestro', 'vuestra', 'vuestros', 'vuestras', 'usted', 'ustedes',
  // Demonstratives
  'este', 'esta', 'esto', 'estos', 'estas', 'ese', 'esa', 'eso', 'esos', 'esas',
  'aquel', 'aquella', 'aquello', 'aquellos', 'aquellas',
  // Relatives and interrogatives
  'qué', 'quien', 'quién', 'quienes', 'cual', 'cuál', 'cuales', 'cuyo',
  'cuya', 'donde', 'dónde', 'cuanto', 'cuánto', 'cómo',
  // High-frequency adverbs and quantifiers
  'no', 'sí', 'ya', 'muy', 'menos', 'tambien', 'también', 'tampoco',
  'solo', 'sólo', 'aun', 'aún', 'asi', 'así', 'ahi', 'ahí', 'alli', 'allí',
  'alla', 'allá', 'aqui', 'aquí', 'entonces', 'luego', 'despues', 'después',
  'antes', 'siempre', 'nunca', 'casi', 'todo', 'toda', 'todos', 'todas', 'algo',
  'alguien', 'algun', 'algún', 'alguna', 'algunos', 'algunas', 'nada', 'nadie',
  'ningun', 'ningún', 'ninguna', 'otro', 'otra', 'otros', 'otras', 'mismo',
  'misma', 'cada', 'tan', 'tanto',
  // Auxiliary, copular and modal verbs
  'es', 'son', 'era', 'eran', 'fue', 'fueron', 'ser', 'sido', 'siendo', 'sea',
  'sean', 'sera', 'será', 'seran', 'serán', 'está', 'estan', 'están',
  'estaba', 'estaban', 'estar', 'ha', 'han', 'he', 'hemos', 'habia', 'había',
  'habian', 'habían', 'haber', 'hay', 'puede', 'pueden', 'debe', 'deben',
  'tiene', 'tienen',
])

/** English function words. Ported from Curio unchanged, plus a handful it missed. */
export const STOPWORDS_EN: ReadonlySet<string> = new Set([
  'the', 'a', 'an', 'and', 'or', 'but', 'if', 'of', 'to', 'in', 'on', 'at',
  'by', 'for', 'with', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'am', 'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she',
  'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'our',
  'their', 'from', 'into', 'over', 'than', 'then', 'so', 'not', 'no', 'do',
  'does', 'did', 'has', 'have', 'had', 'will', 'would', 'can', 'could',
  'should', 'may', 'might', 'must', 'about', 'up', 'out', 'off', 'via', 'there',
  'here', 'when', 'while', 'which', 'who', 'whom', 'what', 'how', 'because',
])

/** The union actually consulted: a course can mix Spanish prose and English terms. */
export const STOPWORDS: ReadonlySet<string> = new Set([...STOPWORDS_ES, ...STOPWORDS_EN])

/**
 * Split text into tokens, preserving every whitespace and punctuation character so
 * the original prose renders verbatim. A token is clickable when it is a word of
 * more than one character and not a stopword.
 */
export function tokenize(text: string): Token[] {
  const parts = text.match(TOKEN_RE) ?? []
  return parts.map((part) => {
    const isWord = WORD_RE.test(part)
    const clickable = isWord && part.length > 1 && !STOPWORDS.has(part.toLowerCase())
    return { text: part, clickable }
  })
}

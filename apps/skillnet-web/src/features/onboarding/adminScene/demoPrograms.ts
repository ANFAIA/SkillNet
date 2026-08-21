import type { StatsResponse } from '../../../types'

/**
 * Bundled demo content for the admin onboarding scene (docs/design/onboarding.md
 * §3.2). Everything here is a static fixture: no backend call, no artifact id, so
 * the scene renders instantly on a brand-new deployment with nothing seeded.
 *
 * The two persona programs are hand-authored OpenUI Lang (the same dialect the
 * backend emits and `UiSpecRenderer` consumes) using only self-contained kit
 * components — `TextContent`, `Callout`, `AudioExplanation`, `Chart`,
 * `StepSequence`, `Table`. We deliberately avoid `PodcastPlayer`/`InfographicImage`
 * here: those need a real `artifact_id`, which a fresh deployment does not have.
 * The audio-vs-visual contrast is carried by the component *choice* and the tone of
 * the copy instead — the same node, explained two ways.
 *
 * Same topic ("cómo se fija un recuerdo", from the public demo course "Cómo aprende
 * tu cerebro"), same objective, opposite presentation — that contrast is the whole
 * point of the scene.
 */

export type ScenePersonaKey = 'ana' | 'bruno'

export interface ScenePersona {
  key: ScenePersonaKey
  /** Display name. */
  name: string
  /** Short style label, e.g. "audio + metáforas". */
  styleLabelId: string
  /** OpenUI Lang program fed straight to `UiSpecRenderer`. */
  program: string
}

/** Ana — audio + metáforas: a metaphor lead, an analogy callout, a spoken line. */
const ANA_PROGRAM = [
  'root = Stack([lead, analogia, audio], "md")',
  'lead = TextContent("Tu memoria es un jardinero nocturno: mientras duermes, poda lo que sobra y riega lo que de verdad importa.", "lead")',
  'analogia = Callout("info", "Igual que el jardinero no planta de día, tu cerebro fija lo aprendido sobre todo al dormir. Un repaso corto antes de acostarte le deja las semillas listas para crecer.")',
  'audio = AudioExplanation("En una frase: dormir es el momento en que tu memoria decide qué se queda y qué se olvida.", "warm")',
].join('\n')

/** Bruno — visual + definiciones: a crisp definition, a chart, ordered steps, a term table. */
const BRUNO_PROGRAM = [
  'root = Stack([lead, curva, pasos, terminos], "md")',
  'lead = TextContent("Consolidación: proceso por el que un recuerdo lábil pasa a un almacenamiento estable, dependiente del sueño y de la repetición espaciada.", "lead")',
  'curva = Chart("bar", "Cuánto se retiene sin repaso (curva del olvido)", ["20 min", "1 día", "6 días"], [58, 34, 21])',
  'pasos = StepSequence("El ciclo de la memoria", ["Codificación: la información entra y se representa en el hipocampo.", "Consolidación: durante el sueño pasa a la corteza y se estabiliza.", "Recuperación: reactivar el rastro lo refuerza mediante repaso espaciado."])',
  'terminos = Table(["Término", "Definición"], [["Lábil", "Recuerdo aún frágil, fácil de perder."], ["Repaso espaciado", "Repetir con intervalos crecientes para fijarlo."]])',
].join('\n')

export const SCENE_PERSONAS: ScenePersona[] = [
  { key: 'ana', name: 'Ana', styleLabelId: 'adminScene.persona.ana.style', program: ANA_PROGRAM },
  { key: 'bruno', name: 'Bruno', styleLabelId: 'adminScene.persona.bruno.style', program: BRUNO_PROGRAM },
]

/** The sample course the scene opens (matches the public demo showcase course). */
export const SCENE_COURSE = {
  titleId: 'adminScene.course.title',
  subtitleId: 'adminScene.course.subtitle',
}

/**
 * Fake panel figures shown once the scene "comes alive" (beat 3). Typed as the real
 * `StatsResponse` so a shape change breaks compilation here, not silently at runtime.
 * `recent_activity` is intentionally omitted from the count-up and rendered separately.
 */
export const SCENE_DEMO_STATS: StatsResponse = {
  total_employees: 14,
  active_employees: 12,
  total_courses: 6,
  published_courses: 6,
  draft_courses: 2,
  total_enrollments: 38,
  completed_enrollments: 21,
  in_progress_enrollments: 13,
  avg_score: 0.84,
  recent_activity: [
    { type: 'enrollment_completed', user_name: 'Ana López', course_title: 'Cómo aprende tu cerebro', at: '' },
    { type: 'user_created', user_name: 'Bruno Ríos', course_title: null, at: '' },
    { type: 'course_published', user_name: null, course_title: 'La ciencia de los hábitos', at: '' },
  ],
}

// Golden UISpec fixtures. THE SAME JSON FILES the backend uses (§12.3), so a
// break in the §5.2 contract fails both sides at once.
//
// Ownership: the canonical copies live with the render adapter (B1,
// `apps/skillnet-api/tests/fixtures/ui-specs/`). The eleven files imported below
// are **byte-identical copies** of that directory; `golden-drift.test.ts` fails
// the suite if the two ever diverge. Never edit one of them here — edit the
// backend copy and re-copy.
//
// The three `broken*` fixtures are frontend-only: they encode robustness cases
// (dangling ref, cycle, unknown type) that the backend validator rejects by
// design and therefore can never appear in its own fixture set. They still
// follow the serialization the backend emits (`children` always present, ids
// matching the dialect's `ident` production) so that the only thing wrong with
// them is the one thing under test.

import type { UiSpec } from '../../../types/ui-spec'

import cardNested from './card_nested.json'
import chartData from './chart_data.json'
import deepStack from './deep_stack.json'
import escapes from './escapes.json'
import exerciseOnly from './exercise_only.json'
import explanationBasic from './explanation_basic.json'
import explanationCalloutFirst from './explanation_callout_first.json'
import fallbackMarkdown from './fallback_markdown.json'
import mixedQuiz from './mixed_quiz.json'
import quizTypes from './quiz_types.json'
import tableNested from './table_nested.json'

import brokenDanglingRef from './broken-dangling-ref.json'
import brokenCycle from './broken-cycle.json'
import brokenUnknownType from './broken-unknown-type.json'

// JSON widens enums to `string`, so the cast is the price of keeping the file
// itself byte-identical to the backend's copy.
const asSpec = (raw: unknown) => raw as UiSpec

/**
 * B1's eleven canonical specs, under B1's names. Between them they exercise all
 * ten frozen kit components (§5.3):
 *
 * | component    | fixture                                            |
 * |--------------|----------------------------------------------------|
 * | Stack        | every fixture (all roots)                          |
 * | TextContent  | explanation_basic, escapes, deep_stack, …          |
 * | Card         | card_nested                                        |
 * | Callout      | explanation_callout_first, deep_stack, fallback_…  |
 * | StepSequence | explanation_basic, mixed_quiz                      |
 * | Table        | table_nested, explanation_callout_first            |
 * | CodeBlock    | card_nested                                        |
 * | Chart        | chart_data                                         |
 * | QuizItem     | exercise_only, mixed_quiz, quiz_types              |
 * | Markdown     | fallback_markdown                                  |
 */
export const goldenSpecs: Record<string, UiSpec> = {
  card_nested: asSpec(cardNested),
  chart_data: asSpec(chartData),
  deep_stack: asSpec(deepStack),
  escapes: asSpec(escapes),
  exercise_only: asSpec(exerciseOnly),
  explanation_basic: asSpec(explanationBasic),
  explanation_callout_first: asSpec(explanationCalloutFirst),
  fallback_markdown: asSpec(fallbackMarkdown),
  mixed_quiz: asSpec(mixedQuiz),
  quiz_types: asSpec(quizTypes),
  table_nested: asSpec(tableNested),
}

/** Specs the backend would reject; the renderer must survive them anyway. */
export const brokenSpecs = {
  danglingRef: asSpec(brokenDanglingRef),
  cycle: asSpec(brokenCycle),
  unknownType: asSpec(brokenUnknownType),
}

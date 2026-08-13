const SECURE_EVALUATED_COMPONENTS = new Set([
  'didact.matching',
  'didact.sort',
  'didact.categorize',
  'didact.quiz.single-choice',
  'didact.quiz.multi-select',
  'didact.quiz.true-false',
  'didact.quiz.fill-in-the-blank',
  'didact.quiz.short-answer',
  'didact.completion-problem',
  'didact.numeric-question',
  'didact.word-bank',
])

export function usesSecureEvaluationAdapter(componentId: string): boolean {
  return SECURE_EVALUATED_COMPONENTS.has(componentId)
}

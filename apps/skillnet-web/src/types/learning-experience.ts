/**
 * Provider-neutral reference fixed by the course runtime before rendering.
 *
 * `activityId` and `componentId` are temporary compatibility fields for the
 * current Didact API. New providers must rely on the three neutral refs.
 */
export type LearningExperienceReference = Readonly<{
  experienceId: string
  implementationRef: string
  definitionRef: string
  /** Learner-safe projection supplied by the host after resolving definitionRef. */
  publicDefinition?: unknown
  activityId?: string
  componentId?: string
}>

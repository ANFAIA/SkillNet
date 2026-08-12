export const COMPONENT_ROLES = [
  "primitive",
  "interaction",
  "display",
  "composite",
  "headless",
  "adapter",
] as const;

export type ComponentRole = (typeof COMPONENT_ROLES)[number];

export const COMPONENT_FAMILIES = [
  "assessment",
  "retrieval-practice",
  "generative-learning",
  "feedback-scaffolding",
  "knowledge-representation",
  "sequence-procedure",
  "progress-mastery",
  "media",
  "scenario-simulation",
  "technical-practice",
  "authoring",
  "interoperability",
] as const;

export type ComponentFamily = (typeof COMPONENT_FAMILIES)[number];

export const SUBJECT_FACETS = [
  "general",
  "language",
  "mathematics",
  "science",
  "data",
  "business",
  "creative",
  "technical",
  "humanities",
] as const;

export type SubjectFacet = (typeof SUBJECT_FACETS)[number];

export const REPRESENTATION_FACETS = [
  "text",
  "numeric",
  "symbolic",
  "data-series",
  "spatial",
  "image",
  "temporal",
  "audio",
  "video",
  "procedural",
  "system",
  "network",
  "artifact",
] as const;

export type RepresentationFacet = (typeof REPRESENTATION_FACETS)[number];

export const LEARNER_ACTION_FACETS = [
  "inspect",
  "select",
  "respond",
  "write",
  "order",
  "relate",
  "manipulate",
  "construct",
  "calculate",
  "experiment",
  "interpret",
  "explain",
  "create",
  "execute",
  "decide",
  "collaborate",
] as const;

export type LearnerActionFacet = (typeof LEARNER_ACTION_FACETS)[number];

export const LEARNING_PURPOSE_FACETS = [
  "present",
  "explore",
  "practice",
  "retrieve",
  "assess",
  "scaffold",
  "reflect",
  "create",
  "simulate",
  "collaborate",
  "orchestrate",
] as const;

export type LearningPurposeFacet = (typeof LEARNING_PURPOSE_FACETS)[number];

export const LEARNING_CONTEXT_FACETS = [
  "self-paced",
  "classroom",
  "corporate",
  "compliance",
  "onboarding",
  "instructor-led",
  "technical-training",
] as const;

export type LearningContextFacet = (typeof LEARNING_CONTEXT_FACETS)[number];

export function isComponentRole(value: unknown): value is ComponentRole {
  return typeof value === "string" && COMPONENT_ROLES.some((role) => role === value);
}

export function isComponentFamily(value: unknown): value is ComponentFamily {
  return typeof value === "string" && COMPONENT_FAMILIES.some((family) => family === value);
}

export function isSubjectFacet(value: unknown): value is SubjectFacet {
  return typeof value === "string" && SUBJECT_FACETS.some((facet) => facet === value);
}

export function isRepresentationFacet(value: unknown): value is RepresentationFacet {
  return typeof value === "string" && REPRESENTATION_FACETS.some((facet) => facet === value);
}

export function isLearnerActionFacet(value: unknown): value is LearnerActionFacet {
  return typeof value === "string" && LEARNER_ACTION_FACETS.some((facet) => facet === value);
}

export function isLearningPurposeFacet(value: unknown): value is LearningPurposeFacet {
  return typeof value === "string" && LEARNING_PURPOSE_FACETS.some((facet) => facet === value);
}

export function isLearningContextFacet(value: unknown): value is LearningContextFacet {
  return typeof value === "string" && LEARNING_CONTEXT_FACETS.some((facet) => facet === value);
}

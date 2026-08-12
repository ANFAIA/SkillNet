/**
 * Spaced-repetition agnostic interface.
 *
 * Source: `specs/education-components/research.md` Question 4 ("Which spaced-repetition
 * algorithm is reasonable without a heavy dependency, and how should its API be designed to be
 * agnostic of where state is persisted?"). The interface below is research.md's EXACT proposal,
 * derived from how `ts-fsrs` already solves the same problem.
 *
 * Key contract (RF-2 in `requirements.md`): the scheduler NEVER persists anything. It receives
 * the current state, returns the next state; the consuming project decides where that state
 * lives (localStorage, its own database, etc.). This is what lets SkillNet or any other consumer
 * integrate it without the library imposing a storage model.
 */

/**
 * Review state of a card. Deliberately opaque at the type level: each algorithm defines its own
 * internal shape (SM2State: n/EF/I; FSRSState: S/D/reps/lapses/dates; LeitnerState: an integer
 * box) without the consumer needing to know it — it just has to store it and return it as-is.
 */
export type ReviewState = Record<string, unknown>;

/**
 * Grade the user gives their own recall after seeing the answer. Vocabulary taken from
 * FSRS/Anki (research.md P4), also reusable for an SM-2 scheduler by mapping
 * "again"/"hard" to failure (q<3) and "good"/"easy" to success (q>=3).
 */
export type ReviewGrade = "again" | "hard" | "good" | "easy";

/**
 * Result of scheduling a review: the new opaque state to persist and the date the card becomes
 * due again. Retrieval-practice orchestrators (a layer above, in `@didact/core`, RF-2) use `dueAt` to
 * decide which card to show next.
 */
export interface ReviewResult {
  state: ReviewState;
  dueAt: Date;
}

/**
 * Contract each algorithm implements (SM-2, FSRS, and optionally Leitner as a "simple mode").
 * `schedule` is a pure function: the same (state, grade, now) always produces the same result,
 * with no side effects or I/O — a necessary condition for it to be persistence-agnostic.
 */
export interface SpacedRepetitionScheduler {
  /** Creates the initial state of a new card (first time it's seen). */
  createInitialState(): ReviewState;

  /** Computes the next state and the next review date given a grade. Pure. */
  schedule(state: ReviewState, grade: ReviewGrade, now?: Date): ReviewResult;

  /**
   * Optional: previews the outcome of every possible grade without applying it, useful to show
   * the user "if you say 'good' it'll come back in 4 days" before they decide.
   */
  preview?(state: ReviewState, now?: Date): Record<ReviewGrade, ReviewResult>;
}

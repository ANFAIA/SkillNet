/**
 * SM-2 — Didact's default spaced-repetition algorithm.
 *
 * Source: `specs/education-components/research.md` Question 4. Formulas verified against:
 * - https://www.supermemo.com/en/archives1990-2015/english/ol/sm2 (original specification)
 * - https://en.wikipedia.org/wiki/SM-2_(algorithm)
 *
 * Why SM-2 is the default (research.md P4):
 * - ~40-60 lines of pure arithmetic, zero external dependencies.
 * - 35+ years in production (SuperMemo, Anki until 2023, and still an option today).
 * - "Medium" evidence in research.md's table (vs. "high" for FSRS, but FSRS costs 100-250 lines
 *   and an external library choice — see `fsrs.ts`).
 *
 * Algorithm parameters (verified against the sources above):
 * - Initial easiness factor (EF): 2.5, with a floor of 1.3 (never goes below that).
 * - Answer quality rating q in [0,5] in the original specification; this module derives it from
 *   the `ReviewGrade` vocabulary in `types.ts` (again/hard/good/easy) to keep a single rating
 *   scale across the whole library (see `SM2_GRADE_TO_QUALITY` below).
 * - q >= 3 (success): the repetition counter grows and the interval (I) grows — I(1)=1 day,
 *   I(2)=6 days, and thereafter I(n) = round(I(n-1) * EF).
 * - q < 3 (failure): the repetition counter resets to 0 and the interval goes back to 1 day.
 *
 * The easiness factor is recomputed on EVERY review (both success and failure), per the
 * canonical Wikipedia pseudocode, using:
 *
 *     EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))     clamped to a floor of 1.3
 *
 * The original SuperMemo write-up (step 6) is sometimes read as "don't change EF on a failed
 * repetition", but the widely-implemented reading (Wikipedia, most open-source SM-2 ports) applies
 * the EF update unconditionally — which is also what makes the documented 1.3 floor reachable at
 * all (a "good"/"easy"-only EF update can never decrease EF, so the floor would be dead code).
 * Didact follows the unconditional form so that repeated "again"/"hard" grades genuinely drive EF
 * down toward the 1.3 floor, matching how a learner who keeps failing a card should see it come
 * back ever more often rather than the interval creeping up.
 *
 * Persistence contract (RF-2): `schedule` is a pure function of (state, grade, now). It never
 * reads or writes storage; it returns the next opaque `state` for the consumer to persist wherever
 * it likes, plus the `dueAt` date the card next becomes due. Same (state, grade, now) always
 * produces the same result.
 */

import type {
  ReviewGrade,
  ReviewResult,
  ReviewState,
  SpacedRepetitionScheduler,
} from "./types";

/** Internal shape of SM-2 state, see research.md P4 (algorithm table). */
export interface SM2State extends ReviewState {
  /** Number of consecutive successful repetitions (q >= 3). Resets to 0 on a failure. */
  repetitions: number;
  /** Easiness factor. Initial 2.5, floor 1.3. */
  easinessFactor: number;
  /** Current interval in days until the next review. */
  intervalDays: number;
}

const INITIAL_EASINESS_FACTOR = 2.5;
const MINIMUM_EASINESS_FACTOR = 1.3;
const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

/**
 * Mapping from `ReviewGrade` (the library's common vocabulary) to the q∈[0,5] quality scale of
 * the original SM-2 specification. "again"/"hard" fall below the q=3 threshold (failure, resets
 * repetitions); "good"/"easy" clear it (success, grows the interval).
 */
export const SM2_GRADE_TO_QUALITY: Record<ReviewGrade, number> = {
  again: 0,
  hard: 2,
  good: 4,
  easy: 5,
};

/** Success threshold on the q∈[0,5] scale (q >= 3 is a successful recall). */
const SUCCESS_QUALITY_THRESHOLD = 3;

/**
 * Type guard: is this opaque `ReviewState` shaped like SM-2 state? Used so `schedule` can accept a
 * plain `ReviewState` (the agnostic interface's type) but fail loudly if handed something that
 * clearly is not SM-2 state, instead of silently computing on `NaN`.
 */
function isSM2State(state: ReviewState): state is SM2State {
  return (
    typeof state.repetitions === "number" &&
    typeof state.easinessFactor === "number" &&
    typeof state.intervalDays === "number"
  );
}

/** Recompute the easiness factor from the previous EF and the quality grade, clamped to the floor. */
function nextEasinessFactor(previous: number, quality: number): number {
  const updated = previous + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
  return Math.max(MINIMUM_EASINESS_FACTOR, updated);
}

/**
 * SM-2 scheduler. Pure arithmetic, no persistence — the default `SpacedRepetitionScheduler` for
 * Didact retrieval-practice flows (`@didact/core`, RF-2).
 */
export const sm2Scheduler: SpacedRepetitionScheduler = {
  createInitialState(): SM2State {
    return {
      repetitions: 0,
      easinessFactor: INITIAL_EASINESS_FACTOR,
      intervalDays: 0,
    };
  },

  schedule(state: ReviewState, grade: ReviewGrade, now: Date = new Date()): ReviewResult {
    if (!isSM2State(state)) {
      throw new TypeError(
        "@didact/spaced-repetition/sm2: schedule() received a state that is not SM-2 state " +
          "(expected numeric repetitions/easinessFactor/intervalDays). Did you seed it from a " +
          "different scheduler? Use sm2Scheduler.createInitialState() for new cards.",
      );
    }

    const quality = SM2_GRADE_TO_QUALITY[grade];
    const easinessFactor = nextEasinessFactor(state.easinessFactor, quality);

    let repetitions: number;
    let intervalDays: number;

    if (quality >= SUCCESS_QUALITY_THRESHOLD) {
      // Successful recall: grow the repetition count and the interval.
      repetitions = state.repetitions + 1;
      if (repetitions === 1) {
        intervalDays = 1;
      } else if (repetitions === 2) {
        intervalDays = 6;
      } else {
        intervalDays = Math.round(state.intervalDays * easinessFactor);
      }
    } else {
      // Failure: restart the repetition schedule from the beginning (I(1) = 1 day).
      repetitions = 0;
      intervalDays = 1;
    }

    const nextState: SM2State = { repetitions, easinessFactor, intervalDays };
    const dueAt = new Date(now.getTime() + intervalDays * MILLISECONDS_PER_DAY);

    return { state: nextState, dueAt };
  },

  preview(state: ReviewState, now: Date = new Date()): Record<ReviewGrade, ReviewResult> {
    return {
      again: this.schedule(state, "again", now),
      hard: this.schedule(state, "hard", now),
      good: this.schedule(state, "good", now),
      easy: this.schedule(state, "easy", now),
    };
  },
};

/** Exported so consumers/tests can reference the documented EF floor without re-deriving it. */
export const SM2_MINIMUM_EASINESS_FACTOR = MINIMUM_EASINESS_FACTOR;
/** Exported so consumers/tests can reference the documented initial EF without re-deriving it. */
export const SM2_INITIAL_EASINESS_FACTOR = INITIAL_EASINESS_FACTOR;

import { create } from 'zustand'

/**
 * Shared run-state for the employee tour. The overlay lives in the employee shell
 * while the reopen "?" trigger lives in the header — two siblings that need one
 * boolean between them, so it is a tiny store rather than prop-drilling through the
 * layout. It holds only "is the tour running right now"; persistence of whether the
 * user has *seen* it lives in `storage.ts` (localStorage).
 */
interface TourStore {
  run: boolean
  /** Bumped on every (re)start so the runner can reset joyride to step 0. */
  runId: number
  /**
   * Current step index. Only the admin tour uses it: its steps sit on different
   * screens, so the runner drives joyride in controlled mode and needs the index to
   * survive the client-side navigation between one step's route and the next. The
   * store is a module singleton, so it persists across those SPA route changes; a
   * mirror in localStorage (storage.ts `lastStepId`) survives a full reload.
   */
  index: number
  start: () => void
  stop: () => void
  setIndex: (index: number) => void
}

export const useTourStore = create<TourStore>((set) => ({
  run: false,
  runId: 0,
  index: 0,
  // A (re)start always resets to the first step (docs/design/onboarding.md §2.4).
  start: () => set((s) => ({ run: true, runId: s.runId + 1, index: 0 })),
  stop: () => set({ run: false }),
  setIndex: (index) => set({ index }),
}))

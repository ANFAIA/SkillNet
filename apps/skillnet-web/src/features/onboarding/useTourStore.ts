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
  start: () => void
  stop: () => void
}

export const useTourStore = create<TourStore>((set) => ({
  run: false,
  runId: 0,
  start: () => set((s) => ({ run: true, runId: s.runId + 1 })),
  stop: () => set({ run: false }),
}))

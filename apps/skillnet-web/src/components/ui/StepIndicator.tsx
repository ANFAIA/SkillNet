export interface StepIndicatorProps {
  /** Zero-based index of the current step. */
  current: number
  /** Total number of steps. */
  total: number
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

/**
 * Dots-and-rails step progress for multi-step flows.
 *
 * Extracted verbatim from `pages/admin/CreateCourse.tsx` (§13, B8) so the
 * onboarding wizard and the course wizard show the same progress affordance.
 * Pure refactor: same markup, same classes, same behaviour.
 *
 * It renders digits, so a screen reader reads "1 2 3 4 5". Callers that care
 * should wrap it in `aria-hidden` and expose the step count as text — the
 * wizard in `pages/onboarding/Onboarding.tsx` does exactly that.
 */
export function StepIndicator({ current, total }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-1 sm:gap-2">
          <div
            className={`w-6 h-6 sm:w-7 sm:h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors shrink-0 ${
              i < current ? 'bg-accent text-white' : i === current ? 'bg-primary text-white' : 'bg-bg-muted text-text-muted'
            }`}
          >
            {i < current ? <CheckIcon /> : i + 1}
          </div>
          {i < total - 1 && (
            <div className={`w-4 sm:w-8 h-px transition-colors ${i < current ? 'bg-accent' : 'bg-border'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

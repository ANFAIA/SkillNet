import { useState } from 'react'
import { useIntl } from 'react-intl'
import { useCapabilities } from '../../api/setup'

/**
 * Consolidated, dismissible "what is degraded" notice for the admin surface
 * (docs/design/degraded-mode-ux.md §1). SkillNet keeps working when external keys
 * are missing — it just degrades in concrete, invisible ways (robotic offline voice,
 * infographics without a poster, no AI at all). This banner makes those states
 * visible and calm, at the deployment level where they actually live.
 *
 * One banner, not three stacked bars: each capability that is off contributes one
 * line. Nothing shows when everything is present (same discipline as the rest of
 * Settings). Keys are not entered here — they live in the deployment `.env` — so this
 * only informs and points there; it never offers a form.
 *
 * Ordered by severity: `ai` first (nothing AI works without it), then `tts`, then
 * `images`.
 */
export function CapabilityHealthBanner() {
  const intl = useIntl()
  const { ai, tts, images } = useCapabilities()
  const [dismissed, setDismissed] = useState(false)

  const lines: string[] = []
  if (!ai) lines.push(intl.formatMessage({ id: 'capabilityBanner.ai' }))
  if (!tts) lines.push(intl.formatMessage({ id: 'capabilityBanner.tts' }))
  if (!images) lines.push(intl.formatMessage({ id: 'capabilityBanner.images' }))

  if (lines.length === 0 || dismissed) return null

  return (
    <div
      role="status"
      className="relative mt-4 rounded-lg border border-warning/40 bg-warning/5 p-3 pr-10"
    >
      <p className="text-sm font-medium text-text">
        {intl.formatMessage({ id: 'capabilityBanner.title' })}
      </p>
      <ul className="mt-1 space-y-1">
        {lines.map((line) => (
          <li key={line} className="text-sm text-text-secondary">
            {line}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-text-muted">
        {intl.formatMessage({ id: 'capabilityBanner.envHint' })}
      </p>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label={intl.formatMessage({ id: 'capabilityBanner.dismiss' })}
        className="absolute right-2 top-2 grid size-7 place-items-center rounded-full text-text-muted transition-colors hover:text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 cursor-pointer"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

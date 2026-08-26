import { useState } from 'react'
import { useIntl } from 'react-intl'
import { isReady, useCapabilities, type CapabilityName } from '../../api/setup'
import { capabilityTag } from '../../lib/capabilityCopy'

/** Watched in severity order: `ai` first (nothing AI works without it), then voice, then images. */
const WATCHED: CapabilityName[] = ['ai', 'tts', 'images']

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
 * This is the **deployment-level** half of the degraded-mode story; the per-control
 * half is `<Gated mode="explain">`, which says why *this button* is inert. They must
 * not restate each other, so the banner keeps its own summary sentence and adds only
 * what it never had: the machine-readable reason, as a short tag, plus the backend's
 * admin-only `hint` when it sent one. This surface is admin-only, which is why the
 * hint may be rendered here at all.
 */
export function CapabilityHealthBanner() {
  const intl = useIntl()
  const capabilities = useCapabilities()
  const [dismissed, setDismissed] = useState(false)

  const lines = WATCHED.filter((name) => !isReady(capabilities[name])).map((name) => ({
    name,
    text: intl.formatMessage({ id: `capabilityBanner.${name}` }),
    tag: capabilityTag(intl, capabilities[name]),
    hint: capabilities[name].hint ?? null,
  }))

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
          <li key={line.name} className="text-sm text-text-secondary">
            {line.tag && (
              <span className="mr-2 rounded border border-warning/40 px-1.5 py-0.5 text-xs font-medium text-text-muted">
                {line.tag}
              </span>
            )}
            {line.text}
            {line.hint && <span className="block text-xs text-text-muted">{line.hint}</span>}
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

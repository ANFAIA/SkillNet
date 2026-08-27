import { useIntl } from 'react-intl'

export interface PagerProps {
  /** Index of the first row on screen. */
  offset: number
  /** How many rows arrived — not the page size: the last page is short. */
  shown: number
  /** How many rows match, across every page. */
  total: number
  pageSize: number
  onChange: (offset: number) => void
  disabled?: boolean
  /** Extra classes for the wrapper. */
  className?: string
}

/**
 * "1-25 de 240", with the two buttons that move between them.
 *
 * The range is rendered **always**, not only when the list overflows. That line is what
 * tells the reader the list is a window onto something larger in the first place — the
 * defect it exists for was a picker that showed the API's default fifty employees with
 * nothing on screen to suggest a fifty-first, so a company of sixty could not assign
 * anything to ten of its people and the screen looked complete.
 *
 * Deliberately dumb: it owns no state and does no fetching. Three screens page over
 * three different endpoints, and the only thing they share is this arithmetic.
 */
export function Pager({
  offset,
  shown,
  total,
  pageSize,
  onChange,
  disabled = false,
  className = '',
}: PagerProps) {
  const intl = useIntl()
  const shownTo = offset + shown

  return (
    <div className={`flex items-center justify-between gap-3 ${className}`}>
      <p className="text-xs text-text-muted">
        {intl.formatMessage(
          { id: 'people.pageRange' },
          { from: total === 0 ? 0 : offset + 1, to: shownTo, total },
        )}
      </p>
      <div className="flex gap-1">
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-1 text-xs text-text-secondary disabled:opacity-40"
          disabled={disabled || offset === 0}
          onClick={() => onChange(Math.max(0, offset - pageSize))}
        >
          {intl.formatMessage({ id: 'people.previous' })}
        </button>
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-1 text-xs text-text-secondary disabled:opacity-40"
          disabled={disabled || shownTo >= total}
          onClick={() => onChange(offset + pageSize)}
        >
          {intl.formatMessage({ id: 'people.next' })}
        </button>
      </div>
    </div>
  )
}

import { useDeferredValue, useState } from 'react'
import { useUsers, USERS_PAGE_SIZE, type UserFilters } from '../../api/users'
import type { User } from '../../types'
import { Pager, SearchField } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'

interface PeoplePickerProps {
  /** Extra server-side narrowing: a group, its complement, only active people… */
  filters?: Omit<UserFilters, 'search' | 'offset' | 'limit'>
  /** Accessible label for the search box. */
  searchLabel: string
  /** Rendered on the right of each row: the control, whatever it is. */
  renderAction: (person: User) => React.ReactNode
  /** Optional secondary line under the email — "already has 2 of 3", say. */
  renderNote?: (person: User) => React.ReactNode
  emptyMessage: string
  pageSize?: number
}

/**
 * A searchable, paginated list of people, with one caller-supplied control per row.
 *
 * Every screen that has to pick people out of an organization needs the same three
 * things and used to get none of them: a search box, a page at a time, and a line that
 * says how many did **not** fit. The folder-assignment dialog rendered the API's default
 * first fifty employees and called it the team — a company with sixty simply could not
 * assign anything to the last ten, and nothing on screen said why.
 *
 * Search and paging are both server-side (`GET /users`). Filtering a page in the browser
 * only ever finds the matches that happened to land on it, which is the same bug wearing
 * a different hat.
 *
 * The row control is a render prop rather than a fixed checkbox on purpose: the two
 * callers mean genuinely different things by it — a membership *state* that toggles both
 * ways, and a staged *action* — and giving them the same widget is how a control comes
 * to lie about what it does.
 */
export function PeoplePicker({
  filters,
  searchLabel,
  renderAction,
  renderNote,
  emptyMessage,
  pageSize = USERS_PAGE_SIZE,
}: PeoplePickerProps) {
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  // The box stays instant; the query lags one keystroke behind instead of firing a
  // request per character. Same treatment as the course library's search.
  const deferredSearch = useDeferredValue(search.trim())
  const query = useUsers({
    ...filters,
    search: deferredSearch || undefined,
    offset,
    limit: pageSize,
  })
  const people = query.data?.items ?? []
  const total = query.data?.total ?? 0

  function changeSearch(value: string) {
    setSearch(value)
    // Page 3 of the old result set is meaningless for the new one, and staying there is
    // how a search comes back "empty" for a term with plenty of matches.
    setOffset(0)
  }

  return (
    <div className="space-y-3">
      <SearchField
        label={searchLabel}
        placeholder={searchLabel}
        value={search}
        onChange={(event) => changeSearch(event.target.value)}
      />
      <div className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
        {query.isLoading ? (
          <div className="space-y-3 py-4" aria-hidden="true">
            <ShimmerSkeleton className="h-10 w-full" />
            <ShimmerSkeleton className="h-10 w-full" />
            <ShimmerSkeleton className="h-10 w-full" />
          </div>
        ) : people.length === 0 ? (
          <p className="py-4 text-sm text-text-muted">{emptyMessage}</p>
        ) : (
          people.map((person) => (
            <div key={person.id} className="flex items-center gap-3 py-3">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-text">{person.full_name}</span>
                <span className="block truncate text-xs text-text-muted">{person.email}</span>
                {renderNote?.(person)}
              </span>
              <span className="shrink-0">{renderAction(person)}</span>
            </div>
          ))
        )}
      </div>
      <Pager
        offset={offset}
        shown={people.length}
        total={total}
        pageSize={pageSize}
        disabled={query.isFetching}
        onChange={setOffset}
      />
    </div>
  )
}

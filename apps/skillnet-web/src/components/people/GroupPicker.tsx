import { useDeferredValue, useState } from 'react'
import { useUserGroups, type UserGroup, type UserGroupFilters } from '../../api/user-groups'
import { Pager, SearchField } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'

interface GroupPickerProps {
  /** Extra server-side narrowing: the person whose groups must not be offered. */
  filters?: Omit<UserGroupFilters, 'search' | 'offset' | 'limit'>
  /** Accessible label for the search box. */
  searchLabel: string
  /** Rendered on the right of each row: the control, whatever it is. */
  renderAction: (group: UserGroup) => React.ReactNode
  emptyMessage: string
  pageSize?: number
}

/** A short list, because this sits inside a person's record and not on a screen of its own. */
export const GROUP_PICKER_PAGE_SIZE = 5

/**
 * A searchable, paginated list of groups, with one caller-supplied control per row.
 *
 * `PeoplePicker` for the other side of a membership, and the same argument: the thing
 * being picked out of has no ceiling on its size, so the picker needs a search box, a
 * page at a time, and a line saying how many did **not** fit. A `<select>` with every
 * group in it is fine at three and unusable at two hundred, and nothing about the
 * control says which of those you are looking at.
 *
 * Search, paging and the exclusion are all server-side (`GET /user-groups`). Filtering
 * the page here would only ever find the groups that happened to land on it.
 */
export function GroupPicker({
  filters,
  searchLabel,
  renderAction,
  emptyMessage,
  pageSize = GROUP_PICKER_PAGE_SIZE,
}: GroupPickerProps) {
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  // The box stays instant; the query lags one keystroke behind instead of firing a
  // request per character.
  const deferredSearch = useDeferredValue(search.trim())
  const query = useUserGroups({
    ...filters,
    search: deferredSearch || undefined,
    offset,
    limit: pageSize,
  })
  const groups = query.data?.items ?? []
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
      <div className="max-h-56 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
        {query.isLoading ? (
          <div className="space-y-3 py-4" aria-hidden="true">
            <ShimmerSkeleton className="h-8 w-full" />
            <ShimmerSkeleton className="h-8 w-full" />
          </div>
        ) : groups.length === 0 ? (
          <p className="py-4 text-sm text-text-muted">{emptyMessage}</p>
        ) : (
          groups.map((group) => (
            <div key={group.id} className="flex items-center gap-3 py-2">
              <span className="min-w-0 flex-1 truncate text-sm text-text">{group.name}</span>
              <span className="shrink-0">{renderAction(group)}</span>
            </div>
          ))
        )}
      </div>
      <Pager
        offset={offset}
        shown={groups.length}
        total={total}
        pageSize={pageSize}
        disabled={query.isFetching}
        onChange={setOffset}
      />
    </div>
  )
}

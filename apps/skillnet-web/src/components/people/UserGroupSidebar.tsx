import { useDeferredValue, useEffect, useState, type FormEvent } from 'react'
import { useIntl } from 'react-intl'
import { apiErrorMessage } from '../../lib/apiErrors'
import {
  useCreateUserGroup,
  useDeleteUserGroup,
  useRenameUserGroup,
  useUserGroups,
  type UserGroup,
} from '../../api/user-groups'
import { Button, Input, Pager, SearchField } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'

/**
 * `'all'` is everybody, `'ungrouped'` is the people in no group, anything else is a
 * group id.
 *
 * The two virtual rows mirror the course library's "Todos" / "Sin organizar": the
 * question "who have I not covered yet?" has no other answer, and a paginated list
 * cannot be scanned by eye for it.
 */
export type GroupFilter = 'all' | 'ungrouped' | string

/**
 * Rows per page in the rail.
 *
 * Smaller than the people table's 25 because this is a column, not a table: twenty-five
 * rows in a 264px rail is a scroll long enough to hide the list it is meant to filter.
 */
export const GROUPS_RAIL_PAGE_SIZE = 10

function GroupIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function EditIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m4 20 4.5-1 11-11-3.5-3.5-11 11Z" /><path d="m14.5 6 3.5 3.5" /></svg>
}

function TrashIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" /></svg>
}

function BookIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z" /><path d="M4 19a2 2 0 0 1 2-2h13" /></svg>
}

function MembersIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M19 8v6M22 11h-6" /></svg>
}

function PlusIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
}

interface UserGroupSidebarProps {
  selected: GroupFilter
  /** Everyone in the organization, for the "All" row's count. */
  totalCount: number
  /** How many people belong to no group at all. */
  ungroupedCount: number
  onSelect: (value: GroupFilter) => void
  onManageMembers: (group: UserGroup) => void
  onAssign: (group: UserGroup) => void
}

/**
 * The people screen's group rail.
 *
 * Deliberately the same shape as `CourseFolderSidebar` in the course library: a flat
 * list that filters the paginated list beside it, with create / rename / delete inline
 * and the collection's own actions on hover. It is the same problem — a flat collection
 * narrowing a list too long to hold in one page — so it gets the same answer rather than
 * a second pattern the admin has to learn.
 *
 * It owns its own query rather than taking a `groups` prop, because search and page
 * number are its state and a parent holding them would only be a longer way of saying
 * the same thing. Both are server-side: the response is one page, so filtering it here
 * would find the groups that happened to land on it and call the rest non-existent.
 *
 * The two virtual rows are outside all of that. They are views, not groups, and they
 * stay at the top through every search and every page.
 */
export function UserGroupSidebar({
  selected,
  totalCount,
  ungroupedCount,
  onSelect,
  onManageMembers,
  onAssign,
}: UserGroupSidebarProps) {
  const intl = useIntl()
  const createGroup = useCreateUserGroup()
  const renameGroup = useRenameUserGroup()
  const deleteGroup = useDeleteUserGroup()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  // The box stays instant; the query lags one keystroke behind instead of firing a
  // request per character. Same treatment as the people list beside it.
  const deferredSearch = useDeferredValue(search.trim())
  const query = useUserGroups({
    search: deferredSearch || undefined,
    offset,
    limit: GROUPS_RAIL_PAGE_SIZE,
  })
  const groups = query.data?.items ?? []
  const total = query.data?.total ?? 0

  // A latch, not `total > GROUPS_RAIL_PAGE_SIZE` read directly: changing the search term
  // changes the query key, so `data` is briefly undefined and `total` reads 0. Deriving
  // the box's existence from that number makes it unmount mid-word when the admin clears
  // what they typed. Once a rail has overflowed it keeps its search box.
  const [searchable, setSearchable] = useState(false)
  useEffect(() => {
    if (total > GROUPS_RAIL_PAGE_SIZE) setSearchable(true)
  }, [total])
  const showSearch = searchable || deferredSearch.length > 0

  // The selected group is not necessarily on the page being shown — the admin can page
  // past it, or search for something else. A filter that is still narrowing the list
  // beside the rail while its own row has vanished is disorienting, so the last copy the
  // server sent of the selected group is kept and pinned above the page when it is not
  // in it. Kept fresh whenever it *is* on the page; while it is off the page its member
  // count is as old as the last time it was on one, which is the price of not asking for
  // it a second time.
  const [pinned, setPinned] = useState<UserGroup | null>(null)
  const onPage = groups.find((group) => group.id === selected)
  useEffect(() => {
    if (onPage) setPinned(onPage)
  }, [onPage])
  const strayGroup = !onPage && pinned?.id === selected ? pinned : null

  function changeSearch(value: string) {
    setSearch(value)
    // Page 3 of the old result set is meaningless for the new one, and staying there is
    // how a search comes back "empty" for a term with plenty of matches.
    setOffset(0)
  }

  async function submitCreate(event: FormEvent) {
    event.preventDefault()
    const name = newName.trim()
    if (!name) return
    setError(null)
    try {
      await createGroup.mutateAsync(name)
      setNewName('')
      setCreating(false)
    } catch (reason) {
      // A duplicate name is a 409 whose message is the useful one.
      setError(apiErrorMessage(intl, reason, 'groups.saveError'))
    }
  }

  async function submitRename(event: FormEvent, id: string) {
    event.preventDefault()
    const name = editingName.trim()
    if (!name) return
    setError(null)
    try {
      await renameGroup.mutateAsync({ id, name })
      // The pinned copy is not refetched while it is off the page, so a rename made from
      // its own row would leave the old name on screen until it came back.
      setPinned((current) => (current && current.id === id ? { ...current, name } : current))
      setEditingId(null)
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'groups.saveError'))
    }
  }

  async function removeGroup(group: UserGroup) {
    // The confirmation says what deleting does NOT do. Without that sentence the admin
    // has to guess whether the training the group handed out disappears with it.
    if (!window.confirm(intl.formatMessage({ id: 'groups.deleteConfirm' }, { name: group.name, count: group.member_count }))) return
    setError(null)
    try {
      await deleteGroup.mutateAsync(group.id)
      setPinned((current) => (current && current.id === group.id ? null : current))
      if (selected === group.id) onSelect('all')
      // Deleting the only row of the last page would otherwise leave the rail on a page
      // that no longer exists, showing nothing and blaming the search.
      if (groups.length === 1 && offset > 0) setOffset(Math.max(0, offset - GROUPS_RAIL_PAGE_SIZE))
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'groups.deleteError'))
    }
  }

  function filterButton(value: GroupFilter, label: string, count: number | undefined) {
    const active = selected === value
    return (
      <button
        type="button"
        onClick={() => onSelect(value)}
        aria-current={active ? 'true' : undefined}
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${active ? 'bg-primary-subtle text-primary font-medium' : 'text-text-secondary hover:bg-bg-muted hover:text-text'}`}
      >
        <GroupIcon />
        <span className="truncate flex-1">{label}</span>
        {count !== undefined && <span className="text-xs tabular-nums text-text-muted">{count}</span>}
      </button>
    )
  }

  function groupRow(group: UserGroup) {
    if (editingId === group.id) {
      return (
        <form onSubmit={(event) => submitRename(event, group.id)} className="space-y-2 p-1">
          <Input autoFocus value={editingName} maxLength={120} aria-label={intl.formatMessage({ id: 'groups.name' })} onChange={(event) => setEditingName(event.target.value)} />
          <div className="flex gap-1">
            <Button size="sm" type="submit" disabled={!editingName.trim() || renameGroup.isPending}>{intl.formatMessage({ id: 'groups.save' })}</Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setEditingId(null)}>{intl.formatMessage({ id: 'groups.cancel' })}</Button>
          </div>
        </form>
      )
    }
    return (
      // `relative` + an absolutely positioned action cluster, and not a flex row:
      // the four buttons are invisible until hover but a flex sibling still takes
      // its width, which left about seven pixels for the name — every group in the
      // rail rendered as "Tu..." or "Gr...". Out of flow, the label gets the whole
      // row, and the buttons sit over its tail on hover with the rail's own
      // background behind them so nothing shows through.
      <div className="relative flex items-center">
        <div className="min-w-0 flex-1">{filterButton(group.id, group.name, group.member_count)}</div>
        <div className="absolute inset-y-0 right-0 flex items-center rounded-lg bg-bg pl-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
          <button type="button" aria-label={intl.formatMessage({ id: 'groups.manageMembers' }, { name: group.name })} className="p-1.5 text-text-muted hover:text-text" onClick={() => onManageMembers(group)}><MembersIcon /></button>
          <button type="button" aria-label={intl.formatMessage({ id: 'groups.assign' }, { name: group.name })} className="p-1.5 text-text-muted hover:text-text" onClick={() => onAssign(group)}><BookIcon /></button>
          <button type="button" aria-label={intl.formatMessage({ id: 'groups.rename' }, { name: group.name })} className="p-1.5 text-text-muted hover:text-text" onClick={() => { setEditingId(group.id); setEditingName(group.name) }}><EditIcon /></button>
          <button type="button" aria-label={intl.formatMessage({ id: 'groups.delete' }, { name: group.name })} className="p-1.5 text-text-muted hover:text-danger" onClick={() => removeGroup(group)}><TrashIcon /></button>
        </div>
      </div>
    )
  }

  return (
    <aside className="border border-border rounded-lg p-3" aria-label={intl.formatMessage({ id: 'groups.title' })}>
      <div className="mb-3 flex items-center justify-between gap-2 px-1">
        <h3 className="text-sm font-medium text-text">{intl.formatMessage({ id: 'groups.title' })}</h3>
        <Button type="button" variant="secondary" size="sm" onClick={() => setCreating(true)} disabled={creating}>
          <span className="flex items-center gap-1"><PlusIcon />{intl.formatMessage({ id: 'groups.new' })}</span>
        </Button>
      </div>
      <nav className="space-y-1">
        {filterButton('all', intl.formatMessage({ id: 'groups.all' }), totalCount)}
        {filterButton('ungrouped', intl.formatMessage({ id: 'groups.none' }), ungroupedCount)}
      </nav>

      {showSearch && (
        <SearchField
          className="mt-3"
          label={intl.formatMessage({ id: 'groups.search' })}
          placeholder={intl.formatMessage({ id: 'groups.search' })}
          value={search}
          onChange={(event) => changeSearch(event.target.value)}
        />
      )}

      {strayGroup && (
        <div className="mt-2 border-b border-border pb-2">
          <div className="group">{groupRow(strayGroup)}</div>
          <p className="px-3 pt-1 text-xs text-text-muted">{intl.formatMessage({ id: 'groups.selectedOffPage' })}</p>
        </div>
      )}

      <nav className="mt-2 space-y-1">
        {query.isLoading ? (
          <div className="space-y-2 px-1 py-1" aria-hidden="true">
            <ShimmerSkeleton className="h-8 w-full" />
            <ShimmerSkeleton className="h-8 w-full" />
            <ShimmerSkeleton className="h-8 w-full" />
          </div>
        ) : (
          groups
            .filter((group) => group.id !== strayGroup?.id)
            .map((group) => (
              <div key={group.id} className="group">{groupRow(group)}</div>
            ))
        )}
      </nav>

      {query.error && <p role="alert" className="mt-3 px-2 text-xs text-danger">{intl.formatMessage({ id: 'groups.loadError' })}</p>}
      {!query.isLoading && !query.error && groups.length === 0 && !creating && (
        <p className="mt-3 px-2 text-xs text-text-muted">
          {deferredSearch
            ? intl.formatMessage({ id: 'groups.searchEmpty' }, { search: deferredSearch })
            : intl.formatMessage({ id: 'groups.empty' })}
        </p>
      )}
      {/* The range line is rendered whenever there is anything to count, not only when
          the rail overflows: it is what says this list is a window onto something
          larger, and by the time it would be needed it is too late to introduce it. */}
      {(total > 0 || deferredSearch.length > 0) && (
        <Pager
          className="mt-3"
          offset={offset}
          shown={groups.length}
          total={total}
          pageSize={GROUPS_RAIL_PAGE_SIZE}
          disabled={query.isFetching}
          onChange={setOffset}
        />
      )}

      {creating && (
        <form onSubmit={submitCreate} className="mt-3 border-t border-border pt-3 space-y-2">
          <Input autoFocus value={newName} maxLength={120} placeholder={intl.formatMessage({ id: 'groups.name' })} aria-label={intl.formatMessage({ id: 'groups.name' })} onChange={(event) => setNewName(event.target.value)} />
          <div className="flex gap-1">
            <Button size="sm" type="submit" disabled={!newName.trim() || createGroup.isPending}>{intl.formatMessage({ id: 'groups.create' })}</Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => { setCreating(false); setNewName('') }}>{intl.formatMessage({ id: 'groups.cancel' })}</Button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="mt-3 px-2 text-xs text-danger">{error}</p>}
    </aside>
  )
}

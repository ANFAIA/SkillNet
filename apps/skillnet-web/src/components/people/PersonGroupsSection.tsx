import { useState } from 'react'
import { useIntl } from 'react-intl'
import { apiErrorMessage } from '../../lib/apiErrors'
import { useGroupsOfPerson, useUpdateUserGroupMembers } from '../../api/user-groups'
import type { User } from '../../types'
import { Button } from '../ui'
import { GroupPicker } from './GroupPicker'

interface PersonGroupsSectionProps {
  person: User
}

/**
 * Which groups this person is in, and the way to change that from their own record.
 *
 * Membership used to be editable only from the group's side: putting somebody into a
 * group meant leaving their record, opening the rail, finding the group and searching
 * for them in its "add people" list. That is the wrong way round for the question an
 * admin has while looking at a person — "what does this one belong to?" — and it is the
 * only place where the answer belongs.
 *
 * Both directions write through the same `PUT /user-groups/{id}/members`, so there is one
 * definition of what joining a group means and not two that can drift.
 *
 * The "add to a group" half is a searchable picker and not a `<select>` of every group.
 * The dropdown was fine while an organization had three and became a scroll of two
 * hundred identical-looking options the moment it had two hundred — with no way to type
 * a name, and no line saying how many were in there. The groups this person already
 * belongs to are excluded by the server (`exclude_user_id`), not filtered out of the
 * page here: a page is not the collection, and the ones on other pages would still be
 * offered — an action that does nothing, reported as a success.
 */
export function PersonGroupsSection({ person }: PersonGroupsSectionProps) {
  const intl = useIntl()
  const mine = useGroupsOfPerson(person.id)
  const update = useUpdateUserGroupMembers()
  const [error, setError] = useState<string | null>(null)

  const groups = mine.data ?? []

  async function change(groupId: string, action: 'add' | 'remove') {
    if (update.isPending) return
    setError(null)
    try {
      await update.mutateAsync({
        id: groupId,
        add: action === 'add' ? [person.id] : [],
        remove: action === 'remove' ? [person.id] : [],
      })
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'groups.membersSaveError'))
    }
  }

  return (
    <div className="space-y-3">
      {mine.isLoading ? (
        <p className="text-sm text-text-muted">{intl.formatMessage({ id: 'groups.personLoading' })}</p>
      ) : groups.length === 0 ? (
        <p className="text-sm text-text-muted">{intl.formatMessage({ id: 'groups.personNone' })}</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {groups.map((group) => (
            <li key={group.id} className="flex items-center gap-3 px-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-text">{group.name}</span>
                <span className="block text-xs text-text-muted">
                  {intl.formatMessage({ id: 'groups.personMemberCount' }, { count: group.member_count })}
                </span>
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={update.isPending}
                onClick={() => change(group.id, 'remove')}
              >
                {intl.formatMessage({ id: 'groups.memberRemove' })}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-2">
        <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'groups.personAddLabel' })}</p>
        <GroupPicker
          filters={{ exclude_user_id: person.id }}
          searchLabel={intl.formatMessage({ id: 'groups.personAddSearch' })}
          emptyMessage={intl.formatMessage({ id: 'groups.personAddNone' })}
          renderAction={(group) => (
            <Button size="sm" disabled={update.isPending} onClick={() => change(group.id, 'add')}>
              {update.isPending
                ? intl.formatMessage({ id: 'groups.saving' })
                : intl.formatMessage({ id: 'groups.personAddAction' })}
            </Button>
          )}
        />
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  )
}

import { useState } from 'react'
import { useIntl } from 'react-intl'
import { apiErrorMessage } from '../../lib/apiErrors'
import { useUpdateUserGroupMembers, type UserGroup } from '../../api/user-groups'
import type { User } from '../../types'
import { Button, Modal } from '../ui'
import { PeoplePicker } from './PeoplePicker'

interface GroupMembersDialogProps {
  group: UserGroup
  onClose: () => void
}

/**
 * Edit who is in a group.
 *
 * **Two lists, not one list of checkboxes.** A single ticked list would have to know, for
 * every person on the page, whether they are already a member — and with both the people
 * and the membership paginated, the browser cannot know that without intersecting two
 * windows that do not line up. It would be wrong for anyone who fell on a different
 * page, and wrong in the worst direction: offering to add somebody who is already in.
 *
 * So the server answers the question instead. `GET /users?group_id=` is the members,
 * `GET /users?exclude_group_id=` is everyone else, each searchable and paginated on its
 * own, and every row's state is true by construction rather than by inference.
 *
 * Changes are staged and sent as one `PUT .../members` with `{add, remove}`: a page of
 * edits is one intention, and splitting it into a request per tick would let half of it
 * land. Nothing is written until "Guardar", which is also what makes it safe to page
 * around while deciding.
 */
export function GroupMembersDialog({ group, onClose }: GroupMembersDialogProps) {
  const intl = useIntl()
  const update = useUpdateUserGroupMembers()
  const [add, setAdd] = useState<string[]>([])
  const [remove, setRemove] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<{ added: number; removed: number; members: number } | null>(null)

  function toggleAdd(person: User) {
    setAdd((current) =>
      current.includes(person.id)
        ? current.filter((id) => id !== person.id)
        : [...current, person.id],
    )
  }

  function toggleRemove(person: User) {
    setRemove((current) =>
      current.includes(person.id)
        ? current.filter((id) => id !== person.id)
        : [...current, person.id],
    )
  }

  async function save() {
    if (update.isPending || (add.length === 0 && remove.length === 0)) return
    setError(null)
    try {
      const result = await update.mutateAsync({ id: group.id, add, remove })
      setAdd([])
      setRemove([])
      setSaved({ added: result.added_count, removed: result.removed_count, members: result.member_count })
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'groups.membersSaveError'))
    }
  }

  const pending = add.length + remove.length

  return (
    <Modal open onClose={onClose} size="md">
      <h2 className="text-lg font-semibold text-text">
        {intl.formatMessage({ id: 'groups.membersTitle' }, { name: group.name })}
      </h2>
      <p className="mt-1 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'groups.membersDescription' })}
      </p>

      <section className="mt-5">
        <h3 className="mb-2 text-sm font-medium text-text">
          {/* After a save the prop is a page behind — the parent's group list has been
              invalidated but this object was captured when the dialog opened. */}
          {intl.formatMessage({ id: 'groups.membersIn' }, { count: saved?.members ?? group.member_count })}
        </h3>
        <PeoplePicker
          filters={{ group_id: group.id }}
          searchLabel={intl.formatMessage({ id: 'groups.membersSearchIn' })}
          emptyMessage={intl.formatMessage({ id: 'groups.membersNoneIn' })}
          renderAction={(person) => {
            const staged = remove.includes(person.id)
            return (
              <Button
                size="sm"
                variant={staged ? 'secondary' : 'ghost'}
                onClick={() => toggleRemove(person)}
              >
                {intl.formatMessage({ id: staged ? 'groups.memberUndoRemove' : 'groups.memberRemove' })}
              </Button>
            )
          }}
        />
      </section>

      <section className="mt-5">
        <h3 className="mb-2 text-sm font-medium text-text">
          {intl.formatMessage({ id: 'groups.membersAdd' })}
        </h3>
        <PeoplePicker
          filters={{ exclude_group_id: group.id }}
          searchLabel={intl.formatMessage({ id: 'groups.membersSearchOut' })}
          emptyMessage={intl.formatMessage({ id: 'groups.membersNoneOut' })}
          renderAction={(person) => {
            const staged = add.includes(person.id)
            return (
              <Button
                size="sm"
                variant={staged ? 'secondary' : 'ghost'}
                onClick={() => toggleAdd(person)}
              >
                {intl.formatMessage({ id: staged ? 'groups.memberUndoAdd' : 'groups.memberAdd' })}
              </Button>
            )
          }}
        />
      </section>

      {saved && (
        <p className="mt-4 text-sm text-accent">
          {intl.formatMessage({ id: 'groups.membersSaved' }, { added: saved.added, removed: saved.removed })}
        </p>
      )}
      {error && <p role="alert" className="mt-4 text-sm text-danger">{error}</p>}

      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>{intl.formatMessage({ id: 'groups.close' })}</Button>
        <Button disabled={pending === 0 || update.isPending} onClick={save}>
          {update.isPending
            ? intl.formatMessage({ id: 'groups.saving' })
            : intl.formatMessage({ id: 'groups.membersSave' }, { count: pending })}
        </Button>
      </div>
    </Modal>
  )
}

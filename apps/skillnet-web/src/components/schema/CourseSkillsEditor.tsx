import { useMemo, useState } from 'react'
import { useIntl } from 'react-intl'

export interface SkillOption {
  id?: string
  name: string
}

interface CourseSkillsEditorProps {
  skills: SkillOption[]
  availableSkills: SkillOption[]
  onChange: (skills: SkillOption[]) => void
  disabled?: boolean
}

function normalizeSkillName(value: string): string {
  return value.trim().replace(/\s+/g, ' ')
}

export function CourseSkillsEditor({
  skills,
  availableSkills,
  onChange,
  disabled = false,
}: CourseSkillsEditorProps) {
  const intl = useIntl()
  const [draft, setDraft] = useState('')
  const selectedNames = useMemo(
    () => new Set(skills.map((skill) => skill.name.toLocaleLowerCase())),
    [skills],
  )
  const suggestions = availableSkills.filter(
    (skill) => !selectedNames.has(skill.name.toLocaleLowerCase()),
  )

  function addSkill(option?: SkillOption) {
    const name = normalizeSkillName(option?.name ?? draft)
    if (!name || selectedNames.has(name.toLocaleLowerCase())) return
    onChange([...skills, option?.id ? { id: option.id, name } : { name }])
    setDraft('')
  }

  function updateSkill(index: number, name: string) {
    const next = [...skills]
    next[index] = { ...next[index], name }
    onChange(next)
  }

  function finishEditing(index: number) {
    const name = normalizeSkillName(skills[index]?.name ?? '')
    if (!name) {
      onChange(skills.filter((_, current) => current !== index))
      return
    }
    const duplicate = skills.some(
      (skill, current) => current !== index && skill.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
    )
    if (duplicate) {
      onChange(skills.filter((_, current) => current !== index))
      return
    }
    const next = [...skills]
    next[index] = { ...next[index], name }
    onChange(next)
  }

  return (
    <section className="border border-border rounded-lg p-4" aria-labelledby="course-skills-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 id="course-skills-heading" className="text-sm font-medium text-text">
            {intl.formatMessage({ id: 'schema.skills.title' })}
          </h3>
          <p className="text-xs text-text-muted mt-1">
            {intl.formatMessage({ id: 'schema.skills.description' })}
          </p>
        </div>
        <span className="text-xs text-text-muted shrink-0">{skills.length}</span>
      </div>

      {skills.length > 0 ? (
        <div className="space-y-2 mt-4">
          {skills.map((skill, index) => (
            <div key={`${skill.id ?? 'new'}-${index}`} className="flex items-center gap-2">
              <input
                value={skill.name}
                onChange={(event) => updateSkill(index, event.target.value)}
                onBlur={() => finishEditing(index)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.currentTarget.blur()
                }}
                disabled={disabled}
                aria-label={intl.formatMessage({ id: 'schema.skills.itemLabel' }, { index: index + 1 })}
                className="min-w-0 flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-text focus:outline-none focus:border-primary disabled:opacity-60"
              />
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(skills.filter((_, current) => current !== index))}
                className="px-2 py-2 text-xs text-text-muted hover:text-danger disabled:opacity-60"
                aria-label={intl.formatMessage({ id: 'schema.skills.removeLabel' }, { name: skill.name })}
              >
                {intl.formatMessage({ id: 'schema.skills.remove' })}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-text-muted mt-4">
          {intl.formatMessage({ id: 'schema.skills.empty' })}
        </p>
      )}

      <div className="flex gap-2 mt-3">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addSkill()
            }
          }}
          disabled={disabled}
          placeholder={intl.formatMessage({ id: 'schema.skills.newPlaceholder' })}
          aria-label={intl.formatMessage({ id: 'schema.skills.newLabel' })}
          className="min-w-0 flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => addSkill()}
          disabled={disabled || !normalizeSkillName(draft)}
          className="rounded-md border border-border px-3 py-2 text-sm font-medium text-text hover:border-primary hover:text-primary disabled:opacity-50"
        >
          {intl.formatMessage({ id: 'schema.skills.add' })}
        </button>
      </div>

      {suggestions.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-text-muted mb-2">
            {intl.formatMessage({ id: 'schema.skills.suggestions' })}
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.slice(0, 8).map((skill) => (
              <button
                key={skill.id ?? skill.name}
                type="button"
                disabled={disabled}
                onClick={() => addSkill(skill)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-text-secondary hover:border-primary hover:text-primary disabled:opacity-60"
              >
                + {skill.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

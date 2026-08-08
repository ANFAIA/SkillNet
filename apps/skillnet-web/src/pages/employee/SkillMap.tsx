import { useIntl } from 'react-intl'
import { Card, CardTitle, SkillBars, EmptyState, SkeletonRow } from '../../components/ui'
import { useMySkills } from '../../api/users'
import type { UserSkillRead } from '../../types'

export function SkillMap() {
  const intl = useIntl()
  const { data: userSkills, isLoading, error } = useMySkills()

  const skills = userSkills ?? []

  // Group skills by level for a simple overview when there are no categories
  const groupByLevel = (items: UserSkillRead[]) => {
    const groups: Record<string, UserSkillRead[]> = {}
    for (const skill of items) {
      const key = skill.level
      if (!groups[key]) groups[key] = []
      groups[key].push(skill)
    }
    return groups
  }

  const levelLabels: Record<string, string> = {
    low: intl.formatMessage({ id: 'skillmap.levelLow' }),
    medium: intl.formatMessage({ id: 'skillmap.levelMedium' }),
    high: intl.formatMessage({ id: 'skillmap.levelHigh' }),
  }

  const levelOrder = ['high', 'medium', 'low']
  const grouped = groupByLevel(skills)

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'skillmap.title' })}</h2>
        <p className="text-sm text-text-secondary mt-0.5">
          {intl.formatMessage({ id: 'skillmap.subtitle' })}
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 sm:gap-6 mb-6">
        {(['low', 'medium', 'high'] as const).map((level) => (
          <div key={level} className="flex items-center gap-2">
            <SkillBars level={level} />
            <span className="text-xs text-text-secondary">{levelLabels[level]}</span>
          </div>
        ))}
      </div>

      {isLoading ? (
        <Card>
          <CardTitle className="mb-4">{intl.formatMessage({ id: 'skillmap.loading' })}</CardTitle>
          <div className="space-y-1">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        </Card>
      ) : error ? (
        <Card>
          <EmptyState title={intl.formatMessage({ id: 'skillmap.loadError' })} description={intl.formatMessage({ id: 'skillmap.loadErrorDesc' })} />
        </Card>
      ) : skills.length === 0 ? (
        <Card>
          <EmptyState
            title={intl.formatMessage({ id: 'skillmap.emptyTitle' })}
            description={intl.formatMessage({ id: 'skillmap.emptyDesc' })}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {levelOrder
            .filter((level) => grouped[level]?.length)
            .map((level) => (
              <Card key={level}>
                <CardTitle className="mb-4">{levelLabels[level]}</CardTitle>
                <div className="space-y-4">
                  {grouped[level].map((skill) => (
                    <div key={skill.id} className="flex items-center justify-between gap-2 min-w-0">
                      <span className="text-sm text-text truncate min-w-0">{skill.skill_name}</span>
                      <div className="flex items-center gap-3 shrink-0">
                        <SkillBars level={skill.level} />
                        <span className="text-xs text-text-secondary w-20">{levelLabels[skill.level]}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
        </div>
      )}
    </div>
  )
}

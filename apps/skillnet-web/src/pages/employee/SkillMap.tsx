import { Card, CardTitle, SkillBars } from '../../components/ui'
// v1-static: skills/SkillMap have NO backend endpoint yet. This page intentionally
// renders static mock data until a skills API exists (out of v1 scope).
import { skills } from '../../data/mockData'

export function SkillMap() {
  // Group skills by category
  const categories = skills.reduce<Record<string, typeof skills>>((acc, skill) => {
    if (!acc[skill.category]) acc[skill.category] = []
    acc[skill.category].push(skill)
    return acc
  }, {})

  const levelLabels: Record<string, string> = {
    low: 'Basico',
    medium: 'Intermedio',
    high: 'Avanzado',
    expert: 'Experto',
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-text">Skill Map</h2>
        <p className="text-sm text-text-secondary mt-0.5">
          Tu mapa de competencias profesionales
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 sm:gap-6 mb-6">
        {(['low', 'medium', 'high', 'expert'] as const).map((level) => (
          <div key={level} className="flex items-center gap-2">
            <SkillBars level={level} />
            <span className="text-xs text-text-secondary">{levelLabels[level]}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4">
        {Object.entries(categories).map(([category, categorySkills]) => (
          <Card key={category}>
            <CardTitle className="mb-4">{category}</CardTitle>
            <div className="space-y-4">
              {categorySkills.map((skill) => (
                <div key={skill.name} className="flex items-center justify-between gap-2 min-w-0">
                  <span className="text-sm text-text truncate min-w-0">{skill.name}</span>
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
    </div>
  )
}

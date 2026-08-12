import type { TalentCourseSummary } from '../../api/talent'
import type { SkillRead } from '../../api/skills'
import { Card, SearchField, Select } from '../ui'
import { formatSkillName } from '../../lib/formatSkillName'

export type TalentStatusFilter = '' | 'assigned' | 'in_progress' | 'completed'

type TalentFiltersProps = {
  search: string
  courseId: string
  skillId: string
  status: TalentStatusFilter
  courses: TalentCourseSummary[]
  skills: SkillRead[]
  onSearchChange: (value: string) => void
  onCourseChange: (value: string) => void
  onSkillChange: (value: string) => void
  onStatusChange: (value: TalentStatusFilter) => void
  onClear: () => void
}

export function TalentFilters({
  search,
  courseId,
  skillId,
  status,
  courses,
  skills,
  onSearchChange,
  onCourseChange,
  onSkillChange,
  onStatusChange,
  onClear,
}: TalentFiltersProps) {
  const courseName = courses.find((course) => course.course_id === courseId)?.title
  const skillName = skills.find((skill) => skill.id === skillId)?.name
  const statusName = status === 'assigned' ? 'Sin iniciar' : status === 'in_progress' ? 'En curso' : status === 'completed' ? 'Completado' : undefined
  const chips = [
    search.trim() ? { key: 'search', label: `“${search.trim()}”`, clear: () => onSearchChange('') } : null,
    courseName ? { key: 'course', label: courseName, clear: () => onCourseChange('') } : null,
    skillName ? { key: 'skill', label: formatSkillName(skillName), clear: () => onSkillChange('') } : null,
    statusName ? { key: 'status', label: statusName, clear: () => onStatusChange('') } : null,
  ].filter((chip): chip is { key: string; label: string; clear: () => void } => chip !== null)

  return (
    <Card className="mt-5">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_minmax(180px,0.8fr)_minmax(180px,0.8fr)_160px] md:items-end">
        <SearchField label="Buscar persona" placeholder="Nombre o correo" value={search} onChange={(event) => onSearchChange(event.target.value)} />
        <Select label="Curso" value={courseId} onChange={(event) => onCourseChange(event.target.value)}>
          <option value="">Todos los cursos</option>
          {courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}
        </Select>
        <Select label="Habilidad" value={skillId} onChange={(event) => onSkillChange(event.target.value)}>
          <option value="">Todas las habilidades</option>
          {skills.map((skill) => <option key={skill.id} value={skill.id}>{formatSkillName(skill.name)}</option>)}
        </Select>
        <Select label="Estado" value={status} onChange={(event) => onStatusChange(event.target.value as TalentStatusFilter)}>
          <option value="">Todos</option>
          <option value="assigned">Sin iniciar</option>
          <option value="in_progress">En curso</option>
          <option value="completed">Completado</option>
        </Select>
      </div>
      {chips.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4" aria-label="Filtros activos">
          {chips.map((chip) => (
            <button key={chip.key} type="button" onClick={chip.clear} className="inline-flex max-w-full items-center gap-2 rounded-md border border-border bg-bg-subtle px-2.5 py-1 text-xs text-text-secondary hover:border-primary hover:text-text">
              <span className="truncate">{chip.label}</span><span aria-hidden="true">×</span>
            </button>
          ))}
          <button type="button" onClick={onClear} className="ml-auto text-xs font-medium text-primary hover:text-primary-hover">Limpiar filtros</button>
        </div>
      )}
    </Card>
  )
}

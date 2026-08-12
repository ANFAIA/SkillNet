import type { TalentCourseSummary } from '../../api/talent'
import type { SkillRead } from '../../api/skills'
import { formatSkillName } from '../../lib/formatSkillName'
import { SearchField, Select } from '../ui'

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
    <section className="mt-6 border-b border-border pb-5" aria-label="Buscar y filtrar talento">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-[minmax(320px,1.4fr)_minmax(190px,0.8fr)_minmax(190px,0.8fr)_150px] md:items-end">
        <SearchField className="md:col-span-3 xl:col-span-1" label="Buscar persona" placeholder="Buscar por nombre o correo" value={search} onChange={(event) => onSearchChange(event.target.value)} />
        <Select hideLabel label="Curso" aria-label="Curso" value={courseId} onChange={(event) => onCourseChange(event.target.value)}>
          <option value="">Todos los cursos</option>
          {courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}
        </Select>
        <Select hideLabel label="Habilidad" aria-label="Habilidad" value={skillId} onChange={(event) => onSkillChange(event.target.value)}>
          <option value="">Todas las habilidades</option>
          {skills.map((skill) => <option key={skill.id} value={skill.id}>{formatSkillName(skill.name)}</option>)}
        </Select>
        <Select hideLabel label="Estado" aria-label="Estado" value={status} onChange={(event) => onStatusChange(event.target.value as TalentStatusFilter)}>
          <option value="">Todos los estados</option>
          <option value="assigned">Sin iniciar</option>
          <option value="in_progress">En curso</option>
          <option value="completed">Completado</option>
        </Select>
      </div>
      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2" aria-label="Filtros activos">
          {chips.map((chip) => (
            <button key={chip.key} type="button" onClick={chip.clear} className="inline-flex max-w-full items-center gap-2 rounded-md border border-border bg-bg-subtle px-2.5 py-1 text-xs text-text-secondary hover:border-border-strong hover:text-text">
              <span className="truncate">{chip.label}</span><span aria-hidden="true">×</span>
            </button>
          ))}
          <button type="button" onClick={onClear} className="ml-auto text-xs font-medium text-primary hover:text-primary-hover">Limpiar filtros</button>
        </div>
      )}
    </section>
  )
}

import { useState } from 'react'
import { Card, CardTitle, SkillBars, Badge, Button } from '../../components/ui'
import { employees } from '../../data/adminMockData'
import type { Employee } from '../../data/adminMockData'

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

function EmployeeDetail({ employee, onBack }: { employee: Employee; onBack: () => void }) {
  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="text-sm text-primary hover:underline cursor-pointer mb-4"
      >
        Volver a la lista
      </button>
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-text">{employee.name}</h3>
            <p className="text-sm text-text-secondary">{employee.role} -- {employee.department}</p>
          </div>
          <SkillBars level={employee.averageLevel} />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-5">
          <div className="border border-border rounded-lg p-4">
            <p className="text-sm text-text-secondary">Cursos asignados</p>
            <p className="text-2xl font-semibold text-text mt-1">{employee.coursesAssigned}</p>
          </div>
          <div className="border border-border rounded-lg p-4">
            <p className="text-sm text-text-secondary">Cursos completados</p>
            <p className="text-2xl font-semibold text-text mt-1">{employee.coursesCompleted}</p>
          </div>
        </div>

        <div className="mt-5">
          <CardTitle>Skills</CardTitle>
          <div className="mt-3 space-y-3">
            {employee.skills.map((skill) => (
              <div key={skill.name} className="flex items-center gap-3">
                <span className="text-sm text-text w-28">{skill.name}</span>
                <div className="flex-1 h-1.5 bg-bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${skill.score}%`,
                      backgroundColor:
                        skill.level === 'expert' ? 'var(--color-primary)' :
                        skill.level === 'high' ? 'var(--color-skill-high)' :
                        skill.level === 'medium' ? 'var(--color-skill-medium)' :
                        'var(--color-skill-low)',
                    }}
                  />
                </div>
                <span className="text-xs text-text-muted w-8 text-right">{skill.score}</span>
                <SkillBars level={skill.level} />
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}

export function Employees() {
  const [search, setSearch] = useState('')
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null)

  const filtered = employees.filter((emp) =>
    emp.name.toLowerCase().includes(search.toLowerCase()) ||
    emp.role.toLowerCase().includes(search.toLowerCase()) ||
    emp.department.toLowerCase().includes(search.toLowerCase())
  )

  if (selectedEmployee) {
    return (
      <EmployeeDetail
        employee={selectedEmployee}
        onBack={() => setSelectedEmployee(null)}
      />
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text">Empleados</h2>
          <p className="text-sm text-text-secondary mt-1">{employees.length} miembros del equipo</p>
        </div>
        <Button variant="primary" size="md">Agregar empleado</Button>
      </div>

      {/* Search */}
      <div className="relative mt-4">
        <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-text-muted">
          <SearchIcon />
        </div>
        <input
          type="text"
          placeholder="Buscar por nombre, rol o departamento..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
        />
      </div>

      {/* Table */}
      <Card className="mt-4 p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-bg-subtle">
              <th className="text-left py-3 px-5 font-medium text-text-secondary">Nombre</th>
              <th className="text-left py-3 px-4 font-medium text-text-secondary">Rol</th>
              <th className="text-center py-3 px-4 font-medium text-text-secondary">Cursos</th>
              <th className="text-center py-3 px-4 font-medium text-text-secondary">Nivel</th>
              <th className="text-left py-3 px-4 font-medium text-text-secondary">Departamento</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((emp) => (
              <tr
                key={emp.id}
                className="border-b border-border last:border-b-0 hover:bg-bg-subtle transition-colors cursor-pointer"
                onClick={() => setSelectedEmployee(emp)}
              >
                <td className="py-3 px-5">
                  <span className="font-medium text-text">{emp.name}</span>
                </td>
                <td className="py-3 px-4 text-text-secondary">{emp.role}</td>
                <td className="py-3 px-4 text-center">
                  <span className="text-text">{emp.coursesCompleted}</span>
                  <span className="text-text-muted">/{emp.coursesAssigned}</span>
                </td>
                <td className="py-3 px-4">
                  <div className="flex justify-center">
                    <SkillBars level={emp.averageLevel} />
                  </div>
                </td>
                <td className="py-3 px-4">
                  <Badge variant="primary" badgeStyle="plain">{emp.department}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="py-8 text-center text-sm text-text-muted">
            No se encontraron empleados
          </div>
        )}
      </Card>
    </div>
  )
}

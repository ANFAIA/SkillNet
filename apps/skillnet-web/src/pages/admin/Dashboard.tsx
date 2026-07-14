import { Card, CardTitle, MetricCard, Badge } from '../../components/ui'
import { alerts, skillMatrixData, recentActivity } from '../../data/adminMockData'

const skillColors: Record<string, string> = {
  high: 'bg-skill-high',
  medium: 'bg-skill-medium',
  low: 'bg-skill-low',
  none: 'bg-skill-none',
}

const alertVariant: Record<string, 'warning' | 'danger' | 'primary'> = {
  warning: 'warning',
  danger: 'danger',
  info: 'primary',
}

function UsersIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

function TargetIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

const skillColumns = ['React', 'TypeScript', 'SQL', 'Docker'] as const

export function Dashboard() {
  return (
    <div>
      <h2 className="text-xl font-semibold text-text">Panel de Empresa</h2>
      <p className="text-sm text-text-secondary mt-1">Vista general del equipo y formacion</p>

      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4 mt-6">
        <MetricCard
          value="12"
          label="Empleados"
          icon={<UsersIcon />}
          color="blue"
        />
        <MetricCard
          value="5"
          label="Cursos activos"
          icon={<BookIcon />}
          color="green"
        />
        <MetricCard
          value="18"
          label="Skills registradas"
          icon={<TargetIcon />}
          color="purple"
        />
        <MetricCard
          value="3"
          label="Alertas"
          icon={<AlertIcon />}
          color="orange"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        {/* Alerts */}
        <Card>
          <CardTitle>Alertas</CardTitle>
          <div className="mt-3 space-y-0">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-start gap-3 py-3 border-b border-border last:border-b-0"
              >
                <div className="shrink-0 mt-0.5">
                  <Badge variant={alertVariant[alert.type]} badgeStyle="plain">
                    {alert.type === 'warning' ? 'Aviso' : alert.type === 'danger' ? 'Critico' : 'Info'}
                  </Badge>
                </div>
                <p className="text-sm text-text-secondary leading-snug">
                  {alert.message}
                </p>
              </div>
            ))}
          </div>
        </Card>

        {/* Activity */}
        <Card>
          <CardTitle>Actividad del equipo</CardTitle>
          <div className="mt-3 space-y-0">
            {recentActivity.map((activity, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="text-sm text-text">
                    <span className="font-medium">{activity.employee}</span>
                    {' '}{activity.action}
                  </p>
                  <p className="text-xs text-text-muted mt-0.5">{activity.course}</p>
                </div>
                <span className="text-xs text-text-muted shrink-0 ml-4">{activity.time}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Skill Matrix */}
      <Card className="mt-4">
        <CardTitle>Skill Matrix</CardTitle>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-4 font-medium text-text-secondary">Empleado</th>
                {skillColumns.map((skill) => (
                  <th key={skill} className="text-center py-2 px-3 font-medium text-text-secondary">
                    {skill}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {skillMatrixData.map((entry) => (
                <tr key={entry.employeeName} className="border-b border-border last:border-b-0">
                  <td className="py-2.5 pr-4 text-text font-medium">{entry.employeeName}</td>
                  {skillColumns.map((skill) => {
                    const level = entry.skills[skill] ?? 'none'
                    return (
                      <td key={skill} className="text-center py-2.5 px-3">
                        <span
                          className={`inline-block w-6 h-6 rounded ${skillColors[level]}`}
                          title={level}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
            <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-skill-high" /> Alto</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-skill-medium" /> Medio</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-skill-low" /> Bajo</span>
            <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-skill-none" /> Sin datos</span>
          </div>
        </div>
      </Card>
    </div>
  )
}

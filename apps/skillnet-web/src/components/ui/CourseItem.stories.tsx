import type { Meta } from '@storybook/react-vite'
import { CourseItem } from './CourseItem'

const meta: Meta<typeof CourseItem> = {
  title: 'UI/CourseItem',
  component: CourseItem,
}
export default meta

export const Default = () => (
  <div className="max-w-md">
    <CourseItem
      title="Protocolo de devoluciones"
      subtitle="Modulo 2 de 5"
      progress={40}
      color="#3B82F6"
    />
  </div>
)

export const ConClick = () => (
  <div className="max-w-md">
    <CourseItem
      title="Higiene alimentaria"
      subtitle="Modulo 4 de 6 - Evaluacion practica"
      progress={66}
      color="#10B981"
      onClick={() => alert('Navegar al curso')}
    />
  </div>
)

export const ListaDeCursos = () => (
  <div className="max-w-md border border-border rounded-xl p-2">
    <CourseItem
      title="Protocolo de devoluciones"
      subtitle="Modulo 2 de 5 - Ultima sesion: ayer"
      progress={40}
      color="#3B82F6"
      onClick={() => {}}
    />
    <CourseItem
      title="Higiene alimentaria"
      subtitle="Modulo 4 de 6 - Ultima sesion: hace 2 dias"
      progress={66}
      color="#10B981"
      onClick={() => {}}
    />
    <CourseItem
      title="Seguridad laboral"
      subtitle="Modulo 1 de 4 - Sin empezar"
      progress={0}
      color="#F97316"
      onClick={() => {}}
    />
    <CourseItem
      title="Atencion al cliente avanzada"
      subtitle="Completado hace 1 semana"
      progress={100}
      color="#8B5CF6"
      onClick={() => {}}
    />
    <CourseItem
      title="Gestion de inventario"
      subtitle="Modulo 3 de 8 - Ultima sesion: hoy"
      progress={37}
      color="#EC4899"
      onClick={() => {}}
    />
  </div>
)

export const ConIconos = () => {
  const bookIcon = (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )

  return (
    <div className="max-w-md">
      <CourseItem
        title="Protocolo de devoluciones"
        subtitle="Modulo 2 de 5 - Casuisticas especiales"
        progress={40}
        color="#3B82F6"
        icon={bookIcon}
        onClick={() => {}}
      />
      <CourseItem
        title="Higiene alimentaria"
        subtitle="Modulo 4 de 6 - Normativa APPCC"
        progress={66}
        color="#10B981"
        icon={bookIcon}
        onClick={() => {}}
      />
    </div>
  )
}

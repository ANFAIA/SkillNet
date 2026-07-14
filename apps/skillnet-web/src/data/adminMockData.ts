export interface EmployeeSkill {
  name: string
  level: 'low' | 'medium' | 'high' | 'expert'
  score: number // 0-100
}

export interface Employee {
  id: string
  name: string
  role: string
  department: string
  coursesAssigned: number
  coursesCompleted: number
  skills: EmployeeSkill[]
  averageLevel: 'low' | 'medium' | 'high' | 'expert'
}

export interface AdminCourse {
  id: string
  title: string
  status: 'draft' | 'published' | 'archived'
  modules: number
  exercises: number
  assignedCount: number
  createdAt: string
  updatedAt: string
}

export interface Alert {
  id: string
  type: 'warning' | 'danger' | 'info'
  message: string
  timestamp: string
}

export const employees: Employee[] = [
  {
    id: 'emp-1',
    name: 'Laura Martinez',
    role: 'Desarrolladora Frontend',
    department: 'Ingenieria',
    coursesAssigned: 3,
    coursesCompleted: 2,
    skills: [
      { name: 'React', level: 'high', score: 82 },
      { name: 'TypeScript', level: 'medium', score: 65 },
      { name: 'CSS', level: 'expert', score: 90 },
      { name: 'Testing', level: 'medium', score: 55 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-2',
    name: 'Carlos Ruiz',
    role: 'Desarrollador Backend',
    department: 'Ingenieria',
    coursesAssigned: 2,
    coursesCompleted: 1,
    skills: [
      { name: 'Node.js', level: 'expert', score: 92 },
      { name: 'SQL', level: 'high', score: 78 },
      { name: 'Docker', level: 'medium', score: 60 },
      { name: 'Testing', level: 'high', score: 75 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-3',
    name: 'Ana Lopez',
    role: 'Disenadora UX',
    department: 'Diseno',
    coursesAssigned: 4,
    coursesCompleted: 3,
    skills: [
      { name: 'Figma', level: 'expert', score: 95 },
      { name: 'Research', level: 'high', score: 80 },
      { name: 'Prototyping', level: 'high', score: 76 },
      { name: 'CSS', level: 'medium', score: 50 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-4',
    name: 'Pedro Sanchez',
    role: 'DevOps',
    department: 'Infraestructura',
    coursesAssigned: 2,
    coursesCompleted: 0,
    skills: [
      { name: 'AWS', level: 'high', score: 85 },
      { name: 'Docker', level: 'expert', score: 93 },
      { name: 'CI/CD', level: 'high', score: 78 },
      { name: 'Monitoring', level: 'medium', score: 62 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-5',
    name: 'Maria Garcia',
    role: 'Product Manager',
    department: 'Producto',
    coursesAssigned: 3,
    coursesCompleted: 2,
    skills: [
      { name: 'Roadmapping', level: 'expert', score: 88 },
      { name: 'Analytics', level: 'high', score: 74 },
      { name: 'SQL', level: 'low', score: 30 },
      { name: 'Agile', level: 'high', score: 82 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-6',
    name: 'Diego Torres',
    role: 'QA Engineer',
    department: 'Ingenieria',
    coursesAssigned: 2,
    coursesCompleted: 1,
    skills: [
      { name: 'Testing', level: 'expert', score: 91 },
      { name: 'Automation', level: 'high', score: 79 },
      { name: 'SQL', level: 'medium', score: 55 },
      { name: 'CI/CD', level: 'medium', score: 48 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-7',
    name: 'Sofia Hernandez',
    role: 'Data Analyst',
    department: 'Datos',
    coursesAssigned: 3,
    coursesCompleted: 1,
    skills: [
      { name: 'SQL', level: 'expert', score: 94 },
      { name: 'Python', level: 'high', score: 77 },
      { name: 'Visualizacion', level: 'high', score: 81 },
      { name: 'ML Basico', level: 'low', score: 35 },
    ],
    averageLevel: 'high',
  },
  {
    id: 'emp-8',
    name: 'Javier Moreno',
    role: 'Desarrollador Mobile',
    department: 'Ingenieria',
    coursesAssigned: 2,
    coursesCompleted: 2,
    skills: [
      { name: 'React Native', level: 'high', score: 83 },
      { name: 'TypeScript', level: 'high', score: 76 },
      { name: 'iOS', level: 'medium', score: 58 },
      { name: 'Testing', level: 'low', score: 32 },
    ],
    averageLevel: 'medium',
  },
  {
    id: 'emp-9',
    name: 'Valentina Cruz',
    role: 'Desarrolladora Fullstack',
    department: 'Ingenieria',
    coursesAssigned: 4,
    coursesCompleted: 3,
    skills: [
      { name: 'React', level: 'high', score: 80 },
      { name: 'Node.js', level: 'high', score: 75 },
      { name: 'SQL', level: 'medium', score: 63 },
      { name: 'Docker', level: 'low', score: 28 },
    ],
    averageLevel: 'medium',
  },
  {
    id: 'emp-10',
    name: 'Andres Vargas',
    role: 'Intern',
    department: 'Ingenieria',
    coursesAssigned: 5,
    coursesCompleted: 1,
    skills: [
      { name: 'HTML/CSS', level: 'medium', score: 52 },
      { name: 'JavaScript', level: 'low', score: 38 },
      { name: 'Git', level: 'low', score: 25 },
      { name: 'React', level: 'low', score: 20 },
    ],
    averageLevel: 'low',
  },
]

export const adminCourses: AdminCourse[] = [
  {
    id: 'course-1',
    title: 'Fundamentos de React',
    status: 'published',
    modules: 8,
    exercises: 24,
    assignedCount: 6,
    createdAt: '2026-05-10',
    updatedAt: '2026-06-15',
  },
  {
    id: 'course-2',
    title: 'TypeScript Avanzado',
    status: 'published',
    modules: 6,
    exercises: 18,
    assignedCount: 4,
    createdAt: '2026-04-22',
    updatedAt: '2026-06-01',
  },
  {
    id: 'course-3',
    title: 'Docker y Contenedores',
    status: 'draft',
    modules: 5,
    exercises: 12,
    assignedCount: 0,
    createdAt: '2026-07-01',
    updatedAt: '2026-07-10',
  },
  {
    id: 'course-4',
    title: 'SQL para Analistas',
    status: 'published',
    modules: 7,
    exercises: 21,
    assignedCount: 3,
    createdAt: '2026-03-15',
    updatedAt: '2026-05-20',
  },
  {
    id: 'course-5',
    title: 'Introduccion a Testing',
    status: 'archived',
    modules: 4,
    exercises: 10,
    assignedCount: 8,
    createdAt: '2025-11-05',
    updatedAt: '2026-02-28',
  },
  {
    id: 'course-6',
    title: 'CI/CD con GitHub Actions',
    status: 'draft',
    modules: 3,
    exercises: 6,
    assignedCount: 0,
    createdAt: '2026-07-08',
    updatedAt: '2026-07-12',
  },
]

export const alerts: Alert[] = [
  {
    id: 'alert-1',
    type: 'warning',
    message: 'Deadline cercano: "Fundamentos de React" vence en 3 dias para 2 empleados',
    timestamp: '2026-07-13T09:30:00',
  },
  {
    id: 'alert-2',
    type: 'danger',
    message: 'Andres Vargas lleva 14 dias sin actividad en sus cursos asignados',
    timestamp: '2026-07-13T08:00:00',
  },
  {
    id: 'alert-3',
    type: 'info',
    message: 'Onboarding pendiente: nuevo empleado Andres Vargas requiere asignacion de cursos',
    timestamp: '2026-07-12T14:00:00',
  },
  {
    id: 'alert-4',
    type: 'warning',
    message: 'Javier Moreno bloquado en el modulo 3 de "TypeScript Avanzado"',
    timestamp: '2026-07-11T16:45:00',
  },
]

// Skill matrix data for dashboard
export interface SkillMatrixEntry {
  employeeName: string
  skills: Record<string, 'high' | 'medium' | 'low' | 'none'>
}

export const skillMatrixData: SkillMatrixEntry[] = [
  {
    employeeName: 'Laura M.',
    skills: { React: 'high', TypeScript: 'medium', SQL: 'low', Docker: 'none' },
  },
  {
    employeeName: 'Carlos R.',
    skills: { React: 'medium', TypeScript: 'high', SQL: 'high', Docker: 'medium' },
  },
  {
    employeeName: 'Ana L.',
    skills: { React: 'low', TypeScript: 'low', SQL: 'none', Docker: 'none' },
  },
  {
    employeeName: 'Pedro S.',
    skills: { React: 'none', TypeScript: 'medium', SQL: 'medium', Docker: 'high' },
  },
]

export const recentActivity = [
  { employee: 'Laura Martinez', action: 'completo modulo 5', course: 'Fundamentos de React', time: 'hace 2h' },
  { employee: 'Carlos Ruiz', action: 'inicio curso', course: 'Docker y Contenedores', time: 'hace 4h' },
  { employee: 'Sofia Hernandez', action: 'aprobo ejercicio', course: 'SQL para Analistas', time: 'hace 5h' },
  { employee: 'Valentina Cruz', action: 'completo modulo 3', course: 'TypeScript Avanzado', time: 'hace 1d' },
  { employee: 'Diego Torres', action: 'inicio curso', course: 'Introduccion a Testing', time: 'hace 1d' },
]

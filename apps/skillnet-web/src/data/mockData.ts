export type SkillLevel = 'low' | 'medium' | 'high' | 'expert'

export interface Exercise {
  id: string
  type: 'multiple-choice' | 'true-false'
  question: string
  options: string[]
  correctIndex: number
}

export interface Lesson {
  id: string
  title: string
  content: string
  exercise?: Exercise
}

export interface Module {
  id: string
  title: string
  lessons: Lesson[]
}

export interface Course {
  id: string
  title: string
  subtitle: string
  color: string
  progress: number
  status: 'in-progress' | 'completed' | 'pending'
  modules: Module[]
}

export interface Skill {
  name: string
  level: SkillLevel
  category: string
}

export interface ActivityItem {
  id: string
  text: string
  time: string
}

export interface User {
  name: string
  role: 'employee'
  level: number
  streak: number
  activeCourses: number
  completedCourses: number
}

export const user: User = {
  name: 'Pepito',
  role: 'employee',
  level: 3,
  streak: 12,
  activeCourses: 2,
  completedCourses: 5,
}

export const courses: Course[] = [
  {
    id: 'seguridad-alimentaria',
    title: 'Seguridad Alimentaria',
    subtitle: '3 modulos -- 12 lecciones',
    color: '#4BA862',
    progress: 75,
    status: 'in-progress',
    modules: [
      {
        id: 'sa-m1',
        title: 'Fundamentos de higiene',
        lessons: [
          {
            id: 'sa-m1-l1',
            title: 'Introduccion a la seguridad alimentaria',
            content:
              'La seguridad alimentaria es un conjunto de practicas y normativas diseñadas para garantizar que los alimentos sean seguros para el consumo humano. En este modulo, aprenderemos los principios basicos que todo trabajador del sector alimentario debe conocer.\n\nLos pilares de la seguridad alimentaria incluyen: control de temperaturas, higiene personal, limpieza de superficies y control de contaminacion cruzada. Cada uno de estos aspectos es fundamental para prevenir enfermedades transmitidas por alimentos.',
            exercise: {
              id: 'sa-m1-l1-e1',
              type: 'multiple-choice',
              question: 'Cual es uno de los pilares de la seguridad alimentaria?',
              options: [
                'Decoracion del plato',
                'Control de temperaturas',
                'Velocidad de servicio',
                'Costo del ingrediente',
              ],
              correctIndex: 1,
            },
          },
          {
            id: 'sa-m1-l2',
            title: 'Lavado de manos correcto',
            content:
              'El lavado de manos es la barrera mas efectiva contra la contaminacion. Se debe realizar durante al menos 20 segundos con agua tibia y jabon antibacterial.\n\nMomentos criticos para el lavado de manos:\n- Antes de manipular alimentos\n- Despues de ir al baño\n- Despues de tocar superficies no sanitizadas\n- Al cambiar de tarea entre alimentos crudos y cocidos',
            exercise: {
              id: 'sa-m1-l2-e1',
              type: 'true-false',
              question: 'El lavado de manos debe durar al menos 20 segundos.',
              options: ['Verdadero', 'Falso'],
              correctIndex: 0,
            },
          },
        ],
      },
      {
        id: 'sa-m2',
        title: 'Control de temperaturas',
        lessons: [
          {
            id: 'sa-m2-l1',
            title: 'Zona de peligro',
            content:
              'La zona de peligro se define como el rango de temperatura entre 5 C y 65 C. En este rango, las bacterias se multiplican rapidamente, duplicandose cada 20 minutos en condiciones ideales.\n\nPara mantener la seguridad:\n- Alimentos frios: mantener por debajo de 5 C\n- Alimentos calientes: mantener por encima de 65 C\n- No dejar alimentos en zona de peligro por mas de 2 horas',
          },
          {
            id: 'sa-m2-l2',
            title: 'Uso del termometro',
            content:
              'El termometro de alimentos es una herramienta esencial. Debe calibrarse regularmente y usarse para verificar temperaturas internas de coccion.\n\nTemperaturas minimas de coccion:\n- Aves: 74 C\n- Carne molida: 71 C\n- Pescado: 63 C\n- Recalentamiento: 74 C',
            exercise: {
              id: 'sa-m2-l2-e1',
              type: 'multiple-choice',
              question: 'Cual es la temperatura minima de coccion para aves?',
              options: ['63 C', '71 C', '74 C', '80 C'],
              correctIndex: 2,
            },
          },
        ],
      },
      {
        id: 'sa-m3',
        title: 'Contaminacion cruzada',
        lessons: [
          {
            id: 'sa-m3-l1',
            title: 'Tipos de contaminacion',
            content:
              'La contaminacion cruzada ocurre cuando microorganismos daninos se transfieren de un alimento o superficie a otro. Existen tres tipos principales:\n\n1. Directa: contacto directo entre alimentos crudos y cocidos\n2. Indirecta: a traves de superficies, utensilios o equipos\n3. Por manipulador: a traves de las manos del personal',
          },
        ],
      },
    ],
  },
  {
    id: 'atencion-cliente',
    title: 'Atencion al Cliente',
    subtitle: '2 modulos -- 8 lecciones',
    color: '#3661A5',
    progress: 40,
    status: 'in-progress',
    modules: [
      {
        id: 'ac-m1',
        title: 'Comunicacion efectiva',
        lessons: [
          {
            id: 'ac-m1-l1',
            title: 'Escucha activa',
            content:
              'La escucha activa es la habilidad mas importante en la atencion al cliente. Consiste en prestar atencion completa al cliente, sin interrumpir, y demostrar que entendemos su mensaje.\n\nTecnicas de escucha activa:\n- Mantener contacto visual\n- Asentir para mostrar comprension\n- Parafrasear lo que dice el cliente\n- Hacer preguntas clarificadoras',
            exercise: {
              id: 'ac-m1-l1-e1',
              type: 'true-false',
              question: 'Parafrasear lo que dice el cliente es una tecnica de escucha activa.',
              options: ['Verdadero', 'Falso'],
              correctIndex: 0,
            },
          },
          {
            id: 'ac-m1-l2',
            title: 'Lenguaje positivo',
            content:
              'El lenguaje positivo transforma la experiencia del cliente. En lugar de decir lo que no podemos hacer, enfocamos en lo que si podemos ofrecer.\n\nEjemplos:\n- En vez de "No tenemos eso" -> "Le puedo ofrecer estas alternativas"\n- En vez de "Eso no es mi area" -> "Le conecto con quien puede ayudarle mejor"',
          },
        ],
      },
      {
        id: 'ac-m2',
        title: 'Manejo de quejas',
        lessons: [
          {
            id: 'ac-m2-l1',
            title: 'Protocolo de quejas',
            content:
              'El protocolo LEDA para manejo de quejas:\n\nL - Escuchar sin interrumpir\nE - Empatizar con el cliente\nD - Disculparse sinceramente\nA - Actuar para resolver\n\nCada paso es esencial. Saltarse alguno puede escalar la situacion.',
            exercise: {
              id: 'ac-m2-l1-e1',
              type: 'multiple-choice',
              question: 'Que significa la A en el protocolo LEDA?',
              options: ['Aceptar', 'Actuar', 'Analizar', 'Agradecer'],
              correctIndex: 1,
            },
          },
        ],
      },
    ],
  },
  {
    id: 'protocolo-limpieza',
    title: 'Protocolo de Limpieza',
    subtitle: '2 modulos -- 6 lecciones',
    color: '#d97706',
    progress: 15,
    status: 'in-progress',
    modules: [
      {
        id: 'pl-m1',
        title: 'Productos y diluciones',
        lessons: [
          {
            id: 'pl-m1-l1',
            title: 'Tipos de desinfectantes',
            content:
              'Los desinfectantes de uso comun en la industria alimentaria se clasifican en:\n\n1. Compuestos de cloro: efectivos contra amplio espectro de microorganismos\n2. Compuestos de amonio cuaternario: no corrosivos, baja toxicidad\n3. Yodoforos: accion rapida\n4. Peroxido de hidrogeno: biodegradable\n\nCada tipo tiene su concentracion y tiempo de contacto especifico.',
          },
        ],
      },
      {
        id: 'pl-m2',
        title: 'Procedimientos por area',
        lessons: [
          {
            id: 'pl-m2-l1',
            title: 'Limpieza de cocina',
            content:
              'El protocolo de limpieza de cocina sigue el orden:\n1. Retirar residuos solidos\n2. Preenjuague con agua caliente\n3. Lavado con detergente\n4. Enjuague\n5. Sanitizado\n6. Secado al aire\n\nFrecuencia: superficies de trabajo cada 2 horas, pisos al cierre, campanas semanalmente.',
            exercise: {
              id: 'pl-m2-l1-e1',
              type: 'multiple-choice',
              question: 'Con que frecuencia deben limpiarse las superficies de trabajo?',
              options: ['Cada hora', 'Cada 2 horas', 'Cada turno', 'Diariamente'],
              correctIndex: 1,
            },
          },
        ],
      },
    ],
  },
  {
    id: 'gestion-inventario',
    title: 'Gestion de Inventario',
    subtitle: '2 modulos -- 5 lecciones',
    color: '#7c3aed',
    progress: 100,
    status: 'completed',
    modules: [
      {
        id: 'gi-m1',
        title: 'Metodo PEPS',
        lessons: [
          {
            id: 'gi-m1-l1',
            title: 'Primero en entrar, primero en salir',
            content:
              'El metodo PEPS (Primero en Entrar, Primero en Salir) es fundamental para la rotacion de inventario. Asegura que los productos mas antiguos se usen primero, reduciendo el desperdicio.\n\nReglas basicas:\n- Etiquetar todo con fecha de recepcion\n- Colocar lo nuevo atras, lo antiguo adelante\n- Verificar fechas de caducidad al recibir',
          },
        ],
      },
      {
        id: 'gi-m2',
        title: 'Control de stock',
        lessons: [
          {
            id: 'gi-m2-l1',
            title: 'Conteo de inventario',
            content: 'El conteo de inventario debe realizarse de forma periodica y sistematica. Un buen control de stock previene tanto el exceso como la falta de productos.',
          },
        ],
      },
    ],
  },
  {
    id: 'normativa-laboral',
    title: 'Normativa Laboral Basica',
    subtitle: '3 modulos -- 9 lecciones',
    color: '#3661A5',
    progress: 100,
    status: 'completed',
    modules: [
      {
        id: 'nl-m1',
        title: 'Derechos del trabajador',
        lessons: [
          {
            id: 'nl-m1-l1',
            title: 'Contrato y condiciones',
            content: 'Todo trabajador tiene derecho a un contrato escrito que especifique sus condiciones laborales, salario, horario y funciones.',
          },
        ],
      },
    ],
  },
  {
    id: 'primeros-auxilios',
    title: 'Primeros Auxilios',
    subtitle: '2 modulos -- 7 lecciones',
    color: '#dc2626',
    progress: 0,
    status: 'pending',
    modules: [
      {
        id: 'pa-m1',
        title: 'Evaluacion inicial',
        lessons: [
          {
            id: 'pa-m1-l1',
            title: 'Protocolo PAS',
            content:
              'El protocolo PAS (Proteger, Avisar, Socorrer) es la base de toda actuacion en primeros auxilios.\n\n1. Proteger: asegurar la zona, evitar mas accidentes\n2. Avisar: llamar a emergencias (112)\n3. Socorrer: atender a la victima segun conocimientos',
          },
        ],
      },
      {
        id: 'pa-m2',
        title: 'Heridas y quemaduras',
        lessons: [
          {
            id: 'pa-m2-l1',
            title: 'Tratamiento de quemaduras leves',
            content: 'Ante una quemadura leve: enfriar con agua corriente durante 10-20 minutos. No aplicar hielo, pasta de dientes ni remedios caseros. Cubrir con gasa esteril.',
          },
        ],
      },
    ],
  },
  {
    id: 'sostenibilidad',
    title: 'Sostenibilidad en el Trabajo',
    subtitle: '1 modulo -- 4 lecciones',
    color: '#4BA862',
    progress: 0,
    status: 'pending',
    modules: [
      {
        id: 'so-m1',
        title: 'Reduccion de residuos',
        lessons: [
          {
            id: 'so-m1-l1',
            title: 'Las 3R en el entorno laboral',
            content: 'Reducir, Reutilizar, Reciclar. Aplicar las 3R en el entorno laboral reduce costes y minimiza el impacto ambiental. Cada empleado puede contribuir con pequeñas acciones diarias.',
          },
        ],
      },
    ],
  },
]

export const skills: Skill[] = [
  { name: 'Higiene', level: 'high', category: 'Operaciones' },
  { name: 'Servicio al cliente', level: 'medium', category: 'Operaciones' },
  { name: 'Cocina', level: 'low', category: 'Operaciones' },
  { name: 'Seguridad', level: 'expert', category: 'Operaciones' },
  { name: 'Gestion de inventario', level: 'high', category: 'Administracion' },
  { name: 'Normativa laboral', level: 'medium', category: 'Administracion' },
  { name: 'Primeros auxilios', level: 'low', category: 'Seguridad y Salud' },
  { name: 'Sostenibilidad', level: 'low', category: 'Seguridad y Salud' },
]

export const activity: ActivityItem[] = [
  {
    id: 'a1',
    text: 'Completaste la leccion "Lavado de manos correcto"',
    time: 'Hace 2 horas',
  },
  {
    id: 'a2',
    text: 'Aprobaste el ejercicio de Zona de peligro',
    time: 'Hace 5 horas',
  },
  {
    id: 'a3',
    text: 'Iniciaste el curso "Protocolo de Limpieza"',
    time: 'Ayer',
  },
  {
    id: 'a4',
    text: 'Subiste al Nivel 3',
    time: 'Hace 2 dias',
  },
  {
    id: 'a5',
    text: 'Completaste el curso "Gestion de Inventario"',
    time: 'Hace 3 dias',
  },
]

export const chatMessages: { id: string; sender: 'user' | 'bot'; text: string; citation?: string }[] = [
  {
    id: 'msg1',
    sender: 'bot',
    text: 'Hola, Pepito. Soy tu asistente de formacion. Puedes preguntarme sobre cualquier tema de tus cursos.',
  },
  {
    id: 'msg2',
    sender: 'user',
    text: 'Como se hace una devolucion de producto?',
  },
  {
    id: 'msg3',
    sender: 'bot',
    text: 'Para realizar una devolucion de producto, sigue estos pasos:\n\n1. Verifica que el producto esta dentro del plazo de devolucion (15 dias)\n2. Comprueba que tiene el ticket de compra\n3. Inspecciona el estado del producto\n4. Procesa la devolucion en el sistema POS\n5. Emite el comprobante de devolucion al cliente',
    citation: 'Fuente: Manual de Devoluciones, p.12',
  },
  {
    id: 'msg4',
    sender: 'user',
    text: 'Y si no tiene el ticket?',
  },
  {
    id: 'msg5',
    sender: 'bot',
    text: 'Si el cliente no tiene el ticket de compra, puedes buscar la transaccion en el sistema usando la tarjeta de fidelidad o los ultimos 4 digitos de la tarjeta de pago. Si no se encuentra registro, la devolucion debe ser autorizada por un supervisor.',
    citation: 'Fuente: Manual de Devoluciones, p.15',
  },
]

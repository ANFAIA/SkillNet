import type { Meta } from '@storybook/react-vite'
import { SlideCanvas, type SlideCanvasSpec } from './SlideCanvas'

const meta: Meta<typeof SlideCanvas> = {
  title: 'Courses/SlideCanvas',
  component: SlideCanvas,
  parameters: {
    layout: 'fullscreen',
    a11y: { test: 'error' },
  },
}
export default meta

const slides: SlideCanvasSpec[] = [
  {
    title: 'Atender bien también es un proceso',
    subtitle:
      'Una guía práctica para resolver incidencias con claridad, criterio y responsabilidad compartida.',
    composition: 'cover',
    blocks: [],
  },
  {
    title: 'La primera respuesta condiciona toda la conversación',
    subtitle: 'Antes de buscar una solución, necesitamos construir una comprensión común.',
    composition: 'split',
    blocks: [
      {
        type: 'callout',
        tone: 'info',
        text: 'Escuchar no es esperar a que la otra persona termine: es comprobar que hemos entendido qué ocurre, a quién afecta y qué necesita ahora.',
      },
      {
        type: 'text',
        variant: 'body',
        text: 'Resume el problema con tus propias palabras y confirma los datos relevantes. Esta pausa breve reduce malentendidos, evita soluciones prematuras y transmite que la incidencia se está tratando con atención.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'Primero comprender. Después, resolver.',
      },
    ],
  },
  {
    title: 'Las cuatro capacidades de una respuesta útil',
    subtitle:
      'La calidad no depende de una frase perfecta, sino de combinar bien estas capacidades.',
    composition: 'grid',
    blocks: [
      {
        type: 'card',
        title: 'Comprender',
        text: 'Identifica el problema real, su impacto y la urgencia antes de decidir qué hacer.',
      },
      {
        type: 'card',
        title: 'Explicar',
        text: 'Describe las opciones y sus límites con un lenguaje concreto, sin esconderse detrás del proceso.',
      },
      {
        type: 'card',
        title: 'Responsabilizarse',
        text: 'Mantén la propiedad de la conversación aunque la solución dependa de otro equipo.',
      },
      {
        type: 'card',
        title: 'Cerrar',
        text: 'Deja claro el siguiente paso, quién lo realizará y cuándo recibirá noticias la persona.',
      },
    ],
  },
  {
    title: 'De la incidencia al cierre',
    subtitle: 'Cada etapa resuelve una pregunta distinta de la persona que solicita ayuda.',
    composition: 'timeline',
    blocks: [
      {
        type: 'timeline',
        label: 'Ciclo de atención',
        steps: ['Recibir', 'Diagnosticar', 'Actuar', 'Confirmar'],
        details: [
          'Reconocer la situación y recopilar el contexto mínimo.',
          'Distinguir síntomas, causa probable e impacto operativo.',
          'Resolver, derivar o acordar una alternativa viable.',
          'Verificar el resultado y comunicar el cierre con claridad.',
        ],
      },
    ],
  },
  {
    title: 'Cambiar el foco cambia la experiencia',
    subtitle: 'La información puede ser la misma; la sensación de acompañamiento no lo es.',
    composition: 'comparison',
    blocks: [
      {
        type: 'callout',
        tone: 'warn',
        text: 'EVITA · “Eso no depende de mí.” Traslada la carga a la persona y convierte la organización interna en su problema.',
      },
      {
        type: 'callout',
        tone: 'success',
        text: 'PREFIERE · “Voy a localizar a quien puede resolverlo y te confirmaré el siguiente paso antes de las 16:00.”',
      },
      {
        type: 'text',
        text: 'La segunda respuesta no promete una solución inmediata. Promete algo más creíble: propiedad, una acción concreta y un momento de actualización.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'No hace falta tener todas las respuestas para hacerse cargo.',
      },
    ],
  },
  {
    title: 'El plazo depende del tipo de incidencia',
    subtitle:
      'Los datos explican la regla; la interpretación ayuda a tomar una decisión correcta.',
    composition: 'data',
    blocks: [
      {
        type: 'chart',
        kind: 'bar',
        title: 'Plazo máximo de gestión (días)',
        labels: ['Devolución ordinaria', 'Producto defectuoso', 'Error de facturación'],
        values: [30, 60, 15],
      },
      {
        type: 'text',
        text: 'El plazo legal o interno marca el límite, no el momento ideal para responder. La primera comunicación debe producirse cuanto antes y explicar qué comprobaciones siguen abiertas.',
      },
      {
        type: 'callout',
        tone: 'info',
        text: 'Regla práctica: comunica pronto, actualiza cuando cambie la situación y nunca dejes que el plazo sustituya al seguimiento.',
      },
    ],
  },
]

const phishingSlides: SlideCanvasSpec[] = [
  {
    title: 'Detectar un correo de phishing antes de que sea tarde',
    subtitle:
      'Una guía práctica para reconocer señales de manipulación y actuar sin poner en riesgo la organización.',
    composition: 'cover',
    blocks: [],
  },
  {
    title: 'El ataque busca una reacción, no solo una contraseña',
    subtitle: 'La urgencia reduce nuestra capacidad de comprobar lo que tenemos delante.',
    composition: 'split',
    blocks: [
      {
        type: 'callout',
        tone: 'warn',
        text: '“Tu cuenta será bloqueada en 30 minutos.” El mensaje intenta que actúes antes de pensar, verificar o pedir ayuda.',
      },
      {
        type: 'text',
        text: 'Un correo de phishing puede imitar a una persona conocida, una herramienta habitual o un proveedor real. La señal más importante no siempre está en el diseño: está en la acción excepcional que te pide realizar.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'Cuando un mensaje introduce presión, añade una pausa.',
      },
    ],
  },
  {
    title: 'Cuatro señales que deben activar una comprobación',
    subtitle: 'Una sola señal no demuestra un fraude; varias juntas justifican detenerse.',
    composition: 'grid',
    blocks: [
      {
        type: 'card',
        title: 'Remitente extraño',
        text: 'El nombre parece correcto, pero el dominio contiene cambios, letras añadidas o una cuenta externa.',
      },
      {
        type: 'card',
        title: 'Urgencia artificial',
        text: 'Amenaza con consecuencias inmediatas o presenta una oportunidad que desaparecerá si no actúas ya.',
      },
      {
        type: 'card',
        title: 'Enlace inesperado',
        text: 'La dirección visible no coincide con el destino real o conduce a una página de acceso no habitual.',
      },
      {
        type: 'card',
        title: 'Petición excepcional',
        text: 'Solicita credenciales, pagos, códigos de verificación o cambios de cuenta fuera del proceso normal.',
      },
    ],
  },
  {
    title: 'La pausa de seguridad en cuatro pasos',
    subtitle: 'No necesitas investigar el ataque por tu cuenta: solo interrumpir la cadena.',
    composition: 'process',
    blocks: [
      {
        type: 'steps',
        title: 'Antes de responder o hacer clic',
        steps: [
          'Detente: no abras enlaces, archivos ni códigos QR del mensaje.',
          'Comprueba: revisa el dominio y accede al servicio desde tu marcador habitual.',
          'Verifica: contacta con la persona por otro canal si la petición es excepcional.',
          'Reporta: utiliza el canal de seguridad y conserva el mensaje para su análisis.',
        ],
      },
      {
        type: 'callout',
        tone: 'info',
        text: 'Reportar una sospecha razonable es una conducta segura, incluso cuando el mensaje termina siendo legítimo.',
      },
    ],
  },
  {
    title: 'Verificar por otro canal cambia el resultado',
    subtitle: 'Nunca utilices los datos de contacto incluidos en el propio mensaje sospechoso.',
    composition: 'comparison',
    blocks: [
      {
        type: 'callout',
        tone: 'warn',
        text: 'EVITA · Responder al correo: “¿Eres tú?” El atacante controla esa conversación y puede confirmar cualquier historia.',
      },
      {
        type: 'callout',
        tone: 'success',
        text: 'PREFIERE · Abrir Teams, llamar al número conocido o consultar directamente la aplicación corporativa.',
      },
      {
        type: 'text',
        text: 'Un canal independiente rompe el contexto creado por el atacante. La comprobación debe comenzar fuera del correo, del enlace y del número que contiene.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'Verifica la identidad, no la apariencia del mensaje.',
      },
    ],
  },
  {
    title: 'Qué hacer según lo que haya ocurrido',
    subtitle: 'Actuar pronto limita el impacto y permite que seguridad proteja al resto del equipo.',
    composition: 'data',
    blocks: [
      {
        type: 'table',
        headers: ['Situación', 'Acción inmediata'],
        rows: [
          ['Solo recibiste el mensaje', 'Repórtalo y elimínalo cuando seguridad lo confirme.'],
          ['Abriste el enlace', 'Cierra la página y contacta con seguridad.'],
          ['Introdujiste credenciales', 'Avisa de inmediato y cambia la contraseña desde el portal oficial.'],
          ['Aprobaste un acceso o pago', 'Llama al canal urgente de seguridad o fraude.'],
        ],
      },
      {
        type: 'callout',
        tone: 'info',
        text: 'No ocultes el error ni intentes solucionarlo solo. La velocidad y la información precisa son las mejores herramientas de contención.',
      },
    ],
  },
]

const handoffSlides: SlideCanvasSpec[] = [
  {
    title: 'Un buen traspaso evita trabajo invisible',
    subtitle:
      'Cómo mover una tarea entre personas o equipos sin perder contexto, responsabilidad ni ritmo.',
    composition: 'cover',
    blocks: [],
  },
  {
    title: 'Enviar información no equivale a transferir responsabilidad',
    subtitle: 'El siguiente equipo necesita entender el punto de partida y poder actuar.',
    composition: 'split',
    blocks: [
      {
        type: 'callout',
        tone: 'warn',
        text: 'Un “te lo paso para que lo mires” desplaza la tarea, pero no explica qué ocurre, qué se ha probado ni qué decisión hace falta.',
      },
      {
        type: 'text',
        text: 'El traspaso termina cuando la otra parte confirma que dispone del contexto mínimo, comprende la prioridad y acepta el siguiente paso.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'La claridad reduce esperas, preguntas repetidas y responsabilidad difusa.',
      },
    ],
  },
  {
    title: 'Las cuatro piezas del contexto mínimo',
    subtitle: 'Una estructura breve permite entender la tarea sin reconstruir toda su historia.',
    composition: 'grid',
    blocks: [
      {
        type: 'card',
        title: 'Estado',
        text: 'Qué se ha completado, qué sigue abierto y dónde se encuentra la información de trabajo.',
      },
      {
        type: 'card',
        title: 'Objetivo',
        text: 'Qué resultado se espera y qué condición permitirá considerar la tarea terminada.',
      },
      {
        type: 'card',
        title: 'Riesgo',
        text: 'Qué bloqueo, dependencia o plazo puede alterar la prioridad o el enfoque.',
      },
      {
        type: 'card',
        title: 'Siguiente paso',
        text: 'Quién hace qué acción, antes de cuándo y cómo se confirmará el avance.',
      },
    ],
  },
  {
    title: 'Un traspaso completo cabe en cuatro movimientos',
    subtitle: 'La secuencia hace visible el cambio de responsabilidad.',
    composition: 'timeline',
    blocks: [
      {
        type: 'timeline',
        label: 'Secuencia de traspaso',
        steps: ['Resumir', 'Señalar', 'Acordar', 'Confirmar'],
        details: [
          'Describe el estado y el resultado esperado.',
          'Expón la prioridad, los riesgos y las dependencias.',
          'Define el siguiente paso y su responsable.',
          'Comprueba que la otra parte acepta la tarea.',
        ],
      },
    ],
  },
  {
    title: 'La diferencia está en lo que puede hacer quien recibe',
    subtitle: 'Un mensaje útil permite actuar sin abrir una investigación desde cero.',
    composition: 'comparison',
    blocks: [
      {
        type: 'callout',
        tone: 'warn',
        text: 'INCOMPLETO · “Te reenvío el hilo. Es urgente y lo necesita dirección.”',
      },
      {
        type: 'callout',
        tone: 'success',
        text: 'ACCIONABLE · “Falta validar la cifra final. Finanzas responde hoy a las 15:00; después, Marta envía la versión aprobada.”',
      },
      {
        type: 'text',
        text: 'La segunda versión hace visible el estado, la dependencia, la persona responsable y el momento de la próxima acción.',
      },
      {
        type: 'text',
        variant: 'lead',
        text: 'Si quien recibe no sabe cómo empezar, el traspaso aún no ha terminado.',
      },
    ],
  },
  {
    title: 'Comprueba el traspaso antes de cerrar',
    subtitle: 'Una revisión de veinte segundos evita horas de reconstrucción posterior.',
    composition: 'data',
    blocks: [
      {
        type: 'table',
        headers: ['Pregunta', 'Debe quedar claro'],
        rows: [
          ['¿Dónde estamos?', 'Estado actual y trabajo ya realizado'],
          ['¿Qué importa ahora?', 'Objetivo, prioridad y riesgo principal'],
          ['¿Quién actúa?', 'Responsable y siguiente paso concreto'],
          ['¿Cuándo sabremos más?', 'Plazo o momento de actualización'],
        ],
      },
      {
        type: 'callout',
        tone: 'info',
        text: 'Cierra con una confirmación explícita: “¿Tienes lo necesario para continuar?”.',
      },
    ],
  },
]

export const Composiciones = () => (
  <main className="min-h-screen bg-bg-subtle p-6">
    <div className="mx-auto grid max-w-5xl gap-8">
      {slides.map((slide) => (
        <SlideCanvas key={slide.title} slide={slide} />
      ))}
    </div>
  </main>
)

export const PresentacionGenerada = () => (
  <main className="min-h-screen bg-bg-subtle p-6">
    <div className="mx-auto grid max-w-5xl gap-8">
      {phishingSlides.map((slide) => (
        <SlideCanvas key={slide.title} slide={slide} />
      ))}
    </div>
  </main>
)

export const TraspasosOperativos = () => (
  <main className="min-h-screen bg-bg-subtle p-6">
    <div className="mx-auto grid max-w-5xl gap-8">
      {handoffSlides.map((slide) => (
        <SlideCanvas key={slide.title} slide={slide} />
      ))}
    </div>
  </main>
)

/**
 * Landing copy, per locale.
 *
 * The docs are translated as whole markdown files under `src/content/docs/`,
 * so they need no dictionary. The landing is React components, and its strings
 * used to be inlined as module constants inside each one. They live here
 * instead so a single `/en/` page can render the very same components, and so
 * a missing translation is a type error rather than a Spanish sentence
 * shipped on the English page.
 */
import type { Locale } from "./config";

const es = {
  meta: {
    title: "SkillNet",
    description:
      "SkillNet convierte una idea o fuente en un curso que puede adaptar sus explicaciones, actividades e interfaz a cada persona.",
  },
  nav: {
    what: "Qué es SkillNet",
    how: "Cómo funciona",
    who: "Para quién",
    contact: "Contacto",
    docs: "Documentación",
    docsIndex: "Índice",
    backHome: "Volver al inicio",
    main: "Navegación principal",
    menu: "Menú",
    openMenu: "Abrir menú",
    closeMenu: "Cerrar menú",
    switchLang: "Cambiar a inglés",
  },
  hero: {
    title: "Aprender no tiene por qué ser igual para todos.",
    subtitle:
      "SkillNet convierte una idea o fuente en un curso que puede adaptar sus explicaciones, actividades e interfaz a cada persona.",
    github: "Explorar en GitHub",
    moreCta: "Saber más",
  },
  whatWeDo: {
    title: "Qué es SkillNet",
    body: "SkillNet es un sistema de aprendizaje adaptativo y open source. Parte de lo que quieres enseñar y construye un curso completo: organiza el contenido, crea las lecciones y los ejercicios y mantiene la relación con las fuentes utilizadas. Sobre esa misma base, puede adaptar la explicación, la práctica y la interfaz al contexto de cada persona sin cambiar el objetivo de aprendizaje.",
  },
  problem: {
    quote: "No puedes juzgar a un pez por cómo trepa un árbol.",
    explanation:
      "La misma meta no obliga a recorrer el mismo camino. Una persona puede necesitar otro ejemplo, más contexto, una práctica distinta o una interfaz que le permita explorar la idea. Personalizar no significa cambiar lo que se aprende, sino adaptar cómo se llega a comprenderlo.",
  },
  howItWorks: {
    title: "Cómo funciona",
    lead: "El curso parte de un conocimiento y unos objetivos comunes. A partir de ahí, las preferencias declaradas, el rol, el nivel y el progreso de cada persona sirven como señales para decidir qué explicación, actividad, apoyo o interfaz mostrar. Son hipótesis que pueden cambiar, no etiquetas fijas sobre cómo aprende alguien.",
    idea: "Cambian lo que ya sabemos, el contexto, el ritmo y el apoyo que necesitamos. La misma idea puede necesitar otra explicación, otro ejemplo o una forma diferente de practicarla.",
    modes: { texto: "Texto", imagen: "Imagen", video: "Vídeo", audio: "Audio" },
    mediaHeading: "Todos aprendemos de forma distinta.",
    imageAlt: "Infografía: todos aprendemos de forma distinta",
    videoCaptions: [
      "Cuatro personas, el mismo curso.",
      "Una lo dibuja para entenderlo.",
      "Otro prefiere escucharlo.",
      "Mismo conocimiento, distinto camino.",
    ],
    /** Second at which each caption starts in `how-it-works-video-es.mp3`.
        Measured from the real duration of each narrated line, so the caption on
        screen is always the one being spoken. */
    videoCuts: [0, 3.6, 6, 7.99],
    videoDuration: 11.22,
    videoPlay: "Reproducir la secuencia con narración",
    videoPause: "Pausar la secuencia",
    videoNext: "Ver el siguiente fotograma",
    audioPlay: "Reproducir el resumen en audio",
    audioPause: "Pausar el resumen en audio",
    audioQuote: "“Todos aprendemos de forma distinta…”",
    caption:
      "El formato es solo una parte. La explicación, la práctica y la interfaz también pueden cambiar.",
  },
  profiles: {
    title: "Para quién",
    lead: "El sistema es el mismo en los tres casos. Lo que cambia es quién decide qué hay que aprender y cuánto margen tiene cada persona para recorrerlo a su manera.",
    companies: {
      label: "Empresas",
      detail:
        "Onboarding y formación interna sobre los procesos y la documentación que la organización ya tiene.",
    },
    education: {
      label: "Educación",
      detail:
        "Clases y materiales que conservan objetivos comunes mientras cambia la experiencia de cada estudiante.",
    },
    individuals: {
      label: "Personas",
      detail:
        "Aprendizaje por cuenta propia, al ritmo y con el nivel de detalle que cada uno necesita.",
    },
  },
  collaboration: {
    title: "Open source",
    status: "Versión en desarrollo",
    body1:
      "SkillNet se construye en abierto: el código puede revisarse, ejecutarse y mejorarse públicamente. Es self-hosted, con el proveedor de IA que elijas o con modelos locales, y su API, el servicio A2A y el servidor MCP permiten usarlo desde otras herramientas. Licencia Apache 2.0.",
    body2:
      "La instancia y sus datos quedan bajo tu control; si eliges un proveedor externo, el tratamiento del contenido dependerá de su configuración.",
    cardTitle: "Explorar SkillNet en GitHub",
    cardDetail:
      "Revisa el código, pruébalo o deja una estrella para seguir su evolución.",
  },
  vision: {
    title: "Visión",
    body1:
      "Muchas tecnologías nuevas empiezan imitando a las anteriores. Los primeros coches parecían carruajes y las primeras páginas web trasladaban el papel a una pantalla. ¿Y si a buena parte de la educación digital le está pasando algo parecido, con libros, clases y recorridos lineales llevados a internet sin cambiar del todo la experiencia? Si es así, la inteligencia artificial abre la posibilidad de buscar un lenguaje propio para aprender, siempre como herramienta al servicio de docentes y estudiantes.",
    body2:
      "SkillNet ya trabaja en esa dirección. Genera interfaces con OpenUI y las compone con componentes Didact creados para aprender. Las preferencias declaradas, el rol, el nivel y el progreso pueden cambiar la presentación, las actividades y los apoyos que aparecen en el curso.",
    body3:
      "La siguiente frontera es generar la propia experiencia interactiva en lugar de limitarse a elegir entre formatos existentes. Con los modelos actuales todavía resulta caro y lento hacerlo bien, pero ese límite seguirá cambiando.",
    body4:
      "Un curso de animación no debería limitarse a mostrar un vídeo sobre animación: podría generar un simulador de fotogramas para que cada persona experimente con sus propias manos. Eso todavía no es viable a escala, pero es la dirección que SkillNet quiere explorar.",
  },
  builtWith: {
    title: "Hecho con",
    lead: "Dos proyectos propios y abiertos que SkillNet usa por dentro.",
    didactTitle: "Componentes para aprender",
    didactDetail:
      "La biblioteca de componentes React con la que SkillNet compone lo que aparece dentro de una lección.",
    curioTitle: "Explicar en contexto",
    curioDetail:
      "El patrón de pulsar una palabra y ver su explicación sin salir de lo que estabas leyendo, traído a las lecciones.",
  },
  contact: {
    title: "Contacto",
    lead: "SkillNet sigue en desarrollo. Si la idea te interesa, puedes probarlo, contarme qué mejorarías o contribuir directamente al proyecto.",
    developedUnder: "Desarrollado bajo",
    grantSponsor: "Beca ANFAIA 2026, patrocinada por",
    mail: "Escríbenos",
  },
  footer: {
    tagline: "Un proyecto abierto sobre cómo puede cambiar la experiencia de aprender.",
    projectBy: "Un proyecto de",
    grantBy: "Beca patrocinada por",
    contact: "Contacto",
  },
  /* Not `as const`: the leaves must stay `string`, or every English sentence
     would fail to match the Spanish literal it translates. A missing key is
     still a type error, which is the check that matters. */
};

/**
 * English is a localisation by intent, not a literal translation of the
 * Spanish: sentences are re-cut where English reads better short.
 */
const en: typeof es = {
  meta: {
    title: "SkillNet",
    description:
      "SkillNet turns an idea or a source into a course that can adapt its explanations, activities and interface to each person.",
  },
  nav: {
    what: "What SkillNet is",
    how: "How it works",
    who: "Who it is for",
    contact: "Contact",
    docs: "Documentation",
    docsIndex: "Index",
    backHome: "Back to home",
    main: "Main navigation",
    menu: "Menu",
    openMenu: "Open menu",
    closeMenu: "Close menu",
    switchLang: "Switch to Spanish",
  },
  hero: {
    title: "Learning does not have to be the same for everyone.",
    subtitle:
      "SkillNet turns an idea or a source into a course that can adapt its explanations, activities and interface to each person.",
    github: "Explore on GitHub",
    moreCta: "Learn more",
  },
  whatWeDo: {
    title: "What SkillNet is",
    body: "SkillNet is an open source adaptive learning system. It starts from what you want to teach and builds a complete course: it organises the content, writes the lessons and the exercises, and keeps the link back to the sources it used. On that same base, it can adapt the explanation, the practice and the interface to each person's context without changing the learning objective.",
  },
  problem: {
    quote: "You cannot judge a fish by how it climbs a tree.",
    explanation:
      "The same goal does not force the same path. One person may need a different example, more context, a different exercise, or an interface that lets them explore the idea. Personalising is not about changing what is learned, but about adapting how someone comes to understand it.",
  },
  howItWorks: {
    title: "How it works",
    lead: "A course starts from shared knowledge and shared objectives. From there, each person's declared preferences, role, level and progress act as signals for deciding which explanation, activity, support or interface to show. They are hypotheses that can change, not fixed labels about how someone learns.",
    idea: "What changes is what we already know, the context, the pace and the support we need. The same idea may need another explanation, another example, or a different way to practise it.",
    modes: { texto: "Text", imagen: "Image", video: "Video", audio: "Audio" },
    mediaHeading: "We all learn differently.",
    imageAlt: "Infographic: we all learn differently",
    videoCaptions: [
      "Four people, the same course.",
      "One draws it to understand it.",
      "Another would rather hear it.",
      "Same knowledge, a different route.",
    ],
    videoCuts: [0, 2.49, 4.74, 6.88],
    videoDuration: 9.37,
    videoPlay: "Play the sequence with narration",
    videoPause: "Pause the sequence",
    videoNext: "Show the next frame",
    audioPlay: "Play the audio overview",
    audioPause: "Pause the audio overview",
    audioQuote: "“We all learn differently…”",
    caption:
      "Format is only one part. The explanation, the practice and the interface can change too.",
  },
  profiles: {
    title: "Who it is for",
    lead: "The system is the same in all three cases. What changes is who decides what has to be learned, and how much room each person has to get there their own way.",
    companies: {
      label: "Companies",
      detail:
        "Onboarding and internal training built on the processes and documentation the organisation already has.",
    },
    education: {
      label: "Education",
      detail:
        "Classes and materials that keep shared objectives while each student's experience changes.",
    },
    individuals: {
      label: "Individuals",
      detail:
        "Learning on your own, at the pace and level of detail you need.",
    },
  },
  collaboration: {
    title: "Open source",
    status: "Version in development",
    body1:
      "SkillNet is built in the open: the code can be reviewed, run and improved publicly. It is self-hosted, with the AI provider you choose or with local models, and its API, the A2A service and the MCP server let you use it from other tools. Apache 2.0 licence.",
    body2:
      "The instance and its data stay under your control; if you pick an external provider, how the content is handled will depend on their configuration.",
    cardTitle: "Explore SkillNet on GitHub",
    cardDetail:
      "Review the code, try it out, or leave a star to follow how it evolves.",
  },
  vision: {
    title: "Vision",
    body1:
      "Many new technologies start out imitating the ones before them. The first cars looked like carriages, and the first web pages moved paper onto a screen. What if something similar is happening to a good part of digital education, with books, classes and linear paths carried onto the internet without really changing the experience? If so, artificial intelligence opens up the possibility of looking for a language of its own for learning, always as a tool at the service of teachers and students.",
    body2:
      "SkillNet already works in that direction. It generates interfaces with OpenUI and composes them with Didact components made for learning. Declared preferences, role, level and progress can change the presentation, the activities and the support that appear in a course.",
    body3:
      "The next frontier is generating the interactive experience itself, instead of only picking between existing formats. With today's models it is still expensive and slow to do well, but that limit will keep moving.",
    body4:
      "An animation course should not be limited to showing a video about animation: it could generate a frame simulator so each person can experiment with their own hands. That is not viable at scale yet, but it is the direction SkillNet wants to explore.",
  },
  builtWith: {
    title: "Built with",
    lead: "Two open projects of our own that SkillNet uses under the hood.",
    didactTitle: "Components for learning",
    didactDetail:
      "The React component library SkillNet uses to compose what appears inside a lesson.",
    curioTitle: "Explaining in context",
    curioDetail:
      "The pattern of tapping a word and seeing its explanation without leaving what you were reading, brought into lessons.",
  },
  contact: {
    title: "Contact",
    lead: "SkillNet is still in development. If the idea interests you, you can try it, tell me what you would improve, or contribute to the project directly.",
    developedUnder: "Developed under",
    grantSponsor: "ANFAIA 2026 grant, sponsored by",
    mail: "Write to us",
  },
  footer: {
    tagline: "An open project about how the experience of learning can change.",
    projectBy: "A project by",
    grantBy: "Grant sponsored by",
    contact: "Contact",
  },
};

export type Copy = typeof es;

const UI: Record<Locale, Copy> = { es, en };

export function t(locale: Locale): Copy {
  return UI[locale];
}

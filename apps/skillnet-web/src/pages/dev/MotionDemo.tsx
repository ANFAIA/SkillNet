import { useState } from 'react'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import {
  ease,
  duration,
  spring,
  transition,
  pageTransition,
  contentSwap,
  staggerContainer,
  staggerItem,
  itemExit,
  slideVariants,
  backdrop,
  sidebarSlide,
} from '../../lib/motion'

// ── Section wrapper ──────────────────────────────────────────
function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="border border-border rounded-xl p-6 space-y-4">
      <div>
        <h3 className="text-base font-medium text-text">{title}</h3>
        <p className="text-sm text-text-secondary mt-1">{description}</p>
      </div>
      {children}
    </div>
  )
}

function DemoButton({ children, onClick, active }: { children: React.ReactNode; onClick?: () => void; active?: boolean }) {
  return (
    <motion.button
      onClick={onClick}
      className={`text-sm font-medium px-4 py-2 rounded-lg cursor-pointer ${
        active ? 'bg-primary text-white' : 'border border-border hover:bg-bg-muted text-text'
      }`}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      transition={transition.micro}
    >
      {children}
    </motion.button>
  )
}

// ── 1. Page Transitions ──────────────────────────────────────
function PageTransitionDemo() {
  const [page, setPage] = useState(0)
  const pages = ['Dashboard', 'Mis Cursos', 'Skill Map']

  return (
    <Section title="1. Page Transitions" description="Blur + scale al cambiar de ruta. Compara con el fade plano actual.">
      <div className="flex gap-2 mb-4">
        {pages.map((p, i) => (
          <DemoButton key={p} onClick={() => setPage(i)} active={page === i}>{p}</DemoButton>
        ))}
      </div>

      <div className="relative h-40 bg-bg-subtle rounded-lg overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={page}
            className="absolute inset-0 flex items-center justify-center"
            {...pageTransition}
          >
            <div className="text-center">
              <p className="text-lg font-semibold text-text">{pages[page]}</p>
              <p className="text-sm text-text-secondary mt-1">Contenido de la pagina</p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <details className="text-xs text-text-muted">
        <summary className="cursor-pointer">Antes vs Ahora</summary>
        <div className="mt-2 grid grid-cols-2 gap-4">
          <div>
            <p className="font-medium mb-1">Antes:</p>
            <code className="block bg-bg-muted rounded p-2">opacity: 0, y: 8, duration: 0.2</code>
          </div>
          <div>
            <p className="font-medium mb-1">Ahora:</p>
            <code className="block bg-bg-muted rounded p-2">opacity: 0, blur: 8px, scale: 0.98, duration: 0.5</code>
          </div>
        </div>
      </details>
    </Section>
  )
}

// ── 2. Morph Modals ──────────────────────────────────────────
function MorphModalDemo() {
  const [selected, setSelected] = useState<number | null>(null)
  const items = [
    { id: 1, title: 'Seguridad Alimentaria', desc: '12 lecciones', color: 'bg-primary-subtle' },
    { id: 2, title: 'Higiene Industrial', desc: '8 lecciones', color: 'bg-accent-subtle' },
    { id: 3, title: 'Prevencion de Riesgos', desc: '15 lecciones', color: 'bg-warning/10' },
  ]

  return (
    <Section title="2. Morph Modals (layoutId)" description="La card se transforma en el modal. El mismo elemento morfa, no desaparece y reaparece.">
      <LayoutGroup>
        <div className="grid grid-cols-3 gap-3">
          {items.map((item) => (
            selected !== item.id && (
              <motion.div
                key={item.id}
                layoutId={`card-${item.id}`}
                onClick={() => setSelected(item.id)}
                className={`${item.color} border border-border rounded-xl p-4 cursor-pointer`}
                whileHover={{ scale: 1.02 }}
                transition={{ layout: transition.layout }}
              >
                <motion.p layoutId={`title-${item.id}`} className="text-sm font-medium text-text">{item.title}</motion.p>
                <motion.p layoutId={`desc-${item.id}`} className="text-xs text-text-secondary mt-1">{item.desc}</motion.p>
              </motion.div>
            )
          ))}
        </div>

        <AnimatePresence>
          {selected && (() => {
            const item = items.find((i) => i.id === selected)!
            return (
              <>
                <motion.div
                  className="fixed inset-0 bg-black/10 backdrop-blur-sm z-40"
                  {...backdrop}
                  onClick={() => setSelected(null)}
                />
                <motion.div
                  layoutId={`card-${selected}`}
                  className={`fixed inset-4 md:inset-12 lg:inset-24 ${item.color} border border-border rounded-xl p-6 z-50 overflow-auto`}
                  transition={{ layout: transition.layout }}
                >
                  <motion.p layoutId={`title-${selected}`} className="text-xl font-semibold text-text">{item.title}</motion.p>
                  <motion.p layoutId={`desc-${selected}`} className="text-sm text-text-secondary mt-1">{item.desc}</motion.p>
                  <motion.div
                    initial={{ opacity: 0, filter: 'blur(8px)' }}
                    animate={{ opacity: 1, filter: 'blur(0px)' }}
                    transition={{ delay: 0.2, duration: duration.normal, ease: ease.base }}
                    className="mt-6 space-y-3"
                  >
                    <p className="text-sm text-text-secondary">Este contenido aparece con blur despues del morph.</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="bg-bg border border-border rounded-lg p-3 text-xs text-text-secondary">
                          Modulo {i}
                        </div>
                      ))}
                    </div>
                    <DemoButton onClick={() => setSelected(null)}>Cerrar</DemoButton>
                  </motion.div>
                </motion.div>
              </>
            )
          })()}
        </AnimatePresence>
      </LayoutGroup>
    </Section>
  )
}

// ── 3. Staggered Lists ───────────────────────────────────────
function StaggeredListDemo() {
  const [items, setItems] = useState([
    { id: 1, name: 'Ana Garcia', role: 'Marketing' },
    { id: 2, name: 'Carlos Lopez', role: 'Ventas' },
    { id: 3, name: 'Maria Torres', role: 'Operaciones' },
    { id: 4, name: 'Pedro Ruiz', role: 'IT' },
    { id: 5, name: 'Laura Diaz', role: 'RRHH' },
  ])
  const [key, setKey] = useState(0)

  function removeItem(id: number) {
    setItems((prev) => prev.filter((i) => i.id !== id))
  }

  function reset() {
    setItems([
      { id: 1, name: 'Ana Garcia', role: 'Marketing' },
      { id: 2, name: 'Carlos Lopez', role: 'Ventas' },
      { id: 3, name: 'Maria Torres', role: 'Operaciones' },
      { id: 4, name: 'Pedro Ruiz', role: 'IT' },
      { id: 5, name: 'Laura Diaz', role: 'RRHH' },
    ])
    setKey((k) => k + 1)
  }

  return (
    <Section title="3. Staggered Lists" description="Items aparecen secuencialmente con blur. Al eliminar, salen hacia la izquierda.">
      <DemoButton onClick={reset}>Replay</DemoButton>
      <motion.ul
        key={key}
        className="space-y-2 mt-3"
        initial="hidden"
        animate="visible"
        variants={staggerContainer}
      >
        <AnimatePresence>
          {items.map((item) => (
            <motion.li
              key={item.id}
              variants={staggerItem}
              exit={itemExit}
              layout
              className="flex items-center justify-between border border-border rounded-lg p-3 bg-bg"
            >
              <div>
                <p className="text-sm font-medium text-text">{item.name}</p>
                <p className="text-xs text-text-secondary">{item.role}</p>
              </div>
              <motion.button
                onClick={() => removeItem(item.id)}
                className="text-xs text-danger hover:text-danger/80 px-2 py-1 rounded cursor-pointer"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                Eliminar
              </motion.button>
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
    </Section>
  )
}

// ── 4. Push Navigation ───────────────────────────────────────
function PushNavDemo() {
  const [view, setView] = useState<'list' | 'detail'>('list')

  return (
    <Section title="4. Push Navigation" description="Navegacion tipo iOS — enter lento (400ms), exit rapido (200ms). Asimetria intencional.">
      <div className="relative h-48 bg-bg-subtle rounded-lg overflow-hidden">
        <AnimatePresence mode="wait">
          {view === 'list' ? (
            <motion.div
              key="list"
              className="absolute inset-0 p-4"
              initial={{ opacity: 0, x: '-30%' }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: '-30%' }}
              transition={transition.content}
            >
              <p className="text-sm font-medium text-text mb-3">Lista de cursos</p>
              {['Seguridad', 'Higiene', 'Prevencion'].map((c) => (
                <motion.div
                  key={c}
                  onClick={() => setView('detail')}
                  className="border border-border rounded-lg p-3 mb-2 bg-bg cursor-pointer text-sm text-text-secondary hover:border-primary"
                  whileHover={{ x: 4 }}
                  transition={transition.micro}
                >
                  {c} &rarr;
                </motion.div>
              ))}
            </motion.div>
          ) : (
            <motion.div
              key="detail"
              className="absolute inset-0 p-4"
              initial={{ opacity: 0, x: '100%' }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: '100%' }}
              transition={{
                x: view === 'detail' ? transition.pushIn : transition.pushOut,
                opacity: { duration: duration.fast },
              }}
            >
              <DemoButton onClick={() => setView('list')}>&larr; Volver</DemoButton>
              <div className="mt-4">
                <p className="text-sm font-medium text-text">Detalle del curso</p>
                <p className="text-xs text-text-secondary mt-1">Contenido expandido con mas informacion</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Section>
  )
}

// ── 5. Micro-interactions ────────────────────────────────────
function MicroInteractionsDemo() {
  const [active, setActive] = useState(0)

  return (
    <Section title="5. Micro-interactions" description="Botones con scale al hover/tap. Cards con elevacion. Nav pill con spring.">
      <div className="space-y-6">
        {/* Buttons */}
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Botones</p>
          <div className="flex gap-3">
            <motion.button
              className="bg-primary text-white text-sm font-medium px-4 py-2 rounded-lg cursor-pointer"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              transition={transition.micro}
            >
              Primary
            </motion.button>
            <motion.button
              className="border border-border text-sm font-medium px-4 py-2 rounded-lg cursor-pointer"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              transition={transition.micro}
            >
              Secondary
            </motion.button>
            <motion.button
              className="bg-accent text-white text-sm font-medium px-4 py-2 rounded-lg cursor-pointer"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              transition={transition.micro}
            >
              Accent
            </motion.button>
          </div>
        </div>

        {/* Cards hover */}
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Cards interactivas</p>
          <div className="grid grid-cols-3 gap-3">
            {['Curso A', 'Curso B', 'Curso C'].map((c) => (
              <motion.div
                key={c}
                className="border border-border rounded-xl p-4 cursor-pointer bg-bg"
                whileHover={{
                  scale: 1.02,
                  boxShadow: '0 8px 32px -8px rgba(0,0,0,0.12)',
                }}
                transition={{
                  scale: spring.default,
                  boxShadow: { duration: duration.normal, ease: ease.base },
                }}
              >
                <p className="text-sm font-medium text-text">{c}</p>
                <p className="text-xs text-text-secondary mt-1">Hover para ver elevacion</p>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Nav pill */}
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Nav indicator (spring)</p>
          <nav className="relative flex gap-1 bg-bg-subtle rounded-lg p-1">
            <motion.div
              className="absolute top-1 bottom-1 bg-primary rounded-md"
              layoutId="demo-nav-pill"
              transition={spring.stiff}
              style={{ width: `calc(${100 / 4}% - 4px)`, left: `calc(${active * 25}% + 2px)` }}
            />
            {['Inicio', 'Cursos', 'Skills', 'Chat'].map((label, i) => (
              <button
                key={label}
                onClick={() => setActive(i)}
                className={`relative z-10 flex-1 text-sm font-medium py-2 rounded-md transition-colors cursor-pointer ${
                  i === active ? 'text-white' : 'text-text-secondary hover:text-text'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </div>
    </Section>
  )
}

// ── 6. Wizard Steps ──────────────────────────────────────────
function WizardDemo() {
  const [step, setStep] = useState(0)
  const [dir, setDir] = useState<1 | -1>(1)
  const steps = ['Origen', 'Contenido', 'Generando', 'Revisar']
  const variants = slideVariants(80)

  function go(target: number) {
    setDir(target > step ? 1 : -1)
    setStep(target)
  }

  return (
    <Section title="6. Wizard Steps" description="Slide direccional con blur. Enter lento, exit rapido.">
      <div className="flex gap-2 mb-4">
        {steps.map((s, i) => (
          <DemoButton key={s} onClick={() => go(i)} active={step === i}>{s}</DemoButton>
        ))}
      </div>

      <div className="relative h-32 bg-bg-subtle rounded-lg overflow-hidden">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={step}
            custom={dir}
            variants={variants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{
              duration: duration.normal,
              ease: ease.base,
            }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <div className="text-center">
              <p className="text-lg font-semibold text-text">Paso {step + 1}: {steps[step]}</p>
              <p className="text-sm text-text-secondary mt-1">Contenido del paso</p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </Section>
  )
}

// ── 7. Sidebar Overlay ───────────────────────────────────────
function SidebarDemo() {
  const [open, setOpen] = useState(false)

  return (
    <Section title="7. Mobile Sidebar" description="Backdrop con backdrop-blur (no solo opacidad). Sidebar con spring physics.">
      <DemoButton onClick={() => setOpen(true)}>Abrir sidebar</DemoButton>

      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-50">
            <motion.div
              className="absolute inset-0 bg-black/10 backdrop-blur-sm"
              {...backdrop}
              onClick={() => setOpen(false)}
            />
            <motion.div
              className="absolute left-0 top-0 bottom-0 w-64 bg-bg border-r border-border shadow-lg p-6"
              {...sidebarSlide}
            >
              <p className="text-sm font-medium text-text mb-4">Sidebar</p>
              <div className="space-y-2">
                {['Inicio', 'Cursos', 'Skills', 'Chat', 'Ajustes'].map((item) => (
                  <div key={item} className="text-sm text-text-secondary px-3 py-2 rounded-lg hover:bg-bg-muted cursor-pointer">
                    {item}
                  </div>
                ))}
              </div>
              <div className="mt-8">
                <DemoButton onClick={() => setOpen(false)}>Cerrar</DemoButton>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </Section>
  )
}

// ── 8. Content Swap ──────────────────────────────────────────
function ContentSwapDemo() {
  const [lesson, setLesson] = useState(0)
  const lessons = ['Introduccion', 'Conceptos basicos', 'Practica', 'Evaluacion']

  return (
    <Section title="8. Content Swap" description="Cambio de leccion/tab con blur suave. Reemplaza el fade plano de CourseView.">
      <div className="flex gap-2 mb-4">
        {lessons.map((l, i) => (
          <DemoButton key={l} onClick={() => setLesson(i)} active={lesson === i}>{l}</DemoButton>
        ))}
      </div>

      <div className="relative h-32 bg-bg-subtle rounded-lg overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={lesson}
            className="absolute inset-0 flex items-center justify-center p-4"
            {...contentSwap}
          >
            <div className="text-center">
              <p className="text-base font-medium text-text">{lessons[lesson]}</p>
              <p className="text-sm text-text-secondary mt-2">
                Contenido de la leccion con blur al entrar y salir
              </p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </Section>
  )
}

// ── 9. Comparison ────────────────────────────────────────────
function ComparisonDemo() {
  const [key, setKey] = useState(0)

  return (
    <Section title="9. Antes vs Ahora" description="Comparacion directa del mismo patron.">
      <DemoButton onClick={() => setKey((k) => k + 1)}>Replay</DemoButton>

      <div className="grid grid-cols-2 gap-4 mt-4">
        {/* BEFORE */}
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Antes (fade plano)</p>
          <div className="relative h-28 bg-bg-subtle rounded-lg overflow-hidden">
            <AnimatePresence mode="wait">
              <motion.div
                key={`old-${key}`}
                className="absolute inset-0 flex items-center justify-center"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <p className="text-sm text-text-secondary">opacity + y:8, 0.2s</p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* AFTER */}
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Ahora (blur + scale)</p>
          <div className="relative h-28 bg-bg-subtle rounded-lg overflow-hidden">
            <AnimatePresence mode="wait">
              <motion.div
                key={`new-${key}`}
                className="absolute inset-0 flex items-center justify-center"
                {...pageTransition}
              >
                <p className="text-sm text-text-secondary">blur + scale, 0.5s, curva firma</p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </Section>
  )
}

// ── Main Page ────────────────────────────────────────────────
export function MotionDemo() {
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-text">Motion System</h1>
        <p className="text-sm text-text-secondary mt-1">
          Todos los patrones de animacion de SkillNet. Interactua con cada seccion.
        </p>
      </div>

      <PageTransitionDemo />
      <MorphModalDemo />
      <StaggeredListDemo />
      <PushNavDemo />
      <MicroInteractionsDemo />
      <WizardDemo />
      <SidebarDemo />
      <ContentSwapDemo />
      <ComparisonDemo />
    </div>
  )
}

import type { Meta } from '@storybook/react-vite'

const meta: Meta = {
  title: 'Style Explorer',
}
export default meta

// ============ BUTTONS ============

function ButtonRow({ label, className }: { label: string; className: string }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">{label}</p>
      <div className="flex items-center gap-3">
        <button className={`bg-primary text-white font-medium ${className}`}>Crear curso</button>
        <button className={`border border-border text-text font-medium ${className}`}>Cancelar</button>
        <button className={`bg-accent text-white font-medium ${className}`}>Completado</button>
        <button className={`bg-danger text-white font-medium ${className}`}>Eliminar</button>
      </div>
    </div>
  )
}

export const Buttons = () => (
  <div className="space-y-8 p-4">
    <h2 className="text-lg font-semibold text-text">Botones — Estilos visuales</h2>

    <ButtonRow
      label="A — Sharp (sin redondeo, bordes rectos)"
      className="px-4 py-2 text-sm rounded-none"
    />
    <ButtonRow
      label="B — Subtle (redondeo minimo)"
      className="px-4 py-2 text-sm rounded-sm"
    />
    <ButtonRow
      label="C — Standard (redondeo medio)"
      className="px-4 py-2 text-sm rounded-md"
    />
    <ButtonRow
      label="D — Soft (redondeo grande)"
      className="px-4 py-2 text-sm rounded-lg"
    />
    <ButtonRow
      label="E — Pill (completamente redondo)"
      className="px-5 py-2 text-sm rounded-full"
    />
    <ButtonRow
      label="F — Chunky (mas padding, mas presencia)"
      className="px-6 py-3 text-sm rounded-md"
    />
    <ButtonRow
      label="G — Compact (menos padding, mas denso)"
      className="px-3 py-1.5 text-xs rounded-md"
    />
    <ButtonRow
      label="H — Uppercase (identidad fuerte)"
      className="px-4 py-2 text-xs rounded-md uppercase tracking-wider"
    />
  </div>
)

// ============ CARDS ============

function CardSample({ label, className, innerClass = '' }: { label: string; className: string; innerClass?: string }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">{label}</p>
      <div className={`${className} max-w-sm`}>
        <h3 className={`font-medium text-text ${innerClass}`}>Devoluciones en tienda</h3>
        <p className="text-sm text-text-secondary mt-1">3 modulos, 12 ejercicios</p>
        <div className="mt-3 h-1.5 bg-bg-muted rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full" style={{ width: '40%' }} />
        </div>
        <p className="text-xs text-text-muted mt-2">Ultima sesion: ayer</p>
      </div>
    </div>
  )
}

export const Cards = () => (
  <div className="space-y-8 p-4">
    <h2 className="text-lg font-semibold text-text">Cards — Estilos visuales</h2>

    <CardSample
      label="A — Border only (limpio, sin sombra)"
      className="border border-border rounded-lg p-5"
    />
    <CardSample
      label="B — Shadow subtle (sin borde)"
      className="shadow-sm rounded-lg p-5"
    />
    <CardSample
      label="C — Filled (fondo gris, sin borde)"
      className="bg-bg-subtle rounded-lg p-5"
    />
    <CardSample
      label="D — Border + filled (borde con fondo)"
      className="border border-border bg-bg-subtle rounded-lg p-5"
    />
    <CardSample
      label="E — Left accent (linea de color izquierda)"
      className="border border-border rounded-lg p-5 border-l-4 border-l-primary"
    />
    <CardSample
      label="F — Top accent (linea de color arriba)"
      className="border border-border rounded-lg p-5 border-t-3 border-t-accent"
    />
    <CardSample
      label="G — Sharp (sin redondeo)"
      className="border border-border p-5"
    />
    <CardSample
      label="H — Outlined strong (borde grueso)"
      className="border-2 border-border-strong rounded-lg p-5"
    />
    <CardSample
      label="I — Minimal (solo padding, sin nada)"
      className="p-5"
      innerClass="text-base"
    />
  </div>
)

// ============ BADGES ============

function BadgeRow({ label, className }: { label: string; className: string }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">{label}</p>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-medium ${className} bg-accent-subtle text-accent`}>Alto</span>
        <span className={`text-xs font-medium ${className} bg-amber-50 text-amber-700`}>Medio</span>
        <span className={`text-xs font-medium ${className} bg-red-50 text-red-700`}>Bajo</span>
        <span className={`text-xs font-medium ${className} bg-primary-subtle text-primary`}>Asignado</span>
        <span className={`text-xs font-medium ${className} bg-bg-muted text-text-secondary`}>Borrador</span>
      </div>
    </div>
  )
}

export const Badges = () => (
  <div className="space-y-8 p-4">
    <h2 className="text-lg font-semibold text-text">Badges — Estilos visuales</h2>

    <BadgeRow label="A — Pill (redondo completo)" className="px-2 py-0.5 rounded-full" />
    <BadgeRow label="B — Rounded (redondeo medio)" className="px-2 py-0.5 rounded-md" />
    <BadgeRow label="C — Sharp (sin redondeo)" className="px-2 py-0.5 rounded-none" />
    <BadgeRow label="D — Pill grande (mas padding)" className="px-3 py-1 rounded-full" />
    <BadgeRow label="E — Uppercase (identidad fuerte)" className="px-2 py-0.5 rounded-full uppercase tracking-wider text-[10px]" />

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">F — Dot (punto de color + texto)</p>
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-text-secondary">
          <span className="w-2 h-2 rounded-full bg-accent" />Alto
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-text-secondary">
          <span className="w-2 h-2 rounded-full bg-warning" />Medio
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-text-secondary">
          <span className="w-2 h-2 rounded-full bg-danger" />Bajo
        </span>
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">G — Solid (fondo solido, texto blanco)</p>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-accent text-white">Alto</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-warning text-white">Medio</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-danger text-white">Bajo</span>
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">H — Outline (solo borde)</p>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-accent text-accent">Alto</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-warning text-warning">Medio</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-danger text-danger">Bajo</span>
      </div>
    </div>
  </div>
)

// ============ INPUTS ============

function InputSample({ label, className }: { label: string; className: string }) {
  return (
    <div className="space-y-2 max-w-sm">
      <p className="text-xs text-text-muted font-mono">{label}</p>
      <div className="space-y-1">
        <label className="block text-sm font-medium text-text">Email</label>
        <input
          className={`w-full px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none ${className}`}
          placeholder="laura@empresa.com"
        />
      </div>
    </div>
  )
}

export const Inputs = () => (
  <div className="space-y-8 p-4">
    <h2 className="text-lg font-semibold text-text">Inputs — Estilos visuales</h2>

    <InputSample
      label="A — Border standard"
      className="border border-border rounded-md focus:border-primary focus:ring-1 focus:ring-primary"
    />
    <InputSample
      label="B — Filled (fondo gris, sin borde)"
      className="bg-bg-muted rounded-md border border-transparent focus:bg-bg focus:border-primary focus:ring-1 focus:ring-primary"
    />
    <InputSample
      label="C — Underline only (linea abajo)"
      className="border-b border-border rounded-none focus:border-primary"
    />
    <InputSample
      label="D — Sharp border (sin redondeo)"
      className="border border-border rounded-none focus:border-primary focus:ring-1 focus:ring-primary"
    />
    <InputSample
      label="E — Thick border"
      className="border-2 border-border-strong rounded-md focus:border-primary focus:ring-0"
    />
    <InputSample
      label="F — Shadow focus (sombra en lugar de ring)"
      className="border border-border rounded-md focus:border-primary focus:shadow-md focus:shadow-primary/20"
    />
  </div>
)

// ============ PROGRESS ============

export const ProgressBars = () => (
  <div className="space-y-8 p-4 max-w-md">
    <h2 className="text-lg font-semibold text-text">Progress — Estilos visuales</h2>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">A — Thin (h-1)</p>
      <div className="h-1 bg-bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full" style={{ width: '60%' }} />
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">B — Medium (h-2)</p>
      <div className="h-2 bg-bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full" style={{ width: '60%' }} />
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">C — Thick (h-3)</p>
      <div className="h-3 bg-bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full" style={{ width: '60%' }} />
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">D — Sharp (sin redondeo)</p>
      <div className="h-2 bg-bg-muted overflow-hidden">
        <div className="h-full bg-primary" style={{ width: '60%' }} />
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">E — Accent color</p>
      <div className="h-2 bg-bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-accent rounded-full" style={{ width: '60%' }} />
      </div>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">F — Segmented (modulos como segmentos)</p>
      <div className="flex gap-1">
        <div className="h-2 flex-1 bg-accent rounded-full" />
        <div className="h-2 flex-1 bg-accent rounded-full" />
        <div className="h-2 flex-1 bg-primary rounded-full" />
        <div className="h-2 flex-1 bg-bg-muted rounded-full" />
        <div className="h-2 flex-1 bg-bg-muted rounded-full" />
      </div>
      <p className="text-xs text-text-secondary">Modulo 3 de 5</p>
    </div>

    <div className="space-y-2">
      <p className="text-xs text-text-muted font-mono">G — Con porcentaje inline</p>
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 bg-bg-muted rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full" style={{ width: '60%' }} />
        </div>
        <span className="text-xs font-medium text-text-secondary w-8">60%</span>
      </div>
    </div>
  </div>
)

// ============ COMBINED COURSE CARD ============

export const CourseCards = () => (
  <div className="space-y-8 p-4">
    <h2 className="text-lg font-semibold text-text">Course Card — Combinaciones</h2>

    <div className="grid grid-cols-2 gap-6 max-w-2xl">
      <div className="space-y-1">
        <p className="text-xs text-text-muted font-mono">A — Minimal border</p>
        <div className="border border-border rounded-lg p-5">
          <h3 className="text-sm font-medium text-text">Devoluciones en tienda</h3>
          <p className="text-xs text-text-secondary mt-1">Modulo 2 de 5</p>
          <div className="mt-3 h-1.5 bg-bg-muted rounded-full overflow-hidden">
            <div className="h-full bg-primary rounded-full" style={{ width: '40%' }} />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
              <span className="w-1.5 h-1.5 rounded-full bg-accent" />En progreso
            </span>
            <span className="text-xs text-text-muted">Ayer</span>
          </div>
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-xs text-text-muted font-mono">B — Left accent</p>
        <div className="border border-border border-l-4 border-l-primary rounded-lg p-5">
          <h3 className="text-sm font-medium text-text">Devoluciones en tienda</h3>
          <p className="text-xs text-text-secondary mt-1">Modulo 2 de 5</p>
          <div className="mt-3 flex gap-1">
            <div className="h-1.5 flex-1 bg-accent rounded-full" />
            <div className="h-1.5 flex-1 bg-primary rounded-full" />
            <div className="h-1.5 flex-1 bg-bg-muted rounded-full" />
            <div className="h-1.5 flex-1 bg-bg-muted rounded-full" />
            <div className="h-1.5 flex-1 bg-bg-muted rounded-full" />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary-subtle text-primary">En progreso</span>
            <span className="text-xs text-text-muted">Ayer</span>
          </div>
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-xs text-text-muted font-mono">C — Filled + shadow hover</p>
        <div className="bg-bg-subtle rounded-lg p-5 hover:shadow-sm transition-shadow cursor-pointer">
          <h3 className="text-sm font-medium text-text">Devoluciones en tienda</h3>
          <p className="text-xs text-text-secondary mt-1">Modulo 2 de 5</p>
          <div className="mt-3 h-2 bg-bg-muted rounded-full overflow-hidden">
            <div className="h-full bg-accent rounded-full" style={{ width: '40%' }} />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs font-medium text-accent">40%</span>
            <span className="text-xs text-text-muted">Ayer</span>
          </div>
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-xs text-text-muted font-mono">D — Sharp + top accent</p>
        <div className="border border-border border-t-3 border-t-accent p-5">
          <h3 className="text-sm font-medium text-text">Devoluciones en tienda</h3>
          <p className="text-xs text-text-secondary mt-1">Modulo 2 de 5 — 40%</p>
          <div className="mt-3 h-1 bg-bg-muted overflow-hidden">
            <div className="h-full bg-accent" style={{ width: '40%' }} />
          </div>
          <p className="text-xs text-text-muted mt-3">Ultima sesion: ayer</p>
        </div>
      </div>
    </div>
  </div>
)

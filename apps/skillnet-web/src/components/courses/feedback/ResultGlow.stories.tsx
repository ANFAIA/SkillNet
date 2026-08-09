import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Meta } from '@storybook/react-vite'
import { ResultGlow } from './ResultGlow'
import type {
  Resultado,
  ResultGlowAltura,
  ResultGlowIntensidad,
  ResultGlowVariante,
} from './ResultGlow'
import { declaredReducedMotionContext } from '../../../hooks/useReducedMotion'

/**
 * ResultGlow — pantalla de decisión.
 *
 * No es una demo de un caso: es todo lo que hay que mirar a la vez para decidir si la
 * idea funciona. Cada marco es una lección falsa con el mismo texto, para que lo único
 * que cambie entre dos marcos sea lo que se está comparando.
 *
 * Como el degradado se queda 1,6 s y se va, cada marco lleva su propio botón
 * **Repetir**: sin él la story sería una captura en negro. Los marcos empiezan
 * mostrados y quietos (`duracionMs={null}`) para poder comparar tonos con calma; al
 * pulsar Repetir se ve la animación real, con su entrada, su vibración y su salida.
 */
const meta: Meta<typeof ResultGlow> = {
  title: 'Courses/Feedback/ResultGlow',
  component: ResultGlow,
  parameters: { a11y: { test: 'error' }, layout: 'fullscreen' },
}
export default meta

// ── Andamiaje de la story ────────────────────────────────────

/** Texto de ejercicio de mentira. Igual en todos los marcos: la variable es el brillo. */
function LeccionFalsa() {
  return (
    <div className="p-5 space-y-3">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Ejercicio 3 de 8</p>
      <p className="text-sm text-text">Ordena los pasos del arranque en frío de la línea 2.</p>
      <ol className="text-sm text-text-secondary space-y-1.5 list-decimal pl-5">
        <li>Purgar el circuito</li>
        <li>Precalentar a 60 °C</li>
        <li>Abrir la válvula de entrada</li>
        <li>Registrar la lectura inicial</li>
      </ol>
    </div>
  )
}

interface MarcoProps {
  titulo: string
  nota?: string
  children: (intento: number) => ReactNode
}

/**
 * Un contenedor posicionado con el aspecto de la superficie real (blanca, redondeada)
 * y el botón de repetir. `posicion="contenida"` del componente se ancla a este marco,
 * que es lo que permite ver seis a la vez en una pantalla.
 */
function Marco({ titulo, nota, children }: MarcoProps) {
  const [intento, setIntento] = useState(0)

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-text">{titulo}</h3>
        <button
          type="button"
          className="text-xs font-medium text-primary hover:text-primary/80 transition-colors"
          onClick={() => setIntento((n) => n + 1)}
        >
          Repetir
        </button>
      </div>
      <div className="relative overflow-hidden rounded-xl border border-border bg-bg h-64">
        <LeccionFalsa />
        {children(intento)}
      </div>
      {nota && <p className="text-xs text-text-secondary leading-snug">{nota}</p>}
    </div>
  )
}

function Rejilla({ children, cols = 3 }: { children: ReactNode; cols?: 2 | 3 }) {
  return (
    <div className={`grid gap-6 ${cols === 2 ? 'md:grid-cols-2' : 'md:grid-cols-3'} p-6`}>
      {children}
    </div>
  )
}

// ── 1. Los tres estados ──────────────────────────────────────

/**
 * El caso central. Verde pleno / verde a media fuerza / ámbar.
 *
 * Lo que hay que juzgar aquí: ¿se distingue `parcial` de `acierto` sin leer la palabra?
 * Comparten tono a propósito (mismo camino, más corto) y se separan por opacidad y
 * altura. Si a esta distancia parecen el mismo estado, la decisión es subir la
 * diferencia de altura, no cambiarle el color.
 */
export const TresEstados = () => (
  <Rejilla>
    <Marco
      titulo="acierto"
      nota="Verde de marca (--color-accent), altura e intensidad plenas. Respira hacia arriba una vez."
    >
      {(intento) => (
        <ResultGlow resultado="acierto" intento={intento} posicion="contenida" duracionMs={null} />
      )}
    </Marco>
    <Marco
      titulo="parcial"
      nota="Mismo verde al 50 % de opacidad y al 70 % de altura. 3 de 4 es el mismo camino, más corto: el tono dice la dirección, la cantidad dice cuánto falta."
    >
      {(intento) => (
        <ResultGlow resultado="parcial" intento={intento} posicion="contenida" duracionMs={null} />
      )}
    </Marco>
    <Marco
      titulo="fallo"
      nota="Ámbar (--color-warning) y flecha de reintentar. El rojo queda para lo irreversible."
    >
      {(intento) => (
        <ResultGlow resultado="fallo" intento={intento} posicion="contenida" duracionMs={null} />
      )}
    </Marco>
  </Rejilla>
)

// ── 2. Ámbar contra rojo ─────────────────────────────────────

/**
 * La comparación que decide el punto 1 de la cabecera del componente: el mismo fallo,
 * pintado como "todavía no" y como "se acabó".
 *
 * El de la derecha solo aparece con `definitivo`, y `definitivo` solo debería ser cierto
 * cuando de verdad no hay reintento. Puestos uno al lado del otro se ve por qué no
 * pueden ser el mismo color: el rojo cierra la puerta, y en un ejercicio la puerta no
 * está cerrada.
 */
export const AmbarContraRojo = () => (
  <Rejilla cols={2}>
    <Marco
      titulo="fallo (ámbar) — hay reintento"
      nota="Lo que ve el aprendiz el 99 % de las veces. Icono de flecha circular: la acción siguiente es volver a intentarlo."
    >
      {(intento) => (
        <ResultGlow resultado="fallo" intento={intento} posicion="contenida" duracionMs={null} />
      )}
    </Marco>
    <Marco
      titulo="fallo definitivo (rojo) — sin reintento"
      nota="--color-danger, el mismo rojo que un error de red o un borrado. Reservado a último intento consumido o entrega evaluada. Icono de cruz."
    >
      {(intento) => (
        <ResultGlow
          resultado="fallo"
          definitivo
          intento={intento}
          posicion="contenida"
          duracionMs={null}
        />
      )}
    </Marco>
  </Rejilla>
)

// ── 3. Movimiento reducido ───────────────────────────────────

/**
 * Con movimiento reducido, forzado por contexto.
 *
 * `declaredReducedMotionContext` es la mitad "declarada" del hook (la casilla del
 * wizard), así que la story puede enseñar este estado sin tocar el ajuste del sistema
 * operativo. En la app real la preferencia del SO llega por el mismo hook.
 *
 * Aparece con un fundido, **no vibra** y **no se va**: se queda hasta que el ejercicio
 * cambie de estado. Pulsar Repetir aquí no debería producir ningún salto — si algo se
 * mueve, es un defecto.
 */
export const MovimientoReducido = () => (
  <declaredReducedMotionContext.Provider value={true}>
    <Rejilla>
      {(['acierto', 'parcial', 'fallo'] as Resultado[]).map((r) => (
        <Marco key={r} titulo={`${r} · sin movimiento`}>
          {(intento) => <ResultGlow resultado={r} intento={intento} posicion="contenida" />}
        </Marco>
      ))}
    </Rejilla>
  </declaredReducedMotionContext.Provider>
)

// ── 4. Intensidad ────────────────────────────────────────────

/**
 * Las tres intensidades sobre `acierto`, que es el tono más luminoso y por tanto el que
 * antes se pasa de rosca.
 *
 * `media` es el valor por defecto. `plena` es defendible para el final de un nodo;
 * `sutil` para respuestas que se repiten mucho dentro del mismo ejercicio, donde el
 * brillo pleno cansa a la tercera.
 */
export const Intensidades = () => (
  <Rejilla>
    {(['sutil', 'media', 'plena'] as ResultGlowIntensidad[]).map((i) => (
      <Marco key={i} titulo={`intensidad: ${i}`}>
        {(intento) => (
          <ResultGlow
            resultado="acierto"
            intensidad={i}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
    ))}
  </Rejilla>
)

// ── 5. Altura ────────────────────────────────────────────────

/**
 * Las tres alturas sobre `fallo`. Cuanta más altura, más de la lección queda teñida —
 * y el texto del ejercicio es justo lo que el aprendiz tiene que releer para corregir.
 * `alta` con `plena` es la combinación que hay que mirar con más desconfianza.
 */
export const Alturas = () => (
  <Rejilla>
    {(['baja', 'media', 'alta'] as ResultGlowAltura[]).map((a) => (
      <Marco key={a} titulo={`altura: ${a}`}>
        {(intento) => (
          <ResultGlow
            resultado="fallo"
            altura={a}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
    ))}
  </Rejilla>
)

// ── 6. Variantes de forma ────────────────────────────────────

/**
 * Tres maneras de decir lo mismo. Verlas juntas vale más que un párrafo defendiendo una.
 *
 * - **gradiente** — la idea original. Ambiental, no tapa nada, se disuelve. Se pierde
 *   sobre fondos oscuros (un bloque de código a pantalla completa).
 * - **borde** — regla inferior sólida más un halo corto. Sobrevive a cualquier fondo y
 *   ocupa un tercio de la pantalla; a cambio se parece a la validación de un formulario,
 *   que es exactamente el registro escolar del que el degradado escapaba.
 * - **tinte** — baña la lección entera. Imposible de ignorar, y ese es el problema:
 *   tiñe el texto que hay que releer para corregir.
 *
 * Con el mismo resultado en los tres para que la única variable sea la forma.
 */
export const Variantes = () => (
  <Rejilla>
    {(
      [
        ['gradiente', 'La idea original: luz que sube del borde y se disuelve.'],
        ['borde', 'Regla sólida + halo. Legible sobre cualquier fondo, más "formulario".'],
        ['tinte', 'Baño sobre toda la lección. El más fuerte y el que más estorba al leer.'],
      ] as [ResultGlowVariante, string][]
    ).map(([v, nota]) => (
      <Marco key={v} titulo={`variante: ${v}`} nota={nota}>
        {(intento) => (
          <ResultGlow
            resultado="acierto"
            variante={v}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
    ))}
  </Rejilla>
)

/** Las mismas tres formas con `fallo`: el ámbar tiñe distinto que el verde. */
export const VariantesEnFallo = () => (
  <Rejilla>
    {(['gradiente', 'borde', 'tinte'] as ResultGlowVariante[]).map((v) => (
      <Marco key={v} titulo={`fallo · ${v}`}>
        {(intento) => (
          <ResultGlow
            resultado="fallo"
            variante={v}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
    ))}
  </Rejilla>
)

// ── 7. Sin color ─────────────────────────────────────────────

/**
 * Lo que ve alguien con deuteranopía, simulado con un filtro sobre el marco.
 *
 * Verde y ámbar se convierten en dos ocres casi iguales. Lo único que sigue separando
 * los tres estados es el icono y la palabra — por eso `mostrarEtiqueta` viene en `true`
 * y apagarlo tiene que ser una decisión consciente.
 *
 * El cuarto marco es ese mismo apagado: sirve para ver que, sin etiqueta, el componente
 * no comunica nada a quien no distingue los tonos.
 */
export const SinDistinguirColor = () => (
  <div
    // Aproximación de deuteranopía; solo para mirar, no forma parte del componente.
    style={{
      filter:
        'url("data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\'><filter id=\'d\'><feColorMatrix type=\'matrix\' values=\'0.625 0.375 0 0 0 0.7 0.3 0 0 0 0 0.3 0.7 0 0 0 0 0 1 0\'/></filter></svg>#d")',
    }}
  >
    <Rejilla>
      {(['acierto', 'parcial', 'fallo'] as Resultado[]).map((r) => (
        <Marco key={r} titulo={`${r} · visión deutan`}>
          {(intento) => (
            <ResultGlow resultado={r} intento={intento} posicion="contenida" duracionMs={null} />
          )}
        </Marco>
      ))}
      <Marco
        titulo="acierto · sin etiqueta"
        nota="mostrarEtiqueta={false}: solo el tono. Compáralo con el fallo sin etiqueta de al lado — son el mismo gris."
      >
        {(intento) => (
          <ResultGlow
            resultado="acierto"
            mostrarEtiqueta={false}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
      <Marco titulo="fallo · sin etiqueta">
        {(intento) => (
          <ResultGlow
            resultado="fallo"
            mostrarEtiqueta={false}
            intento={intento}
            posicion="contenida"
            duracionMs={null}
          />
        )}
      </Marco>
    </Rejilla>
  </div>
)

// ── 8. A tamaño real ─────────────────────────────────────────

/**
 * `posicion="fija"`, que es el valor por defecto y el único que se comporta como en la
 * app: anclado al borde inferior de la ventana, con el temporizador de 1,6 s corriendo.
 *
 * Es la única story donde se ve la duración real y la salida. Pulsa los tres botones
 * seguidos para comprobar que un resultado nuevo reemplaza al anterior sin parpadeo, y
 * el mismo botón dos veces para ver que `intento` vuelve a disparar la animación.
 */
export const APantallaCompleta = () => {
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [definitivo, setDefinitivo] = useState(false)
  const [intento, setIntento] = useState(0)

  function disparar(r: Resultado, esDefinitivo = false) {
    setResultado(r)
    setDefinitivo(esDefinitivo)
    setIntento((n) => n + 1)
  }

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-xl mx-auto rounded-xl border border-border bg-bg">
        <LeccionFalsa />
        <div className="flex flex-wrap gap-2 border-t border-border p-4">
          {(['acierto', 'parcial', 'fallo'] as Resultado[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => disparar(r)}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-primary transition-colors"
            >
              {r}
            </button>
          ))}
          <button
            type="button"
            onClick={() => disparar('fallo', true)}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-primary transition-colors"
          >
            fallo definitivo
          </button>
        </div>
      </div>

      <ResultGlow
        resultado={resultado}
        definitivo={definitivo}
        intento={intento}
        onFin={() => setResultado(null)}
        altura="alta"
      />
    </div>
  )
}

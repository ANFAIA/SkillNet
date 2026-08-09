import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'
import { useReducedMotion } from '../../../hooks/useReducedMotion'

/**
 * ResultGlow — el resultado de un ejercicio, dicho con luz en el borde inferior.
 *
 * Aparece por abajo, vibra una vez, se va. No ocupa layout, no roba el foco y no
 * bloquea el puntero: es una respuesta ambiental, del mismo orden que el sonido que
 * hace un botón al pulsarse, no un cartel que hay que cerrar.
 *
 * ## Independiente del ejercicio
 *
 * Recibe `resultado` y nada más. No sabe si venía de un quiz, de un arrastrar-ordenar
 * o de una caja de código, no importa un tipo de bloque y no lee ningún store — por eso
 * vive en `feedback/` y no en `blocks/`. Cualquier bloque puede montarlo pasándole una
 * de tres palabras; ninguno tiene que saber cómo se pinta.
 *
 * ## Por qué no hay verde/rojo y ya
 *
 * Tres decisiones de color, y las tres son sobre lo mismo: **qué le dice el color al
 * aprendiz sobre lo que puede hacer a continuación.**
 *
 * 1. **`fallo` es ámbar, no rojo.** El rojo del sistema (`--color-danger`) es el color
 *    de "esto se ha roto" y de "esto ya no tiene vuelta": errores de red, borrados.
 *    Un ejercicio fallado no es ninguna de las dos cosas — el aprendiz puede reintentar
 *    ahora mismo, y el fallo es literalmente el mecanismo por el que el tutor baja la
 *    dificultad. Pintarlo del mismo color que un 500 le enseña a temer el botón de
 *    enviar. `--color-warning` dice "todavía no", que es lo que de verdad ha pasado.
 *    El icono acompaña: una flecha circular (reintenta), no una cruz (se acabó).
 *
 *    El rojo no desaparece del componente, se **reserva**: `definitivo` lo saca para
 *    el caso en que de verdad no hay reintento (último intento consumido, entrega
 *    evaluada). Un color que solo se usa cuando importa conserva su significado.
 *
 * 2. **`parcial` es el verde de `acierto`, a media fuerza.** 3 de 4 bien no es un
 *    estado tercero e independiente: es el mismo camino, más corto.
 *    - Ponerlo en el ámbar de `fallo` haría que "3 de 4" y "0 de 4" se vieran igual,
 *      que es exactamente lo único que `parcial` existe para evitar.
 *    - Ponerlo en verde pleno haría que "casi" se viera como "hecho", y el aprendiz
 *      pasaría de pantalla sin mirar qué le faltó.
 *    - Un cuarto tono propio (azul, violeta) obligaría a aprenderse un código de
 *      colores nuevo para un estado que aparece una vez de cada diez.
 *
 *    Así que **el tono dice la dirección y la cantidad dice cuánto**: mismo verde,
 *    la mitad de opacidad y un 70 % de altura. Se lee "vas por ahí, falta un trozo"
 *    sin que haya que explicarlo.
 *
 * 3. **Nunca solo color.** Todos los tonos llevan icono + palabra por defecto
 *    (`Correcto` / `Casi` / `Todavía no` / `Incorrecto`). Para alguien con deuteranopía
 *    el verde y el ámbar son dos grises casi idénticos; con `mostrarEtiqueta` a `false`
 *    este componente no comunicaría absolutamente nada, así que el valor por defecto
 *    es `true` y quitarlo tiene que ser una decisión explícita de quien lo monta.
 *    El texto va además en `role="status"`, de modo que quien no ve el degradado lo
 *    oye igual.
 *
 * ## Movimiento
 *
 * Con `useReducedMotion()` activo (preferencia del SO **o** la casilla del wizard) el
 * degradado aparece con un fundido, no vibra y **no se va solo**: si has renunciado al
 * movimiento, un aviso de 1,6 s que se desvanece es un aviso que te puedes perder.
 * Se queda hasta que el padre cambie `resultado` a `null`.
 *
 * Duraciones y curvas salen de `lib/motion.ts`; los colores, de los tokens de
 * `index.css`. No hay ni un hex ni un `0.3` en este fichero.
 */

export type Resultado = 'acierto' | 'fallo' | 'parcial'

/**
 * Las tres formas de pintarlo. `gradiente` es la idea original; las otras dos están
 * aquí para poder compararlas en la story antes de decidir (ver ResultGlow.stories).
 */
export type ResultGlowVariante = 'gradiente' | 'borde' | 'tinte'

export type ResultGlowIntensidad = 'sutil' | 'media' | 'plena'

export type ResultGlowAltura = 'baja' | 'media' | 'alta'

export interface ResultGlowProps {
  /** Qué ha pasado. `null` = nada que decir; el degradado sale de pantalla. */
  resultado: Resultado | null
  /**
   * Sube este número para volver a disparar la animación con el **mismo** resultado.
   * Sin él, fallar dos veces seguidas no produciría ninguna respuesta visible.
   */
  intento?: number
  /**
   * Solo para `fallo`: no queda reintento (último intento, entrega evaluada). Saca el
   * rojo `--color-danger` y la cruz. Sin esto, fallar siempre es ámbar.
   */
  definitivo?: boolean
  /** Sustituye la palabra por defecto ("Correcto" / "Casi" / "Todavía no"). */
  etiqueta?: string
  /** Sustituye el icono por defecto. */
  icono?: ReactNode
  /** Icono + palabra. Apágalo solo si el bloque ya dice el resultado con texto propio. */
  mostrarEtiqueta?: boolean
  variante?: ResultGlowVariante
  intensidad?: ResultGlowIntensidad
  altura?: ResultGlowAltura
  /**
   * Milisegundos visible antes de irse. `null` = se queda hasta que `resultado` sea
   * `null`. Con movimiento reducido se ignora y siempre se queda.
   */
  duracionMs?: number | null
  /**
   * `fija` (por defecto) se ancla al borde inferior de la ventana. `contenida` se ancla
   * al padre posicionado más cercano — para las stories y para lecciones dentro de un
   * panel, donde el borde de la ventana no es el borde del ejercicio.
   */
  posicion?: 'fija' | 'contenida'
  /** Se llama cuando ha terminado de salir. */
  onFin?: () => void
  className?: string
}

/**
 * Cuánto se queda antes de irse solo.
 *
 * 1,6 s: por encima de `duration.morphSlow` (una animación larga del sistema, 1 s) para
 * que no compita con la propia transición del bloque al estado resuelto, y por debajo de
 * los ~2 s a los que una luz de colores en el borde de la pantalla deja de ser una
 * respuesta y empieza a ser decoración.
 */
const VISIBLE_MS = 1600

// ── Tonos ────────────────────────────────────────────────────
// `alpha` es la opacidad del degradado en su punto más bajo, en % para color-mix.
// `factorAltura` recorta la altura pedida — es la mitad de cómo `parcial` se distingue
// de `acierto` compartiendo el mismo verde.

type ClaveTono = 'acierto' | 'parcial' | 'fallo' | 'definitivo'

interface Tono {
  /** Token de color, siempre var() — nunca un hex. */
  color: string
  /** Clase Tailwind del mismo token, para el texto y el icono de la etiqueta. */
  claseTexto: string
  palabra: string
  alpha: number
  factorAltura: number
}

const TONOS: Record<ClaveTono, Tono> = {
  acierto: {
    color: 'var(--color-accent)',
    claseTexto: 'text-accent',
    palabra: 'Correcto',
    alpha: 1,
    factorAltura: 1,
  },
  // Mismo verde que `acierto`, la mitad de fuerza y 70 % de altura. Ver el bloque 2
  // de la cabecera: el tono dice la dirección, la cantidad dice cuánto falta.
  parcial: {
    color: 'var(--color-accent)',
    claseTexto: 'text-accent',
    palabra: 'Casi',
    alpha: 0.5,
    factorAltura: 0.7,
  },
  // Ámbar, no rojo: "todavía no", no "se acabó".
  fallo: {
    color: 'var(--color-warning)',
    claseTexto: 'text-warning',
    palabra: 'Todavía no',
    alpha: 0.85,
    factorAltura: 0.9,
  },
  // El rojo del sistema, reservado para cuando de verdad no hay reintento.
  definitivo: {
    color: 'var(--color-danger)',
    claseTexto: 'text-danger',
    palabra: 'Incorrecto',
    alpha: 1,
    factorAltura: 1,
  },
}

/** Opacidad base del degradado en su punto más bajo, en % para `color-mix`. */
const INTENSIDADES: Record<ResultGlowIntensidad, number> = {
  sutil: 26,
  media: 46,
  plena: 70,
}

const ALTURAS: Record<ResultGlowAltura, number> = {
  baja: 96,
  media: 160,
  alta: 232,
}

// ── Iconos ───────────────────────────────────────────────────
// SVG en línea al estilo de CalloutBlock: el proyecto no tiene librería de iconos.

function IconoTono({ clave }: { clave: ClaveTono }) {
  const cls = 'shrink-0 w-4 h-4'
  switch (clave) {
    case 'acierto':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
            clipRule="evenodd"
          />
        </svg>
      )
    case 'parcial':
      // Círculo medio lleno: la forma dice "una parte", no hace falta leer el porcentaje.
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M10 2a8 8 0 100 16 8 8 0 000-16zm0 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13z"
            clipRule="evenodd"
          />
          <path d="M10 5a5 5 0 010 10V5z" />
        </svg>
      )
    case 'fallo':
      // Flecha circular = reintenta. Una cruz aquí diría "se acabó", que es falso.
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
            clipRule="evenodd"
          />
        </svg>
      )
    case 'definitivo':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
            clipRule="evenodd"
          />
        </svg>
      )
  }
}

// ── Pintado ──────────────────────────────────────────────────

/** `color-mix` en lugar de un hex con alfa: el token sigue siendo la única fuente. */
function mezcla(color: string, porcentaje: number) {
  return `color-mix(in oklab, ${color} ${Math.round(porcentaje)}%, transparent)`
}

function estiloCapa(
  variante: ResultGlowVariante,
  tono: Tono,
  alturaPx: number,
  alphaBase: number,
): CSSProperties {
  const a = alphaBase * tono.alpha

  switch (variante) {
    // La idea original: luz que sube desde el borde y se disuelve.
    case 'gradiente':
      return {
        height: alturaPx,
        background: `linear-gradient(to top, ${mezcla(tono.color, a)} 0%, ${mezcla(
          tono.color,
          a * 0.34,
        )} 42%, transparent 100%)`,
      }

    // Regla inferior sólida + un halo corto. Ocupa mucho menos pantalla y sobrevive
    // sobre cualquier fondo, incluido un bloque de código oscuro donde el degradado
    // se pierde. A cambio se parece más a un borde de validación de formulario.
    case 'borde':
      return {
        height: Math.max(40, alturaPx * 0.34),
        borderBottom: `3px solid ${mezcla(tono.color, Math.min(100, a * 1.6))}`,
        background: `linear-gradient(to top, ${mezcla(tono.color, a * 0.55)} 0%, transparent 100%)`,
      }

    // Baño plano sobre toda la superficie del contenedor. Tiñe el propio ejercicio,
    // que es más difícil de ignorar — y también más difícil de leer por encima.
    case 'tinte':
      return {
        top: 0,
        height: 'auto',
        background: `linear-gradient(to top, ${mezcla(tono.color, a * 0.42)} 0%, ${mezcla(
          tono.color,
          a * 0.16,
        )} 100%)`,
      }
  }
}

export function ResultGlow({
  resultado,
  intento = 0,
  definitivo = false,
  etiqueta,
  icono,
  mostrarEtiqueta = true,
  variante = 'gradiente',
  intensidad = 'media',
  altura = 'media',
  duracionMs = VISIBLE_MS,
  posicion = 'fija',
  onFin,
  className,
}: ResultGlowProps) {
  const sinMovimiento = useReducedMotion()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (resultado === null) {
      setVisible(false)
      return
    }
    setVisible(true)
    // Sin movimiento no hay salida automática: quien renunció a las animaciones no
    // debería tener que cazar un aviso de 1,6 s.
    if (sinMovimiento || duracionMs === null) return
    const t = window.setTimeout(() => setVisible(false), duracionMs)
    return () => window.clearTimeout(t)
  }, [resultado, intento, duracionMs, sinMovimiento])

  const clave: ClaveTono =
    resultado === null
      ? 'acierto'
      : resultado === 'fallo' && definitivo
        ? 'definitivo'
        : resultado
  const tono = TONOS[clave]
  const alturaPx = ALTURAS[altura] * tono.factorAltura
  const alphaBase = INTENSIDADES[intensidad]

  // La vibración. `acierto`/`parcial` respiran hacia arriba (crece y vuelve); `fallo`
  // tiembla en horizontal. Ambos van sobre la capa del degradado y **no** sobre la
  // etiqueta: una palabra que tirita se lee peor, y lo que vibra es la luz.
  const vibracion = sinMovimiento
    ? {}
    : clave === 'fallo' || clave === 'definitivo'
      ? { x: [0, -5, 5, -3, 3, 0] }
      : { scaleY: [1, clave === 'parcial' ? 1.05 : 1.09, 1] }

  return (
    <AnimatePresence onExitComplete={onFin}>
      {visible && resultado !== null && (
        <motion.div
          // La clave incluye `intento`, así que dos fallos seguidos remontan el nodo
          // y la animación vuelve a correr en vez de quedarse quieta.
          key={`${clave}-${intento}`}
          data-testid="result-glow"
          data-resultado={resultado}
          data-tono={clave}
          aria-hidden={mostrarEtiqueta ? undefined : true}
          className={[
            posicion === 'fija' ? 'fixed' : 'absolute',
            'inset-x-0 bottom-0 z-40 pointer-events-none select-none',
            'flex items-end justify-center overflow-hidden',
            className ?? '',
          ]
            .filter(Boolean)
            .join(' ')}
          style={{ height: variante === 'tinte' ? '100%' : alturaPx }}
          initial={sinMovimiento ? { opacity: 0 } : { opacity: 0, y: 24 }}
          animate={sinMovimiento ? { opacity: 1 } : { opacity: 1, y: 0 }}
          exit={sinMovimiento ? { opacity: 0 } : { opacity: 0, y: 16 }}
          transition={{
            opacity: { duration: duration.fast, ease: ease.base },
            y: { duration: duration.normal, ease: ease.base },
          }}
        >
          <motion.div
            aria-hidden="true"
            className="absolute inset-x-0 bottom-0"
            style={{
              ...estiloCapa(variante, tono, alturaPx, alphaBase),
              transformOrigin: 'bottom',
            }}
            animate={vibracion}
            transition={{
              // Arranca cuando el degradado ya está a la vista, si no la vibración se
              // come la entrada y solo se ve un borrón.
              x: { duration: duration.medium, ease: ease.base, delay: duration.fast },
              scaleY: { duration: duration.slow, ease: ease.base, delay: duration.fast },
            }}
          />

          {mostrarEtiqueta && (
            <p
              role="status"
              className={[
                'relative mb-5 inline-flex items-center gap-1.5 rounded-full',
                'bg-bg/85 px-3 py-1.5 text-sm font-semibold',
                // El pill opaco es lo que mantiene el texto legible sobre el degradado
                // a intensidad `plena`; sin él el contraste depende del tono.
                'shadow-sm ring-1 ring-border',
                tono.claseTexto,
              ].join(' ')}
            >
              {icono ?? <IconoTono clave={clave} />}
              {etiqueta ?? tono.palabra}
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

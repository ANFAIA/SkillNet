import { useId } from 'react'
import { motion } from 'framer-motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'

/**
 * SkillNet brand mascot — the green "seed head" with the white eye-mask.
 *
 * A faithful React/framer-motion port of the rigged brand SVG
 * (`01_Mascota/mascota-base-vector.svg`, viewBox 0 0 512 512) plus the
 * **ojos-feliz** animation beat (`animaciones/ojos-feliz`): the open navy eyes
 * pop into happy upward smile arcs (^^) by ~0.8s, hold, then return — a calm
 * ~3.2s loop that "keeps moving" (never fully static), per the animation spec.
 *
 *   <Mascota />                    // idle: the happy-pop loops gently
 *   <Mascota expression="happy" /> // hold the smiling eyes (float only)
 *   <Mascota size={220} />
 *
 * Design notes
 * - Only `transform`/`opacity` animate (GPU-cheap); no layout, no filters.
 * - Full-colour brand mascot (green shell / white mask / navy eyes). It reads on
 *   both the light mint and the dark grounds, so the palette is intentionally
 *   fixed rather than themed.
 * - `prefers-reduced-motion` (OS or declared): renders the static happy face,
 *   no float and no loop.
 *
 * The whole timeline is expressed as keyframe arrays over one normalised 3.2s
 * loop. Times are the GSAP source cues divided by 3.2. Left/right pupils mirror
 * on the x drift; everything else is shared.
 */

// Brand palette — fixed, from the kit.
const SHELL = '#36b982'
const BAND = '#08764d'
const MASK_RIM = '#08764d'
const WHITE = '#ffffff'
const PUPIL = '#071c3f'

const LOOP = 3.2

// GSAP cue seconds → normalised fractions of the 3.2s loop.
const s = (sec: number) => sec / LOOP

// Pupil control keyframe cues (shared times for every pupil property).
const PUPIL_TIMES = [0, s(0.12), s(0.34), s(0.45), s(0.55), s(0.58), s(2.52), s(2.9), 1]
const PUPIL_SCALE_X = [1, 1.035, 1, 1.12, 1.12, 1.12, 1.12, 1, 1]
const PUPIL_SCALE_Y = [1, 1, 1, 0.2, 0.2, 0.2, 0.2, 1, 1]
const PUPIL_OPACITY = [1, 1, 1, 1, 1, 0, 0, 1, 1]
const PUPIL_DRIFT = 2.5 // px, toward centre then back

// Happy smile-arc cues.
const HAPPY_TIMES = [0, s(0.55), s(0.78), s(2.45), s(2.63), 1]
const HAPPY_OPACITY = [0, 0, 1, 1, 0, 0]
const HAPPY_SCALE = [0.72, 0.72, 1, 1, 0.72, 0.72]

// Head bob (part of the pop beat).
const HEAD_TIMES = [0, s(0.12), s(0.34), s(0.54), s(0.9), s(1.6), s(2.3), 1]
const HEAD_Y = [0, 0, -2, 0, 0, -1.5, 0, 0]

const loopTransition = (times: number[]) => ({
  duration: LOOP,
  times,
  repeat: Infinity,
  ease: 'easeInOut' as const,
})

export type MascotExpression = 'idle' | 'happy'

export interface MascotaProps {
  /** Rendered width & height in px (square). */
  size?: number
  /**
   * `idle` (default) loops the happy-pop beat; `happy` holds the smiling eyes.
   * Both float gently. Under reduced motion both render the static happy face.
   */
  expression?: MascotExpression
  className?: string
  /** Overrides the default aria-label. */
  ariaLabel?: string
}

export function Mascota({
  size = 180,
  expression = 'idle',
  className = '',
  ariaLabel = 'Mascota de SkillNet',
}: MascotaProps) {
  const reduce = useReducedMotion()
  const uid = useId().replace(/:/g, '')
  const id = (name: string) => `${name}-${uid}`

  // Static: reduced motion OR the caller pinned "happy". Show the smile arcs,
  // hide the round pupils, no loop.
  const staticHappy = reduce || expression === 'happy'

  // The outer gentle float (idle life). Skipped entirely under reduced motion.
  const floatAnimate = reduce
    ? undefined
    : { y: [0, -6, 0], rotate: [0, 0.8, 0, -0.8, 0] }
  const floatTransition = { duration: 4, repeat: Infinity, ease: 'easeInOut' as const }

  // Pupil animation: only when we run the live idle loop.
  const runLoop = !staticHappy
  const originStyle = (cx: number, cy: number) =>
    ({ transformBox: 'fill-box', transformOrigin: `${cx}px ${cy}px` }) as const

  return (
    <motion.div
      className={className}
      style={{ width: size, height: size, lineHeight: 0 }}
      animate={floatAnimate}
      transition={floatTransition}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 512 512"
        width={size}
        height={size}
        role="img"
        aria-label={ariaLabel}
        style={{ display: 'block', overflow: 'visible' }}
      >
        <defs>
          <clipPath id={id('shell-clip')} clipPathUnits="userSpaceOnUse">
            <use href={`#${id('head-shell')}`} />
          </clipPath>
          <clipPath id={id('eye-left-safe')} clipPathUnits="userSpaceOnUse">
            <ellipse cx="176" cy="276" rx="44" ry="56" />
          </clipPath>
          <clipPath id={id('eye-right-safe')} clipPathUnits="userSpaceOnUse">
            <ellipse cx="336" cy="276" rx="44" ry="56" />
          </clipPath>
          <path
            id={id('eye-mask-shape')}
            d="M 112 225 C 134 199, 170 196, 199 213 C 225 228, 237 251, 256 251 C 275 251, 287 228, 313 213 C 342 196, 378 199, 400 225 C 428 259, 416 313, 382 338 C 355 358, 321 352, 293 331 C 277 319, 268 311, 256 311 C 244 311, 235 319, 219 331 C 191 352, 157 358, 130 338 C 96 313, 84 259, 112 225 Z"
          />
        </defs>

        {/* head-rig: carries the pop bob during the idle loop. */}
        <motion.g
          style={originStyle(256, 260)}
          animate={runLoop ? { y: HEAD_Y } : undefined}
          transition={runLoop ? loopTransition(HEAD_TIMES) : undefined}
        >
          {/* shell + band */}
          <path
            id={id('head-shell')}
            fill={SHELL}
            d="M 256 64 C 376 64, 456 128, 472 218 C 488 304, 448 382, 374 424 C 338 444, 298 450, 256 450 C 214 450, 174 444, 138 424 C 64 382, 24 304, 40 218 C 56 128, 136 64, 256 64 Z"
          />
          <path
            fill={BAND}
            clipPath={`url(#${id('shell-clip')})`}
            d="M 38 205 C 48 238, 65 260, 93 271 C 160 296, 352 296, 419 271 C 447 260, 464 238, 474 205 L 475 240 C 464 268, 447 287, 420 297 C 350 323, 162 323, 92 297 C 65 287, 48 268, 37 240 Z"
          />

          {/* face module: mask + eyes */}
          <g>
            <use
              href={`#${id('eye-mask-shape')}`}
              fill="none"
              stroke={MASK_RIM}
              strokeWidth={22}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <use href={`#${id('eye-mask-shape')}`} fill={WHITE} />

            {/* Round open eyes — animated (or hidden in the static happy face). */}
            {!staticHappy && (
              <g>
                <g clipPath={`url(#${id('eye-left-safe')})`}>
                  <motion.g
                    style={originStyle(176, 276)}
                    animate={{
                      x: [0, PUPIL_DRIFT, 0, 0, 0, 0, 0, 0, 0],
                      scaleX: PUPIL_SCALE_X,
                      scaleY: PUPIL_SCALE_Y,
                      opacity: PUPIL_OPACITY,
                    }}
                    transition={loopTransition(PUPIL_TIMES)}
                  >
                    <ellipse cx="176" cy="276" rx="24" ry="36" fill={PUPIL} />
                    <circle cx="163" cy="248" r="8" fill={WHITE} />
                  </motion.g>
                </g>
                <g clipPath={`url(#${id('eye-right-safe')})`}>
                  <motion.g
                    style={originStyle(336, 276)}
                    animate={{
                      x: [0, -PUPIL_DRIFT, 0, 0, 0, 0, 0, 0, 0],
                      scaleX: PUPIL_SCALE_X,
                      scaleY: PUPIL_SCALE_Y,
                      opacity: PUPIL_OPACITY,
                    }}
                    transition={loopTransition(PUPIL_TIMES)}
                  >
                    <ellipse cx="336" cy="276" rx="24" ry="36" fill={PUPIL} />
                    <circle cx="323" cy="248" r="8" fill={WHITE} />
                  </motion.g>
                </g>
              </g>
            )}

            {/* Happy smile arcs — static when pinned/reduced, else pop on the loop. */}
            <motion.path
              d="M138 278c10-20 32-25 49-2"
              fill="none"
              stroke={PUPIL}
              strokeWidth={16}
              strokeLinecap="round"
              strokeLinejoin="round"
              style={originStyle(176, 276)}
              initial={false}
              animate={
                staticHappy
                  ? { opacity: 1, scale: 1 }
                  : { opacity: HAPPY_OPACITY, scale: HAPPY_SCALE }
              }
              transition={staticHappy ? undefined : loopTransition(HAPPY_TIMES)}
            />
            <motion.path
              d="M325 276c17-23 39-18 49 2"
              fill="none"
              stroke={PUPIL}
              strokeWidth={16}
              strokeLinecap="round"
              strokeLinejoin="round"
              style={originStyle(336, 276)}
              initial={false}
              animate={
                staticHappy
                  ? { opacity: 1, scale: 1 }
                  : { opacity: HAPPY_OPACITY, scale: HAPPY_SCALE }
              }
              transition={staticHappy ? undefined : loopTransition(HAPPY_TIMES)}
            />
          </g>
        </motion.g>
      </svg>
    </motion.div>
  )
}

export default Mascota

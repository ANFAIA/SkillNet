import { useEffect, useRef, useState } from 'react'
import './mascota.css'

/**
 * SkillNet mascot (arañita) as a self-contained, animatable SVG.
 * Faithful to the reference art; all pieces are inline so animations run on CSS.
 *
 *   <Mascota anim="celebrar" size={140} />
 *   <Mascota anim="talk" say="¡Muy bien!" />
 *
 * Learning-flow anims: celebrar | animar | pensar | idea | ups | amor | fuego
 * Basic anims: idle | talk | web | saltar | caminar | temblar | saludar | dormir
 * One-shot anims auto-return to "idle" when finished.
 */
export type MascotaAnim =
  | 'idle' | 'talk' | 'web' | 'saltar' | 'caminar' | 'temblar' | 'saludar' | 'dormir'
  | 'celebrar' | 'animar' | 'pensar' | 'idea' | 'ups' | 'amor' | 'fuego'

const ONE_SHOT = new Set<MascotaAnim>(['saltar', 'temblar', 'saludar', 'idea'])

const SVG_HTML = (say: string) => `<svg class="mas-svg" viewBox="0 -60 240 272" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mascota">
  <g class="mas-hang"><g class="mas-sway">
    <line class="thread" x1="120" y1="-320" x2="120" y2="17"/>
    <g class="mas-root">
      <ellipse class="m-shadow" cx="120" cy="200" rx="72" ry="9"/>
      <g class="mas-legs-l"><path class="m-leg leg-wave" d="M58,116 L15,111 L11,146"/><path class="m-leg" d="M64,141 L23,167 L27,193"/></g>
      <g class="mas-legs-r"><path class="m-leg" d="M182,116 L225,111 L229,146"/><path class="m-leg" d="M176,141 L217,167 L213,193"/></g>
      <path class="m-body" d="M 98.93,18.14 L 97.46,19.25 L 96.20,20.44 L 95.16,21.73 L 94.34,23.11 L 93.72,24.57 L 93.26,26.01 L 92.96,27.42 L 92.81,28.80 L 92.81,30.15 L 92.87,31.37 L 92.99,32.48 L 93.17,33.46 L 93.42,34.31 L 93.94,35.48 L 94.73,36.95 L 95.81,38.72 L 97.15,40.81 L 97.15,42.70 L 95.81,44.42 L 93.11,45.95 L 89.07,47.30 L 85.55,48.55 L 82.55,49.72 L 80.06,50.79 L 78.11,51.77 L 75.87,53.03 L 73.36,54.56 L 70.57,56.36 L 67.51,58.45 L 64.32,60.93 L 61.02,63.81 L 57.59,67.08 L 54.03,70.76 L 50.82,74.46 L 47.94,78.20 L 45.40,81.97 L 43.19,85.76 L 41.20,89.62 L 39.43,93.54 L 37.86,97.52 L 36.52,101.57 L 35.38,105.52 L 34.46,109.38 L 33.76,113.14 L 33.27,116.82 L 32.96,120.43 L 32.84,123.98 L 32.90,127.47 L 33.15,130.91 L 33.55,134.21 L 34.10,137.40 L 34.80,140.46 L 35.66,143.40 L 36.79,146.46 L 38.20,149.65 L 39.89,152.95 L 41.84,156.38 L 43.99,159.63 L 46.32,162.69 L 48.83,165.57 L 51.52,168.27 L 54.25,170.75 L 57.00,173.01 L 59.79,175.07 L 62.61,176.90 L 65.76,178.71 L 69.25,180.49 L 73.08,182.23 L 77.25,183.95 L 81.78,185.51 L 86.68,186.92 L 91.95,188.17 L 97.58,189.28 L 103.31,190.13 L 109.13,190.75 L 115.04,191.11 L 121.04,191.24 L 126.68,191.17 L 131.94,190.93 L 136.84,190.50 L 141.38,189.89 L 145.72,189.15 L 149.89,188.30 L 153.87,187.32 L 157.67,186.21 L 161.34,184.99 L 164.90,183.64 L 168.33,182.17 L 171.63,180.58 L 174.82,178.86 L 177.88,177.03 L 180.82,175.07 L 183.64,172.98 L 186.30,170.78 L 188.81,168.45 L 191.17,166.00 L 193.38,163.43 L 195.37,160.89 L 197.14,158.38 L 198.71,155.90 L 200.05,153.44 L 201.22,151.18 L 202.20,149.10 L 202.99,147.20 L 203.61,145.48 L 204.22,143.43 L 204.83,141.04 L 205.44,138.32 L 206.06,135.25 L 206.49,131.88 L 206.73,128.21 L 206.79,124.23 L 206.67,119.94 L 206.30,115.68 L 205.69,111.46 L 204.83,107.26 L 203.73,103.10 L 202.47,99.09 L 201.06,95.23 L 199.50,91.52 L 197.79,87.97 L 196.19,84.84 L 194.72,82.15 L 193.38,79.88 L 192.15,78.05 L 190.59,75.96 L 188.69,73.64 L 186.46,71.06 L 183.88,68.25 L 181.00,65.46 L 177.82,62.70 L 174.33,59.98 L 170.53,57.28 L 166.89,54.89 L 163.40,52.81 L 160.06,51.03 L 156.87,49.56 L 153.75,48.25 L 150.69,47.08 L 147.69,46.07 L 144.75,45.22 L 142.82,44.17 L 141.90,42.95 L 141.99,41.54 L 143.09,39.95 L 144.04,38.42 L 144.84,36.95 L 145.48,35.54 L 145.97,34.19 L 146.34,32.81 L 146.58,31.40 L 146.70,29.96 L 146.70,28.49 L 146.64,27.21 L 146.52,26.11 L 146.34,25.19 L 146.09,24.45 L 145.66,23.59 L 145.05,22.62 L 144.25,21.51 L 143.28,20.29 L 142.20,19.22 L 141.04,18.30 L 139.78,17.53 L 138.44,16.92 L 137.03,16.49 L 135.56,16.25 L 134.03,16.18 L 132.43,16.31 L 130.96,16.55 L 129.62,16.92 L 128.39,17.41 L 127.29,18.02 L 126.25,18.70 L 125.27,19.43 L 124.35,20.23 L 123.49,21.08 L 122.69,22.00 L 121.96,22.98 L 121.29,24.02 L 120.67,25.13 L 120.03,25.65 L 119.36,25.59 L 118.65,24.94 L 117.92,23.72 L 117.06,22.52 L 116.08,21.36 L 114.98,20.23 L 113.75,19.12 L 112.59,18.20 L 111.49,17.47 L 110.44,16.92 L 109.47,16.55 L 108.30,16.31 L 106.95,16.18 L 105.42,16.18 L 103.71,16.31 L 102.05,16.67 L 100.46,17.29 Z"/>
      <g class="eye-open">
        <rect class="m-white" x="64" y="99" width="42" height="56" rx="21"/>
        <rect class="m-white" x="134" y="99" width="42" height="56" rx="21"/>
        <g class="look">
          <rect class="m-pupil" x="82" y="109" width="22" height="32" rx="11"/>
          <rect class="m-pupil" x="136" y="109" width="22" height="32" rx="11"/>
          <circle class="m-hl" cx="94" cy="117" r="3.4"/><circle class="m-hl" cx="148" cy="117" r="3.4"/>
        </g>
      </g>
      <path class="eye-sleep" d="M69,124 Q85,139 101,124"/>
      <path class="eye-sleep" d="M139,124 Q155,139 171,124"/>
      <g class="mas-mouth">
        <path class="m-mouth m-smile" d="M108,156 Q120,167 132,156"/>
        <path class="m-talk" d="M108,155 Q120,152 132,155 Q127,170 120,170 Q113,170 108,155 Z"/>
        <path class="m-grin" d="M103,153 Q120,150 137,153 Q131,173 120,173 Q109,173 103,153 Z"/>
        <path class="m-flat" d="M110,160 L130,160"/>
      </g>
      <path class="sweat" transform="translate(58,116)" d="M0,0 C4,6 6,9 6,12 A6,6 0 1 1 -6,12 C-6,9 -4,6 0,0 Z" fill="#6BB8FF"/>
      <g class="bubble">
        <path class="bubble-box" d="M150,-52 h74 a12,12 0 0 1 12,12 v20 a12,12 0 0 1 -12,12 h-52 l-14,12 l2,-12 h-10 a12,12 0 0 1 -12,-12 v-20 a12,12 0 0 1 12,-12 z"/>
        <text class="bubble-txt" x="187" y="-25" text-anchor="middle">%SAY%</text>
      </g>
      <g class="think">
        <circle cx="150" cy="6" r="3" fill="#fff"/><circle cx="162" cy="-6" r="5" fill="#fff"/>
        <rect x="172" y="-40" width="64" height="32" rx="14" fill="#fff"/>
        <circle class="d d1" cx="188" cy="-24" r="3.2" fill="#12203f"/>
        <circle class="d d2" cx="204" cy="-24" r="3.2" fill="#12203f"/>
        <circle class="d d3" cx="220" cy="-24" r="3.2" fill="#12203f"/>
      </g>
      <g class="bulb">
        <line class="ray" x1="120" y1="-46" x2="120" y2="-54"/><line class="ray" x1="99" y1="-40" x2="92" y2="-46"/>
        <line class="ray" x1="141" y1="-40" x2="148" y2="-46"/><line class="ray" x1="94" y1="-24" x2="85" y2="-24"/>
        <line class="ray" x1="146" y1="-24" x2="155" y2="-24"/>
        <circle cx="120" cy="-26" r="14" fill="#FFD24A"/><rect x="112" y="-15" width="16" height="8" rx="2" fill="#CDD3DE"/>
      </g>
      <g class="flame">
        <path d="M120,8 C110,-4 114,-18 120,-32 C126,-18 130,-4 120,8 Z" fill="#FF7A1A"/>
        <path d="M120,5 C114,-3 116,-13 120,-22 C124,-13 126,-3 120,5 Z" fill="#FFD24A"/>
      </g>
      <g class="confetti"><rect class="conf" style="--tx:0px;--ty:120px;--rot:-166deg;animation-delay:0.36s;fill:#FF6B6B" x="116" y="56" width="5" height="5" rx="1"/><rect class="conf" style="--tx:55px;--ty:66px;--rot:54deg;animation-delay:0.52s;fill:#FFD24A" x="115" y="56" width="6" height="6" rx="1"/><circle class="conf" style="--tx:-60px;--ty:87px;--rot:108deg;animation-delay:0.06s;fill:#4ADE80" cx="120" cy="59" r="2.5"/><rect class="conf" style="--tx:-67px;--ty:112px;--rot:259deg;animation-delay:0.11s;fill:#FF8FB0" x="115" y="56" width="6" height="6" rx="1"/><rect class="conf" style="--tx:65px;--ty:97px;--rot:86deg;animation-delay:0.04s;fill:#6BA8FF" x="115" y="56" width="6" height="6" rx="1"/><rect class="conf" style="--tx:60px;--ty:114px;--rot:-184deg;animation-delay:0.26s;fill:#B980FF" x="115" y="56" width="6" height="6" rx="1"/><rect class="conf" style="--tx:64px;--ty:79px;--rot:253deg;animation-delay:0.73s;fill:#FF9F45" x="115" y="56" width="6" height="6" rx="1"/><rect class="conf" style="--tx:66px;--ty:96px;--rot:-128deg;animation-delay:0.34s;fill:#FF6B6B" x="116" y="56" width="5" height="5" rx="1"/><circle class="conf" style="--tx:76px;--ty:73px;--rot:188deg;animation-delay:0.61s;fill:#FFD24A" cx="120" cy="59" r="3.5"/><rect class="conf" style="--tx:37px;--ty:97px;--rot:144deg;animation-delay:0.33s;fill:#4ADE80" x="115" y="56" width="6" height="6" rx="1"/><circle class="conf" style="--tx:-20px;--ty:65px;--rot:268deg;animation-delay:0.27s;fill:#FF8FB0" cx="120" cy="59" r="3.5"/><circle class="conf" style="--tx:32px;--ty:78px;--rot:303deg;animation-delay:0.88s;fill:#6BA8FF" cx="120" cy="59" r="2.5"/><circle class="conf" style="--tx:-40px;--ty:108px;--rot:30deg;animation-delay:0.14s;fill:#B980FF" cx="120" cy="59" r="3.5"/><circle class="conf" style="--tx:-72px;--ty:102px;--rot:-241deg;animation-delay:0.69s;fill:#FF9F45" cx="120" cy="59" r="3.0"/><rect class="conf" style="--tx:7px;--ty:98px;--rot:188deg;animation-delay:0.52s;fill:#FF6B6B" x="115" y="56" width="7" height="7" rx="1"/><rect class="conf" style="--tx:-59px;--ty:120px;--rot:-44deg;animation-delay:0.43s;fill:#FFD24A" x="116" y="56" width="5" height="5" rx="1"/></g>
      <g class="hearts"><g class="heart" style="--hx:-20px;animation-delay:0s"><path d="M0,3 C-2,-1 -7,-1 -7,3 C-7,6 -3,8 0,11 C3,8 7,6 7,3 C7,-1 2,-1 0,3 Z" transform="translate(120,98) scale(1.4)" fill="#FF6B8B"/></g><g class="heart" style="--hx:14px;animation-delay:0.6s"><path d="M0,3 C-2,-1 -7,-1 -7,3 C-7,6 -3,8 0,11 C3,8 7,6 7,3 C7,-1 2,-1 0,3 Z" transform="translate(120,104) scale(1.4)" fill="#FF6B8B"/></g><g class="heart" style="--hx:-2px;animation-delay:1.2s"><path d="M0,3 C-2,-1 -7,-1 -7,3 C-7,6 -3,8 0,11 C3,8 7,6 7,3 C7,-1 2,-1 0,3 Z" transform="translate(120,96) scale(1.4)" fill="#FF6B8B"/></g></g>
      <text class="zzz z1" x="150" y="60">z</text>
      <text class="zzz z2" x="162" y="46" font-size="15">z</text>
      <text class="zzz z3" x="172" y="34" font-size="12">z</text>
    </g>
  </g></g>
</svg>`.replace('%SAY%', say)

export interface MascotaProps {
  /** Current animation. One-shot anims fall back to "idle" when done. */
  anim?: MascotaAnim
  /** Width in px (or any CSS length). Height scales automatically. */
  size?: number | string
  /** Text shown in the speech bubble for anim="talk". */
  say?: string
  /** Pupils follow the pointer. Default true. */
  followCursor?: boolean
  className?: string
  onClick?: () => void
}

export function Mascota({
  anim = 'idle',
  size = 140,
  say = '¡Hola!',
  followCursor = true,
  className = '',
  onClick,
}: MascotaProps) {
  const [current, setCurrent] = useState<MascotaAnim>(anim)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => { setCurrent(anim) }, [anim])

  // pupils follow the pointer
  useEffect(() => {
    const el = ref.current
    if (!el || !followCursor) return
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      const dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2)
      const dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2)
      el.style.setProperty('--lx', `${Math.max(-1, Math.min(1, dx)) * 3}px`)
      el.style.setProperty('--ly', `${Math.max(-1, Math.min(1, dy)) * 3}px`)
    }
    const reset = () => {
      el.style.setProperty('--lx', '0px'); el.style.setProperty('--ly', '0px')
    }
    window.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', reset)
    return () => {
      window.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', reset)
    }
  }, [followCursor])

  const width = typeof size === 'number' ? `${size}px` : size

  return (
    <div
      ref={ref}
      className={`skn-mascota ${className}`}
      data-anim={current}
      style={{ width }}
      onClick={onClick}
      onAnimationEnd={() => { if (ONE_SHOT.has(current)) setCurrent('idle') }}
      dangerouslySetInnerHTML={{ __html: SVG_HTML(say) }}
    />
  )
}

export default Mascota

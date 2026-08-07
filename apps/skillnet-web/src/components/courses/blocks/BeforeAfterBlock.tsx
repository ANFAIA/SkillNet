import { useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'
import { ClickableText } from '../ClickableText'

export interface BeforeAfterBlockProps {
  title: string
  beforeLabel: string
  beforeContent: string
  afterLabel: string
  afterContent: string
}

export function BeforeAfterBlock({
  title,
  beforeLabel,
  beforeContent,
  afterLabel,
  afterContent,
}: BeforeAfterBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState(50)

  function handlePointerDown(e: React.PointerEvent) {
    e.preventDefault()
    const target = e.currentTarget as HTMLElement
    target.setPointerCapture(e.pointerId)
  }

  function handlePointerMove(e: React.PointerEvent) {
    const target = e.currentTarget as HTMLElement
    if (!target.hasPointerCapture(e.pointerId)) return
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100))
    setPosition(pct)
  }

  function handlePointerUp(e: React.PointerEvent) {
    const target = e.currentTarget as HTMLElement
    target.releasePointerCapture(e.pointerId)
  }

  return (
    <div className={INLINE_SURFACE}>
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}

      <div
        ref={containerRef}
        className="relative select-none overflow-hidden rounded-lg border border-border"
        style={{ minHeight: 120 }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        role="slider"
        aria-label={`Comparar ${beforeLabel} y ${afterLabel}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(position)}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setPosition((p) => Math.max(0, p - 2))
          if (e.key === 'ArrowRight') setPosition((p) => Math.min(100, p + 2))
        }}
      >
        {/* Before side (full width, clipped) */}
        <div
          className="absolute inset-0 bg-red-50/40 dark:bg-red-950/20"
          style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        >
          <div className="p-4 h-full">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {beforeLabel || 'Antes'}
            </span>
            <ClickableText as="p" className="text-sm text-text mt-2 whitespace-pre-wrap">{beforeContent}</ClickableText>
          </div>
        </div>

        {/* After side (full width, clipped) */}
        <div
          className="absolute inset-0 bg-emerald-50/40 dark:bg-emerald-950/20"
          style={{ clipPath: `inset(0 0 0 ${position}%)` }}
        >
          <div className="p-4 h-full">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wide">
              {afterLabel || 'Despues'}
            </span>
            <ClickableText as="p" className="text-sm text-text mt-2 whitespace-pre-wrap">{afterContent}</ClickableText>
          </div>
        </div>

        {/* Invisible spacer for natural height */}
        <div className="invisible p-4">
          <span className="text-xs font-medium uppercase tracking-wide">&nbsp;</span>
          <p className="text-sm mt-2 whitespace-pre-wrap">
            {beforeContent.length > afterContent.length ? beforeContent : afterContent}
          </p>
        </div>

        {/* Divider */}
        <motion.div
          className="absolute top-0 bottom-0 w-px bg-border-strong z-10"
          style={{ left: `${position}%` }}
          aria-hidden
        >
          {/* Handle */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-bg border-2 border-border-strong flex items-center justify-center shadow-sm cursor-ew-resize">
            <svg width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden>
              <path d="M1 0v12M4 0v12M7 0v12" stroke="currentColor" strokeWidth="1" className="text-text-muted" />
            </svg>
          </div>
        </motion.div>
      </div>
    </div>
  )
}

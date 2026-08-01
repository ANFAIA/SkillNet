import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'
import { BLOCK_TITLE } from './rhythm'

export interface Hotspot {
  x: number
  y: number
  label: string
  detail: string
}

export interface HotspotImageBlockProps {
  imageUrl: string
  alt: string
  hotspots: Hotspot[]
}

/**
 * Parse raw hotspot data from the OpenUI dialect.
 *
 * Each sub-array is `[x, y, label, detail]` where `x` and `y` are percentage
 * strings ("42", "78") that must be parsed as numbers.
 */
export function parseHotspots(raw: unknown): Hotspot[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((entry) => Array.isArray(entry) && entry.length >= 4)
    .map((entry) => ({
      x: clampPct(Number(entry[0])),
      y: clampPct(Number(entry[1])),
      label: typeof entry[2] === 'string' ? entry[2] : String(entry[2] ?? ''),
      detail: typeof entry[3] === 'string' ? entry[3] : String(entry[3] ?? ''),
    }))
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

function HotspotMarker({
  hotspot,
  index,
  isActive,
  onToggle,
}: {
  hotspot: Hotspot
  index: number
  isActive: boolean
  onToggle: () => void
}) {
  // Determine popover position: if hotspot is on the right side, show on left; etc.
  const popoverLeft = hotspot.x > 60
  const popoverAbove = hotspot.y > 70

  return (
    <div
      className="absolute"
      style={{
        left: `${hotspot.x}%`,
        top: `${hotspot.y}%`,
        transform: 'translate(-50%, -50%)',
      }}
    >
      {/* The marker button */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        aria-label={`Punto ${index + 1}: ${hotspot.label}`}
        aria-expanded={isActive}
        className={`relative w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-semibold transition-colors ${
          isActive
            ? 'bg-primary border-primary text-white'
            : 'bg-bg border-primary text-primary hover:bg-primary-subtle'
        }`}
      >
        {index + 1}
        {/* Pulse ring for inactive markers */}
        {!isActive && (
          <span
            aria-hidden="true"
            className="absolute inset-0 rounded-full border-2 border-primary animate-ping opacity-20"
          />
        )}
      </button>

      {/* Popover */}
      <AnimatePresence>
        {isActive && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: duration.fast, ease: ease.base }}
            className={`absolute z-20 w-56 rounded-lg border border-border bg-bg p-3 shadow-md ${
              popoverLeft ? 'right-full mr-2' : 'left-full ml-2'
            } ${popoverAbove ? 'bottom-0' : 'top-0'}`}
          >
            <p className="text-sm font-medium text-text">{hotspot.label}</p>
            <p className="text-xs text-text-secondary mt-1 leading-relaxed">
              {hotspot.detail}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function HotspotImageBlock({ imageUrl, alt, hotspots }: HotspotImageBlockProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const safeHotspots = Array.isArray(hotspots) ? hotspots : []

  function handleToggle(index: number) {
    setActiveIndex((prev) => (prev === index ? null : index))
  }

  function handleClickOutside() {
    setActiveIndex(null)
  }

  return (
    <figure className="min-w-0 m-0">
      {alt ? <figcaption className={BLOCK_TITLE}>{alt}</figcaption> : null}
      {/* Container: relative positioning for hotspot overlay */}
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
      <div className="relative inline-block w-full" onClick={handleClickOutside}>
        <img
          src={imageUrl}
          alt={alt}
          className="w-full h-auto block rounded-lg"
          loading="lazy"
        />
        {safeHotspots.map((hotspot, idx) => (
          <HotspotMarker
            key={idx}
            hotspot={hotspot}
            index={idx}
            isActive={activeIndex === idx}
            onToggle={() => handleToggle(idx)}
          />
        ))}
      </div>
      {/* Accessible list of hotspots for screen readers */}
      <ul className="sr-only">
        {safeHotspots.map((hotspot, idx) => (
          <li key={idx}>
            {hotspot.label}: {hotspot.detail}
          </li>
        ))}
      </ul>
    </figure>
  )
}

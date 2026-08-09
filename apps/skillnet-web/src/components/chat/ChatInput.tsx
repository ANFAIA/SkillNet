/**
 * ChatInput — unified composer for every chat surface in the app.
 *
 * Auto-growing textarea, Enter to send / Shift+Enter for newline,
 * send-or-stop button with a gooey morph animation lifted from the
 * admin chat page.
 *
 * Two sizes: `"md"` (default, for full-page chat) and `"sm"` (for
 * sidebars, modals and the lesson buddy bubble).
 */

import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useIntl } from 'react-intl'

export interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop?: () => void
  isStreaming?: boolean
  placeholder?: string
  disabled?: boolean
  /** Visual size. `"md"` for page-level chat, `"sm"` for panels/modals. */
  size?: 'md' | 'sm'
  /** Auto-focus the textarea on mount after a short delay. */
  autoFocus?: boolean
}

const MAX_HEIGHT: Record<'md' | 'sm', number> = { md: 200, sm: 120 }

// Sizes for the button and icon.
const BTN: Record<'md' | 'sm', { h: string; w: string; icon: number }> = {
  md: { h: 'h-11', w: 'w-11', icon: 15 },
  sm: { h: 'h-8', w: 'w-8', icon: 12 },
}

// A unique filter id per instance avoids clashes when multiple ChatInputs
// coexist on the same page (e.g. NodeChat panel open alongside the chat page).
let nextFilterId = 0

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming = false,
  placeholder,
  disabled = false,
  size = 'md',
  autoFocus = false,
}: ChatInputProps) {
  const intl = useIntl()
  const taRef = useRef<HTMLTextAreaElement>(null)
  const [focused, setFocused] = useState(false)
  const [filterId] = useState(() => `chatinput-gooey-${nextFilterId++}`)

  const maxH = MAX_HEIGHT[size]
  const btn = BTN[size]

  // Auto-focus on mount when requested.
  useLayoutEffect(() => {
    if (!autoFocus) return
    const t = setTimeout(() => taRef.current?.focus(), 200)
    return () => clearTimeout(t)
  }, [autoFocus])

  // Auto-grow textarea: shrink to `auto`, then take the content height capped at maxH.
  const resize = useCallback(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`
    el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden'
  }, [maxH])

  // Recompute on every value change.
  useLayoutEffect(resize, [value, resize])

  // Recompute when the textarea's own width changes. Without this, a composer that
  // mounts inside an animating container (e.g. the NodeView chat panel sliding from
  // 48px to 400px) measures scrollHeight while the box is still narrow — the
  // placeholder wraps into many lines and the height sticks at maxH forever, since
  // the value-driven effect above never re-fires. Also covers window resize and
  // late font loads. Guarded on width so our own height writes don't loop.
  useLayoutEffect(() => {
    const el = taRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let lastWidth = el.clientWidth
    const observer = new ResizeObserver(() => {
      if (el.clientWidth === lastWidth) return
      lastWidth = el.clientWidth
      resize()
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [resize])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!value.trim() || disabled) return
    onSend()
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const active = focused || value.trim().length > 0

  const resolvedPlaceholder =
    placeholder ?? intl.formatMessage({ id: 'chatInput.placeholder' })

  const minH = size === 'sm' ? 'min-h-[36px]' : 'min-h-[44px]'
  const py = size === 'sm' ? 'py-2' : 'py-[11px]'
  const px = size === 'sm' ? 'px-3' : 'px-4'
  const rounding = 'rounded-3xl'

  return (
    <div style={{ filter: `url(#${filterId})` }}>
      <div className="relative flex items-end">
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={1}
          disabled={disabled}
          placeholder={resolvedPlaceholder}
          className={`${minH} flex-1 resize-none overflow-y-hidden ${rounding} bg-bg-muted ${px} ${py} text-sm leading-normal text-text outline-none placeholder:text-text-muted disabled:opacity-50`}
          style={{
            marginRight: active || isStreaming ? (size === 'sm' ? 40 : 52) : 0,
            transition: 'margin-right 0.5s var(--ease-gooey)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            right: 0,
            bottom: 0,
            transform: active || isStreaming ? 'translateX(0)' : 'translateX(-4px)',
            transition: 'transform 0.5s var(--ease-gooey)',
          }}
        >
          <button
            type={isStreaming ? 'button' : 'submit'}
            onClick={isStreaming ? onStop : undefined}
            disabled={!isStreaming && (!value.trim() || disabled)}
            aria-label={
              isStreaming
                ? intl.formatMessage({ id: 'chatInput.stop' })
                : intl.formatMessage({ id: 'chatInput.send' })
            }
            className={`flex ${btn.h} ${btn.w} items-center justify-center rounded-full bg-bg-muted text-text-muted transition-colors hover:bg-primary hover:text-white disabled:text-text-muted disabled:hover:bg-bg-muted`}
          >
            {isStreaming ? (
              <svg width={btn.icon - 1} height={btn.icon - 1} viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            ) : (
              <svg
                width={btn.icon}
                height={btn.icon}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  opacity: active ? 1 : 0,
                  transition: 'opacity 0.3s ease 0.15s',
                }}
              >
                <path d="M5 12h13" />
                <path d="M12 5l7 7-7 7" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Gooey filter: makes the button morph into/out of the textarea. */}
      <svg style={{ position: 'absolute', width: 0, height: 0 }} aria-hidden="true">
        <defs>
          <filter id={filterId}>
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
            <feColorMatrix
              in="blur"
              type="matrix"
              values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -9"
              result="gooey"
            />
            <feComposite in="SourceGraphic" in2="gooey" operator="atop" />
          </filter>
        </defs>
      </svg>
    </div>
  )
}

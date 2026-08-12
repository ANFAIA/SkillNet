export const ACCENT_COLOR_OPTIONS = [
  { value: 'neutral', color: '#27272a', labelId: 'appearance.accent.neutral' },
  { value: 'blue', color: '#3661a5', labelId: 'appearance.accent.blue' },
  { value: 'purple', color: '#7c3aed', labelId: 'appearance.accent.purple' },
  { value: 'green', color: '#16815c', labelId: 'appearance.accent.green' },
  { value: 'orange', color: '#c65c22', labelId: 'appearance.accent.orange' },
  { value: 'pink', color: '#be3a71', labelId: 'appearance.accent.pink' },
] as const

export type AccentColor = (typeof ACCENT_COLOR_OPTIONS)[number]['value'] | 'custom'

export const DEFAULT_ACCENT_COLOR: AccentColor = 'blue'
export const DEFAULT_CUSTOM_ACCENT = '#5b5ce2'

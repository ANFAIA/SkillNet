export const UI_PRESET_OPTIONS = [
  {
    value: 'clean',
    labelId: 'appearance.preset.clean',
    descriptionId: 'appearance.preset.cleanDesc',
  },
  {
    value: 'classic',
    labelId: 'appearance.preset.classic',
    descriptionId: 'appearance.preset.classicDesc',
  },
  {
    value: 'monochrome',
    labelId: 'appearance.preset.monochrome',
    descriptionId: 'appearance.preset.monochromeDesc',
  },
] as const

export type UiPreset = (typeof UI_PRESET_OPTIONS)[number]['value']

export const DEFAULT_UI_PRESET: UiPreset = 'clean'

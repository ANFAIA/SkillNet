export function formatSkillName(value: string): string {
  const normalized = value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+([,.;:])/g, '$1')
    .replace(/([,.;:])(?=\S)/g, '$1 ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!normalized) return ''
  return normalized.charAt(0).toLocaleUpperCase('es') + normalized.slice(1)
}

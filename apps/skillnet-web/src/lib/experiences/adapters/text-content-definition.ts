export type TextContentVariant = 'lead' | 'body' | 'caption'

export type TextContentDefinition = Readonly<{
  content: string
  variant: TextContentVariant
}>

export type TextContentValidation =
  | { ok: true; definition: TextContentDefinition }
  | { ok: false }

const VARIANTS = new Set<TextContentVariant>(['lead', 'body', 'caption'])
const MAX_CONTENT_LENGTH = 1_600

export function validateTextContentDefinition(value: unknown): TextContentValidation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { ok: false }
  const raw = value as Record<string, unknown>
  if (typeof raw.content !== 'string') return { ok: false }

  const content = raw.content.trim()
  if (!content || content.length > MAX_CONTENT_LENGTH) return { ok: false }
  if (typeof raw.variant !== 'string' || !VARIANTS.has(raw.variant as TextContentVariant)) {
    return { ok: false }
  }

  return {
    ok: true,
    definition: { content, variant: raw.variant as TextContentVariant },
  }
}


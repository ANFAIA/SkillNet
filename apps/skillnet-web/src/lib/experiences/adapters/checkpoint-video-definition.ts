export type CheckpointVideoDefinition = Readonly<{
  src: string
  title: string
  captionsSrc?: string
  captionsLanguage?: string
  transcript?: string
  checkpointText?: string
}>

export type CheckpointVideoValidation =
  | { ok: true; definition: CheckpointVideoDefinition }
  | { ok: false }

function text(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized || undefined
}

function safeMediaUrl(value: unknown): string | undefined {
  const candidate = text(value)
  if (!candidate) return undefined
  if (candidate.startsWith('/') && !candidate.startsWith('//')) return candidate

  try {
    const parsed = new URL(candidate)
    return parsed.protocol === 'https:' ? parsed.toString() : undefined
  } catch {
    return undefined
  }
}

export function validateCheckpointVideoDefinition(value: unknown): CheckpointVideoValidation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { ok: false }
  const raw = value as Record<string, unknown>
  const src = safeMediaUrl(raw.src)
  const captionsSrc = safeMediaUrl(raw.captionsSrc)
  const transcript = text(raw.transcript)
  if (!src || (!captionsSrc && !transcript)) return { ok: false }

  return {
    ok: true,
    definition: {
      src,
      title: text(raw.title) ?? 'Vídeo formativo',
      ...(captionsSrc ? { captionsSrc } : {}),
      ...(text(raw.captionsLanguage) ? { captionsLanguage: text(raw.captionsLanguage) } : {}),
      ...(transcript ? { transcript } : {}),
      ...(text(raw.checkpointText) ? { checkpointText: text(raw.checkpointText) } : {}),
    },
  }
}


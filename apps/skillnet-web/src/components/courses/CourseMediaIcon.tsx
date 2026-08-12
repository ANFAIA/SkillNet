import type { MediaKind } from '../../api/media'

interface CourseMediaIconProps {
  kind: string
  className?: string
  size?: number
}

export function CourseMediaIcon({ kind, className = '', size = 20 }: CourseMediaIconProps) {
  const props = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
    'aria-hidden': true,
  }

  switch (kind as MediaKind) {
    case 'podcast':
      return (
        <svg {...props}>
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      )
    case 'video':
      return (
        <svg {...props}>
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <polygon points="10 9 15 12 10 15 10 9" />
        </svg>
      )
    case 'infographic':
      return (
        <svg {...props}>
          <line x1="6" y1="20" x2="6" y2="14" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="18" y1="20" x2="18" y2="10" />
        </svg>
      )
    case 'slides':
      return (
        <svg {...props}>
          <rect x="3" y="4" width="18" height="12" rx="1" />
          <line x1="12" y1="16" x2="12" y2="20" />
          <line x1="9" y1="20" x2="15" y2="20" />
        </svg>
      )
    default:
      return null
  }
}

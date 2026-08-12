export type SettingsIconName =
  | 'sun'
  | 'moon'
  | 'monitor'
  | 'palette'
  | 'sparkles'
  | 'accessibility'
  | 'format'
  | 'balance'
  | 'image'
  | 'text'
  | 'pointer'
  | 'detail'
  | 'zap'
  | 'normal'
  | 'layers'
  | 'images'
  | 'imagePlus'
  | 'imageOff'
  | 'shield'
  | 'arrowRight'

export function SettingsIcon({
  name,
  size = 16,
  className = '',
}: {
  name: SettingsIconName
  size?: number
  className?: string
}) {
  const common = {
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

  switch (name) {
    case 'sun':
      return <svg {...common}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" /></svg>
    case 'moon':
      return <svg {...common}><path d="M20.7 13.2A8.5 8.5 0 1 1 10.8 3.3a6.6 6.6 0 0 0 9.9 9.9Z" /></svg>
    case 'monitor':
      return <svg {...common}><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></svg>
    case 'palette':
      return <svg {...common}><path d="M12 3a9 9 0 0 0 0 18h1.5a1.5 1.5 0 0 0 0-3H12a2 2 0 0 1 0-4h2.5A6.5 6.5 0 0 0 21 7.5C21 5 17 3 12 3Z" /><circle cx="7.5" cy="10.5" r=".5" fill="currentColor" /><circle cx="10" cy="7" r=".5" fill="currentColor" /><circle cx="14" cy="7" r=".5" fill="currentColor" /></svg>
    case 'sparkles':
      return <svg {...common}><path d="m12 3-1.2 3.1L8 7.5l2.8 1.4L12 12l1.2-3.1L16 7.5l-2.8-1.4L12 3ZM5 13l-.8 2.2L2 16l2.2.8L5 19l.8-2.2L8 16l-2.2-.8L5 13ZM18 13l-.8 2.2L15 16l2.2.8L18 19l.8-2.2L21 16l-2.2-.8L18 13Z" /></svg>
    case 'accessibility':
      return <svg {...common}><circle cx="12" cy="4" r="2" /><path d="M5 8h14M12 6v7M8 21l4-8 4 8M7 13l5 2 5-2" /></svg>
    case 'format':
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 9v11" /></svg>
    case 'balance':
      return <svg {...common}><path d="M12 3v18M5 7h14M7 7l-4 7h8L7 7ZM17 7l-4 7h8l-4-7Z" /></svg>
    case 'image':
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 15-5-5L5 20" /></svg>
    case 'text':
      return <svg {...common}><path d="M4 6h16M4 10h12M4 14h16M4 18h10" /></svg>
    case 'pointer':
      return <svg {...common}><path d="m5 3 14 9-6 1-3 6-5-16Z" /></svg>
    case 'detail':
      return <svg {...common}><path d="M4 6h16M4 12h16M4 18h16" /></svg>
    case 'zap':
      return <svg {...common}><path d="m13 2-9 12h7l-1 8 9-12h-7l1-8Z" /></svg>
    case 'normal':
      return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
    case 'layers':
      return <svg {...common}><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 17l9 5 9-5" /></svg>
    case 'images':
      return <svg {...common}><rect x="3" y="5" width="14" height="14" rx="2" /><path d="m17 9 4 2v8a2 2 0 0 1-2 2H9l-2-2M3 15l4-4 5 5 2-2 3 3" /></svg>
    case 'imagePlus':
      return <svg {...common}><rect x="3" y="4" width="14" height="16" rx="2" /><path d="m3 16 4-4 4 4 2-2 4 4M20 5v6M17 8h6" /></svg>
    case 'imageOff':
      return <svg {...common}><path d="m3 3 18 18M10.5 5H5a2 2 0 0 0-2 2v12h14M14 5h5a2 2 0 0 1 2 2v10M3 16l4-4 2 2" /></svg>
    case 'shield':
      return <svg {...common}><path d="M12 3 20 6v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6l8-3Z" /><path d="m9 12 2 2 4-5" /></svg>
    case 'arrowRight':
      return <svg {...common}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
  }
}

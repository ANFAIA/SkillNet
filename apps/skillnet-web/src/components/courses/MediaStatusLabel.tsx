interface MediaStatusLabelProps {
  status: string
  label: string
  animated: boolean
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'text-text-muted',
  running: 'text-primary',
  done: 'text-accent',
  error: 'text-danger',
}

export function MediaStatusLabel({ status, label, animated }: MediaStatusLabelProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${STATUS_COLOR[status] ?? 'text-text-muted'}`}>
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={status === 'running' && animated ? 'animate-spin' : ''}
        aria-hidden="true"
      >
        {status === 'done' ? (
          <><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></>
        ) : status === 'error' ? (
          <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>
        ) : status === 'running' ? (
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        ) : (
          <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>
        )}
      </svg>
      {label}
    </span>
  )
}

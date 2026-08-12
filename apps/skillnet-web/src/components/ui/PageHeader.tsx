interface PageHeaderProps {
  title: string
  description?: string
  actions?: React.ReactNode
  eyebrow?: string
}

export function PageHeader({ title, description, actions, eyebrow }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">{eyebrow}</p>}
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-text-secondary">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

/** One line of a settings list: what it is on the left, the control on the right. */
export function SettingRow({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-5 border-b border-border">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">{title}</p>
        <p className="text-sm text-text-secondary mt-1">{description}</p>
      </div>
      {children}
    </div>
  )
}

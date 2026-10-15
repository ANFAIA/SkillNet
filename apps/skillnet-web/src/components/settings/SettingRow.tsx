import { InfoTooltip } from '../ui'

/** One line of a settings list: what it is on the left, the control on the right. */
export function SettingRow({
  title,
  description,
  info,
  children,
}: {
  title: string
  description?: string
  /** Detail kept out of the page: shown only when the (i) next to the title is pressed. */
  info?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-3">
      <div className="min-w-0">
        <p className="flex items-center text-sm font-medium text-text">
          {title}
          {info && <InfoTooltip text={info} />}
        </p>
        {description && <p className="text-sm text-text-secondary mt-1 max-w-md">{description}</p>}
      </div>
      {children}
    </div>
  )
}

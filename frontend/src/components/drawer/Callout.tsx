import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export function Callout({
  icon: Icon,
  children,
  actions,
  tone,
}: {
  icon: LucideIcon
  children: ReactNode
  actions?: ReactNode
  /** CSS custom property name for the icon colour, e.g. `--stage-in-progress`. */
  tone?: string
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Icon className="mt-[0.2rem] size-4 shrink-0" style={tone ? { color: `var(${tone})` } : undefined} aria-hidden />
        <div className="min-w-0 text-body text-foreground">{children}</div>
      </div>
      {actions ? <div className="flex flex-wrap gap-2 max-sm:pl-7">{actions}</div> : null}
    </div>
  )
}

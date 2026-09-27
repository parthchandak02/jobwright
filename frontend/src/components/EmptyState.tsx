import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Props = {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  /** One primary action (plus an optional secondary). */
  action?: ReactNode
  /** Extra content under the action, e.g. a progress bar. */
  children?: ReactNode
  /** `inline` for lists and panels, `page` adds more vertical room. */
  size?: 'inline' | 'page'
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, children, size = 'inline', className }: Props) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        'mx-auto flex max-w-sm flex-col items-center text-center',
        size === 'page' ? 'py-16 md:py-24' : 'py-10',
        className,
      )}
    >
      {Icon ? <Icon className="mb-4 size-10 text-subtle-foreground" strokeWidth={1.5} aria-hidden /> : null}
      <h3 className="text-subheading text-foreground">{title}</h3>
      {description ? <p className="mt-1.5 text-body text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
      {children ? <div className="mt-4 w-full">{children}</div> : null}
    </div>
  )
}

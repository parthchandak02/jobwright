import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Props = {
  title?: ReactNode
  children: ReactNode
  className?: string
  /** First block has no top border */
  first?: boolean
}

export function DrawerSection({ title, children, className, first }: Props) {
  return (
    <section
      className={cn(
        'space-y-3 py-5',
        !first && 'border-t border-border/60',
        className,
      )}
    >
      {title ? (
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
      ) : null}
      {children}
    </section>
  )
}

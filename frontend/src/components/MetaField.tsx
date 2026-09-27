import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  icon?: LucideIcon
  empty: string
  value?: string | null
  className?: string
}

export function MetaField({ icon: Icon, empty, value, className }: Props) {
  const hasValue = value != null && value.trim() !== ''
  return (
    <div className={cn('job-card-meta-row', className)}>
      {Icon && <Icon className="size-3 shrink-0 text-muted-foreground" />}
      {hasValue ? (
        <span className="truncate text-foreground">{value}</span>
      ) : (
        <span className="truncate text-muted-foreground">{empty}</span>
      )}
    </div>
  )
}

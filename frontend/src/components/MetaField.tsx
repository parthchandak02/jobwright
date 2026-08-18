import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  icon?: LucideIcon
  label: string
  value?: string | null
  className?: string
}

export function MetaField({ icon: Icon, label, value, className }: Props) {
  const hasValue = value != null && value.trim() !== ''
  return (
    <div className={cn('flex items-center gap-1.5 text-[11px] leading-tight', className)}>
      {Icon && <Icon className="size-3 shrink-0 text-muted-foreground" />}
      {hasValue ? (
        <span className="truncate text-foreground">{value}</span>
      ) : (
        <span className="truncate text-muted-foreground">
          {label}: <span className="font-medium">NA</span>
        </span>
      )}
    </div>
  )
}

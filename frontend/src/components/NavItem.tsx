import type { CSSProperties } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { laneTone } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  active: boolean
  label: string
  count: number
  icon: LucideIcon
  onClick: () => void
  stage?: string
  countVariant?: 'secondary' | 'outline'
}

export function NavItem({
  active,
  label,
  count,
  icon: Icon,
  onClick,
  stage,
  countVariant = 'outline',
}: Props) {
  const lane = stage ? laneTone(stage) : undefined

  return (
    <button
      type="button"
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      className={cn(
        'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
        active
          ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
          : 'hover:bg-sidebar-accent/60',
      )}
      onClick={onClick}
    >
      <Icon className={cn('size-4 shrink-0', lane && 'text-[color:var(--lane)]')} />
      <span
        className={cn(
          'min-w-0 flex-1 truncate text-left',
          lane && 'text-xs font-bold uppercase tracking-wider text-[color:var(--lane)]',
        )}
      >
        {label}
      </span>
      {lane ? (
        <span className="shrink-0 text-xs font-semibold tabular-nums text-[color:var(--lane)]/70">
          {count}
        </span>
      ) : (
        <Badge variant={countVariant}>{count}</Badge>
      )}
    </button>
  )
}

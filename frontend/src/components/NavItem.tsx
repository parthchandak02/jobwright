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
      aria-current={active ? 'page' : undefined}
      aria-label={`${label}, ${count}`}
      className={cn(
        'flex items-center gap-2 overflow-hidden rounded-md px-3 py-2 text-sm transition-colors duration-(--dur-1) max-md:min-h-11',
        active
          ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
          : 'text-sidebar-foreground hover:bg-sidebar-accent/60',
      )}
      onClick={onClick}
    >
      <span className="relative shrink-0">
        <Icon className={cn('size-4', active ? 'text-current' : 'text-muted-foreground')} aria-hidden />
        {lane ? (
          <span
            aria-hidden
            className="absolute -right-0.5 -bottom-0.5 size-1.5 rounded-full bg-(--lane) ring-2 ring-sidebar"
          />
        ) : null}
      </span>
      <span
        className={cn(
          'sidebar-label flex-1 text-left',
          lane && 'lane-label text-micro font-semibold tracking-wide uppercase',
        )}
      >
        {label}
      </span>
      {lane ? (
        <span className="sidebar-label shrink-0 text-micro font-medium text-muted-foreground tabular-nums">{count}</span>
      ) : (
        <span className="sidebar-label shrink-0">
          <Badge variant={countVariant}>{count}</Badge>
        </span>
      )}
    </button>
  )
}

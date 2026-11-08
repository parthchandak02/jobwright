import type { CSSProperties } from 'react'
import type { LucideIcon } from 'lucide-react'
import { laneTone } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  active: boolean
  label: string
  count: number
  icon: LucideIcon
  onClick: () => void
  /** A board stage: adds the 6px lane dot on the icon. */
  stage?: string
}

/** Sidebar row: neutral icon (+ lane dot for stages), Title Case label, muted count. */
export function NavItem({ active, label, count, icon: Icon, onClick, stage }: Props) {
  const lane = stage ? laneTone(stage) : undefined

  return (
    <button
      type="button"
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      aria-current={active ? 'page' : undefined}
      aria-label={`${label}, ${count}`}
      className={cn(
        'flex items-center gap-2 overflow-hidden rounded-md px-3 py-2 text-body transition-colors duration-(--dur-1) max-md:min-h-11',
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
      <span className="sidebar-label min-w-0 flex-1 truncate text-left">{label}</span>
      <span
        className={cn(
          'sidebar-label shrink-0 text-caption tabular-nums',
          active ? 'text-sidebar-accent-foreground' : 'text-muted-foreground',
        )}
      >
        {count}
      </span>
    </button>
  )
}

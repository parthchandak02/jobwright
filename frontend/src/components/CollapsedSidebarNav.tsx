import type { CSSProperties } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { BoardResponse, laneTone, Profile, STAGE_LABELS } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  className?: string
}

function CollapsedNavItem({
  active,
  label,
  count,
  icon: Icon,
  onClick,
  stage,
}: {
  active: boolean
  label: string
  count: number
  icon: LucideIcon
  onClick: () => void
  stage?: string
}) {
  const lane = stage ? laneTone(stage) : undefined
  const displayLabel = stage ? label.toUpperCase() : label

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
          className={cn(
            'flex w-full flex-col items-center gap-0.5 rounded-md px-1 py-2 transition-colors',
            active
              ? 'bg-sidebar-accent text-sidebar-accent-foreground'
              : 'text-sidebar-foreground hover:bg-sidebar-accent/60',
          )}
          aria-label={`${displayLabel} (${count})`}
        >
          <Icon className={cn('size-4 shrink-0', lane && 'text-[color:var(--lane)]')} />
          <span
            className={cn(
              'text-[10px] font-medium leading-none tabular-nums',
              lane && 'font-semibold text-[color:var(--lane)]/70',
            )}
          >
            {count}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">{displayLabel}</TooltipContent>
    </Tooltip>
  )
}

export function CollapsedSidebarNav({
  profile,
  board,
  filterStage,
  onFilterStage,
  className,
}: Props) {
  const stages = board?.stages || Object.keys(STAGE_LABELS)

  return (
    <nav className={cn('flex flex-col gap-0.5 p-1.5', className)}>
      <CollapsedNavItem
        active={filterStage === 'all'}
        label="ALL"
        count={board?.total ?? 0}
        icon={NAV_ICONS.all}
        onClick={() => onFilterStage('all')}
      />
      {stages.map((stage) => (
        <CollapsedNavItem
          key={stage}
          active={filterStage === stage}
          label={STAGE_LABELS[stage] || stage}
          stage={stage}
          count={profile?.stage_counts?.[stage] ?? board?.columns?.[stage]?.length ?? 0}
          icon={NAV_ICONS[stage] || Inbox}
          onClick={() => onFilterStage(stage)}
        />
      ))}
    </nav>
  )
}

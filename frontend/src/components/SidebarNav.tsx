import { Inbox } from 'lucide-react'
import { NavItem } from '@/components/NavItem'
import { BoardResponse, Profile, STAGE_LABELS } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  onNavigate?: () => void
  className?: string
}

export function SidebarNav({
  profile,
  board,
  filterStage,
  onFilterStage,
  onNavigate,
  className,
}: Props) {
  const stages = board?.stages || Object.keys(STAGE_LABELS)

  function select(stage: string | 'all') {
    onFilterStage(stage)
    onNavigate?.()
  }

  return (
    <nav className={cn('flex flex-col gap-0.5 p-2', className)}>
      <NavItem
        active={filterStage === 'all'}
        label="ALL"
        count={board?.total ?? 0}
        icon={NAV_ICONS.all}
        countVariant="secondary"
        onClick={() => select('all')}
      />
      {stages.map((stage) => (
        <NavItem
          key={stage}
          active={filterStage === stage}
          label={STAGE_LABELS[stage] || stage}
          stage={stage}
          count={profile?.stage_counts?.[stage] ?? board?.columns?.[stage]?.length ?? 0}
          icon={NAV_ICONS[stage] || Inbox}
          onClick={() => select(stage)}
        />
      ))}
    </nav>
  )
}

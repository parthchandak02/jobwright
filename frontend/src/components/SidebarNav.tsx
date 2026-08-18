import { NavItem } from '@/components/NavItem'
import { BoardResponse, Profile, STAGE_LABELS } from '@/lib/api'

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  onNavigate?: () => void
}

export function SidebarNav({ profile, board, filterStage, onFilterStage, onNavigate }: Props) {
  const stages = board?.stages || Object.keys(STAGE_LABELS)

  function select(stage: string | 'all') {
    onFilterStage(stage)
    onNavigate?.()
  }

  return (
    <nav className="flex flex-col gap-0.5 p-2">
      <NavItem
        active={filterStage === 'all'}
        label="All jobs"
        count={board?.total ?? 0}
        countVariant="secondary"
        onClick={() => select('all')}
      />
      {stages.map((stage) => (
        <NavItem
          key={stage}
          active={filterStage === stage}
          label={STAGE_LABELS[stage] || stage}
          count={profile?.stage_counts?.[stage] ?? board?.columns?.[stage]?.length ?? 0}
          onClick={() => select(stage)}
        />
      ))}
    </nav>
  )
}

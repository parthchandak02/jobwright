import { Briefcase } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { SidebarNav } from '@/components/SidebarNav'
import { BoardResponse, Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  collapsed: boolean
}

export function AppSidebar({
  profile,
  board,
  filterStage,
  onFilterStage,
  collapsed,
}: Props) {
  return (
    <aside
      className={cn(
        'hidden shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar/70 text-sidebar-foreground backdrop-blur-xl transition-[width] duration-200 md:flex',
        collapsed ? 'w-0 border-r-0' : 'w-56',
      )}
      aria-hidden={collapsed}
    >
      <div className="flex w-56 items-center gap-2 px-4 py-4">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Briefcase className="size-4" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">jobwright</p>
          <p className="truncate text-xs text-muted-foreground">
            {profile?.name || profile?.user_id || '…'}
          </p>
        </div>
      </div>
      <Separator className="w-56" />
      <SidebarNav
        profile={profile}
        board={board}
        filterStage={filterStage}
        onFilterStage={onFilterStage}
      />
    </aside>
  )
}

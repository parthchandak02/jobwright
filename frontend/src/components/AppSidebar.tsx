import { CircleUser, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { BrandLogo, APP_SHELL_HEADER_HEIGHT } from '@/components/BrandLogo'
import { CollapsedSidebarNav } from '@/components/CollapsedSidebarNav'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { SidebarNav } from '@/components/SidebarNav'
import { ThemeToggle } from '@/components/ThemeToggle'
import { BoardResponse, Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  collapsed: boolean
  onToggleSidebar: () => void
  profileActive: boolean
  onOpenProfile: () => void
}

export function AppSidebar({
  profile,
  board,
  filterStage,
  onFilterStage,
  collapsed,
  onToggleSidebar,
  profileActive,
  onOpenProfile,
}: Props) {
  return (
    <aside
      className={cn(
        'hidden h-full shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar/70 text-sidebar-foreground backdrop-blur-xl transition-[width] duration-200 md:flex',
        collapsed ? 'w-14' : 'w-56',
      )}
      aria-hidden={false}
    >
      {collapsed ? (
        <>
          <div className={cn(APP_SHELL_HEADER_HEIGHT, 'justify-center')}>
            <BrandLogo className="size-7" />
          </div>
          <CollapsedSidebarNav
            className="min-h-0 flex-1 overflow-y-auto"
            profile={profile}
            board={board}
            filterStage={filterStage}
            onFilterStage={onFilterStage}
          />
        </>
      ) : (
        <>
          <div className={cn(APP_SHELL_HEADER_HEIGHT, 'w-56 gap-2')}>
            <BrandLogo className="size-7" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold uppercase tracking-[0.14em]">
                jobwright
              </p>
            </div>
          </div>
          <SidebarNav
            className="min-h-0 flex-1 overflow-y-auto"
            profile={profile}
            board={board}
            filterStage={filterStage}
            onFilterStage={onFilterStage}
          />
        </>
      )}

      <div className="mt-auto flex shrink-0 flex-col gap-0.5 border-t border-sidebar-border p-2">
        <SidebarActionButton
          collapsed={collapsed}
          active={profileActive}
          icon={CircleUser}
          label={profile?.name || profile?.user_id || 'Profile'}
          onClick={onOpenProfile}
        />
        <ThemeToggle collapsed={collapsed} />
        <SidebarActionButton
          collapsed={collapsed}
          icon={collapsed ? PanelLeftOpen : PanelLeftClose}
          label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          onClick={onToggleSidebar}
        />
      </div>
    </aside>
  )
}

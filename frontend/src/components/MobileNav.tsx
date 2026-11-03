import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { Menu } from 'lucide-react'
import { ProfileSwitcher } from '@/components/ProfileSwitcher'
import { ShellNavActions } from '@/components/ShellNavActions'
import { SidebarNav } from '@/components/SidebarNav'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { BoardResponse, Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

type MobileNavState = { open: boolean; setOpen: (open: boolean) => void }

const MobileNavContext = createContext<MobileNavState | null>(null)

/** Owns the phone menu state so any page (via `PageHeader` / `MobileNavTrigger`) can open it. */
export function MobileNavProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const value = useMemo(() => ({ open, setOpen }), [open])
  return <MobileNavContext.Provider value={value}>{children}</MobileNavContext.Provider>
}

export function useMobileNav(): MobileNavState | null {
  return useContext(MobileNavContext)
}

/** Phone-only menu button. Renders nothing outside `MobileNavProvider` (e.g. Welcome). */
export function MobileNavTrigger({ className }: { className?: string }) {
  const nav = useMobileNav()
  if (!nav) return null
  return (
    <Button
      type="button"
      size="icon-sm"
      variant="ghost"
      onClick={() => nav.setOpen(true)}
      aria-label="Open menu"
      aria-expanded={nav.open}
      className={cn('md:hidden', className)}
    >
      <Menu />
    </Button>
  )
}

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
}

/** The phone navigation sheet: stages, Match quality, Admin (admins), Profile, theme. Render once in the app shell. */
export function MobileNav({ profile, board, filterStage, onFilterStage }: Props) {
  const nav = useMobileNav()
  if (!nav) return null
  const close = () => nav.setOpen(false)

  return (
    <Sheet open={nav.open} onOpenChange={nav.setOpen}>
      <SheetContent side="left" className="flex w-72 max-w-[85vw] flex-col gap-0 p-0">
        <SheetHeader className="border-b px-4 py-4 text-left">
          <SheetTitle className="truncate text-subheading">{profile?.name || 'jobwright'}</SheetTitle>
          <SheetDescription className="sr-only">Navigation</SheetDescription>
          <ProfileSwitcher className="mt-2 w-full" />
        </SheetHeader>
        <SidebarNav
          className="min-h-0 flex-1 overflow-y-auto"
          profile={profile}
          board={board}
          filterStage={filterStage}
          onFilterStage={(s) => {
            onFilterStage(s)
            close()
          }}
        />
        <div className="mt-auto flex flex-col gap-0.5 border-t border-border p-2 pb-[calc(0.5rem+var(--safe-bottom))]">
          <ShellNavActions onNavigate={close} />
        </div>
      </SheetContent>
    </Sheet>
  )
}

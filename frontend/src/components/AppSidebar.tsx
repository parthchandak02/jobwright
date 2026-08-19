import { useEffect, useRef, useState } from 'react'
import { CircleUser } from 'lucide-react'
import { Link } from 'react-router-dom'
import { BrandLogo, APP_SHELL_HEADER_HEIGHT } from '@/components/BrandLogo'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { SidebarNav } from '@/components/SidebarNav'
import { ThemeToggle } from '@/components/ThemeToggle'
import { BoardResponse, Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

const HOVER_OPEN_MS = 80
const HOVER_CLOSE_MS = 180

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  profileActive: boolean
  onOpenProfile: () => void
  /** Unpin when a job drawer opens (more room for the board). */
  jobOpen?: boolean
}

export function AppSidebar({
  profile,
  board,
  filterStage,
  onFilterStage,
  profileActive,
  onOpenProfile,
  jobOpen = false,
}: Props) {
  const [pinned, setPinned] = useState(false)
  const [hovered, setHovered] = useState(false)
  const rootRef = useRef<HTMLElement>(null)
  const openTimer = useRef(0)
  const closeTimer = useRef(0)
  const expanded = pinned || hovered

  function clearTimers() {
    window.clearTimeout(openTimer.current)
    window.clearTimeout(closeTimer.current)
  }

  function setHoverSoon(next: boolean, delay: number) {
    clearTimers()
    if (pinned) return
    const id = window.setTimeout(() => setHovered(next), delay)
    if (next) openTimer.current = id
    else closeTimer.current = id
  }

  useEffect(() => () => clearTimers(), [])

  useEffect(() => {
    if (!jobOpen) return
    clearTimers()
    setPinned(false)
    setHovered(false)
  }, [jobOpen])

  useEffect(() => {
    if (!pinned) return
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return
      clearTimers()
      setPinned(false)
      setHovered(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [pinned])

  useEffect(() => {
    if (!expanded) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      clearTimers()
      setPinned(false)
      setHovered(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  return (
    <>
      <div
        className="sidebar-spacer hidden h-full shrink-0 md:block"
        data-pinned={pinned ? 'true' : 'false'}
        aria-hidden
      />
      <aside
        ref={rootRef}
        data-expanded={expanded ? 'true' : 'false'}
        data-pinned={pinned ? 'true' : 'false'}
        onPointerEnter={() => setHoverSoon(true, HOVER_OPEN_MS)}
        onPointerLeave={() => setHoverSoon(false, HOVER_CLOSE_MS)}
        onFocusCapture={() => setHoverSoon(true, 0)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) {
            setHoverSoon(false, HOVER_CLOSE_MS)
          }
        }}
        onClick={() => {
          clearTimers()
          setPinned(true)
        }}
        className={cn(
          'group sidebar-shell absolute top-0 left-0 z-30 hidden h-full flex-col overflow-hidden border-r border-sidebar-border bg-sidebar/70 text-sidebar-foreground backdrop-blur-xl md:flex',
          expanded && !pinned && 'shadow-lg',
        )}
      >
        <div className={cn(APP_SHELL_HEADER_HEIGHT, 'w-[var(--sidebar-panel)] gap-2')}>
          <Link
            to="/"
            className="flex min-w-0 flex-1 items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            aria-label="Back to board"
            onClick={(event) => event.stopPropagation()}
          >
            <BrandLogo className="size-7" />
            <div className="sidebar-label min-w-0 flex-1">
              <p className="truncate text-sm font-semibold uppercase tracking-[0.14em]">
                jobwright
              </p>
            </div>
          </Link>
        </div>
        <SidebarNav
          className="min-h-0 w-[var(--sidebar-panel)] flex-1 overflow-y-auto"
          profile={profile}
          board={board}
          filterStage={filterStage}
          onFilterStage={onFilterStage}
        />
        <div className="mt-auto flex w-[var(--sidebar-panel)] shrink-0 flex-col gap-0.5 border-t border-sidebar-border p-2">
          <SidebarActionButton
            active={profileActive}
            icon={CircleUser}
            label={profile?.name || profile?.user_id || 'Profile'}
            onClick={onOpenProfile}
          />
          <ThemeToggle variant="sidebar" />
        </div>
      </aside>
    </>
  )
}

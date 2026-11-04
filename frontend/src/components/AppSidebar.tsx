import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandLogo, APP_SHELL_HEADER_HEIGHT } from '@/components/BrandLogo'
import { ProfileSwitcher } from '@/components/ProfileSwitcher'
import { ShellNavActions } from '@/components/ShellNavActions'
import { SidebarNav } from '@/components/SidebarNav'
import { BoardResponse, Profile } from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn } from '@/lib/utils'

const HOVER_OPEN_MS = 80
const HOVER_CLOSE_MS = 180

type Props = {
  profile: Profile | null
  board: BoardResponse | null
  filterStage: string | 'all'
  onFilterStage: (stage: string | 'all') => void
  /** Unpin when a job drawer opens (more room for the board). */
  jobOpen?: boolean
}

export function AppSidebar({
  profile,
  board,
  filterStage,
  onFilterStage,
  jobOpen = false,
}: Props) {
  const [pinned, setPinned] = useState(false)
  const [hovered, setHovered] = useState(false)
  // Keep the panel open while the profile menu (a portal outside the sidebar) is open.
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const { me } = useMe()
  // With several profiles the switcher shows the name, so the link says what it opens.
  const manyProfiles = (me?.profiles.length ?? 0) > 1
  const profileLabel = manyProfiles ? undefined : profile?.name || profile?.user_id || 'Profile'

  const rootRef = useRef<HTMLElement>(null)
  const openTimer = useRef(0)
  const closeTimer = useRef(0)
  const expanded = pinned || hovered || switcherOpen

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
      {/* Clicking anywhere in the rail pins it open: a mouse-only convenience. Keyboard users get the same
          panel through onFocusCapture (it stays open while focus is inside), and every control in it is a
          real button or link, so there is nothing a key handler on the <aside> would add. */}
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions */}
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
          'group sidebar-shell absolute top-0 left-0 z-30 hidden h-full flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground md:flex',
          expanded && !pinned && 'shadow-e2',
        )}
      >
        <div className={cn(APP_SHELL_HEADER_HEIGHT, 'w-[var(--sidebar-panel)] gap-2')}>
          <Link
            to="/"
            className="flex min-w-0 flex-1 items-center gap-2 rounded-md"
            aria-label="Back to board"
            onClick={(event) => event.stopPropagation()}
          >
            <BrandLogo className="size-7" />
            <div className="sidebar-label min-w-0 flex-1">
              <p className="truncate text-subheading tracking-tight">
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
          {/* Profile switcher (several profiles only): folds away in the icon rail. */}
          {manyProfiles ? (
            <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-(--dur-2) ease-out group-data-[expanded=false]:-mb-0.5 group-data-[expanded=true]:grid-rows-[1fr]">
              <div className="sidebar-label min-h-0">
                <div className="p-0.5 pb-1.5">
                  <ProfileSwitcher className="w-full" onOpenChange={setSwitcherOpen} />
                </div>
              </div>
            </div>
          ) : null}
          <ShellNavActions profileLabel={profileLabel} />
        </div>
      </aside>
    </>
  )
}

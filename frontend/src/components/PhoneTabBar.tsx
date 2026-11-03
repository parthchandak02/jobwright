import { useEffect, type CSSProperties } from 'react'
import { BriefcaseBusiness } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SHELL_LINKS, type ShellLink } from '@/components/ShellNavActions'
import { useMe } from '@/lib/me'
import { cn } from '@/lib/utils'

const BOARD_SEARCH_KEY = 'jobwright-board-search'

const JOBS_TAB: ShellLink = { path: '/', label: 'Jobs', tabLabel: 'Jobs', icon: BriefcaseBusiness }

function isActive(link: ShellLink, pathname: string) {
  if (link.path === '/') return pathname === '/' || pathname.startsWith('/jobs/')
  return pathname.startsWith(link.path)
}

/**
 * Phone bottom navigation (under 768px): Jobs, then `SHELL_LINKS` (admin-only ones for admins).
 * 56px plus the safe area; render as the last child of the app shell's column so pages end above it.
 * The board's stage filter and view are kept when coming back to Jobs.
 */
export function PhoneTabBar({ className }: { className?: string }) {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const { me } = useMe()
  const links = [JOBS_TAB, ...SHELL_LINKS.filter((link) => !link.adminOnly || me?.is_admin)]

  useEffect(() => {
    if (pathname === '/') sessionStorage.setItem(BOARD_SEARCH_KEY, search)
  }, [pathname, search])

  return (
    <nav
      aria-label="Main"
      // The bar owns the bottom safe area; it re-reads the inset because the shell zeroes it for pages above.
      style={{ '--safe-bottom': 'env(safe-area-inset-bottom, 0px)' } as CSSProperties}
      className={cn('flex shrink-0 border-t border-border bg-background pb-(--safe-bottom) md:hidden', className)}
    >
      {links.map((link) => {
        const active = isActive(link, pathname)
        const Icon = link.icon
        return (
          <button
            key={link.path}
            type="button"
            aria-current={active ? 'page' : undefined}
            onClick={() => {
              if (link.path === '/') {
                if (pathname !== '/') navigate(`/${sessionStorage.getItem(BOARD_SEARCH_KEY) || ''}`)
              } else if (!active) navigate(link.path)
            }}
            className={cn(
              'flex h-14 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-micro transition-colors duration-(--dur-1) ease-out focus-visible:outline-offset-[-2px]',
              active ? 'font-medium text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="size-5" strokeWidth={active ? 2.25 : 1.75} aria-hidden />
            <span className="max-w-full truncate px-1">{link.tabLabel}</span>
          </button>
        )
      })}
    </nav>
  )
}

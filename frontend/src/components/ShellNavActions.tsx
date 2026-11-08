import { CircleUser, Gauge, Layers, MessagesSquare, Shield, type LucideIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { ThemeToggle } from '@/components/ThemeToggle'
import { useMe } from '@/lib/me'
import { isLinkActive, type NavLinkShape } from '@/lib/shellNav'

export type ShellLink = NavLinkShape & {
  label: string
  /** Short label under the icon in the phone tab bar. */
  tabLabel: string
  icon: LucideIcon
  adminOnly?: boolean
}

/**
 * The app's page links. Single source for the desktop sidebar (below the stage list) and the
 * phone tab bar (after Jobs, in this order). Add a page here in one line.
 */
export const SHELL_LINKS: ShellLink[] = [
  { path: '/review', label: 'Quick review', tabLabel: 'Review', icon: Layers },
  { path: '/quality', label: 'Match quality', tabLabel: 'Quality', icon: Gauge },
  { path: '/admin', label: 'Admin', tabLabel: 'Admin', icon: Shield, adminOnly: true },
  {
    path: '/profile',
    search: '?tab=claude',
    label: 'Use with Claude',
    tabLabel: 'Claude',
    icon: MessagesSquare,
    // Phones keep at most 5 tabs (admins already have 5); Settings → Claude is one tap away there.
    phoneOptional: true,
  },
  { path: '/profile', label: 'Profile & settings', tabLabel: 'Settings', icon: CircleUser },
]

type Props = {
  /** Label for the Profile link (the desktop sidebar shows the profile's name). */
  profileLabel?: string
  /** Called after navigating. */
  onNavigate?: () => void
}

export function ShellNavActions({ profileLabel, onNavigate }: Props) {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const { me } = useMe()
  const links = SHELL_LINKS.filter((link) => !link.adminOnly || me?.is_admin)

  return (
    <>
      {links.map((link) => (
        <SidebarActionButton
          key={link.path + (link.search ?? '')}
          active={isLinkActive(link, pathname, search, links)}
          icon={link.icon}
          label={link.path === '/profile' && !link.search && profileLabel ? profileLabel : link.label}
          onClick={() => {
            navigate(link.path + (link.search ?? ''))
            onNavigate?.()
          }}
        />
      ))}
      <ThemeToggle variant="sidebar" />
    </>
  )
}

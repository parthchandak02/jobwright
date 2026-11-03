import { CircleUser, Gauge, Layers, Shield, type LucideIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { ThemeToggle } from '@/components/ThemeToggle'
import { useMe } from '@/lib/me'

export type ShellLink = {
  path: string
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
  const { pathname } = useLocation()
  const { me } = useMe()

  return (
    <>
      {SHELL_LINKS.filter((link) => !link.adminOnly || me?.is_admin).map((link) => (
        <SidebarActionButton
          key={link.path}
          active={pathname.startsWith(link.path)}
          icon={link.icon}
          label={link.path === '/profile' && profileLabel ? profileLabel : link.label}
          onClick={() => {
            navigate(link.path)
            onNavigate?.()
          }}
        />
      ))}
      <ThemeToggle variant="sidebar" />
    </>
  )
}

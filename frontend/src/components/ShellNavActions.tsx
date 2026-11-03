import { CircleUser, Gauge, Layers, Shield, type LucideIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { ThemeToggle } from '@/components/ThemeToggle'
import { useMe } from '@/lib/me'

type ShellLink = {
  path: string
  label: string
  icon: LucideIcon
  adminOnly?: boolean
}

/** The app's page links below the stage list. Single source for the desktop sidebar and the phone menu. */
export const SHELL_LINKS: ShellLink[] = [
  { path: '/review', label: 'Quick review', icon: Layers },
  { path: '/quality', label: 'Match quality', icon: Gauge },
  { path: '/admin', label: 'Admin', icon: Shield, adminOnly: true },
  { path: '/profile', label: 'Profile & settings', icon: CircleUser },
]

type Props = {
  /** Label for the Profile link (the desktop sidebar shows the profile's name). */
  profileLabel?: string
  /** Called after navigating (the phone menu closes itself). */
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

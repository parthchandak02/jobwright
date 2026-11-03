import { Monitor, Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { useTheme, type ThemePreference } from '@/lib/theme'

type Props = {
  variant?: 'sidebar'
}

const ICONS = { light: Sun, dark: Moon, system: Monitor } as const
const LABELS: Record<ThemePreference, string> = {
  light: 'Light theme',
  dark: 'Dark theme',
  system: 'System theme',
}
const NEXT_LABEL: Record<ThemePreference, string> = {
  light: 'dark',
  dark: 'system (follows your device)',
  system: 'light',
}

/** Cycles Light → Dark → System. System follows the device setting. */
export function ThemeToggle({ variant }: Props) {
  const { preference, cycleTheme } = useTheme()
  const Icon = ICONS[preference]
  const label = LABELS[preference]
  const hint = `${label}. Switch to ${NEXT_LABEL[preference]}`

  if (variant === 'sidebar') {
    return <SidebarActionButton icon={Icon} label={label} title={hint} onClick={cycleTheme} />
  }

  return (
    <Button type="button" size="icon-sm" variant="ghost" onClick={cycleTheme} title={hint} aria-label={hint}>
      <Icon />
    </Button>
  )
}

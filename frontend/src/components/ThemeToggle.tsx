import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { useTheme } from '@/lib/theme'

type Props = {
  collapsed?: boolean
}

export function ThemeToggle({ collapsed }: Props) {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  if (collapsed !== undefined) {
    return (
      <SidebarActionButton
        collapsed={collapsed}
        icon={isDark ? Moon : Sun}
        label={isDark ? 'Dark theme' : 'Light theme'}
        onClick={toggleTheme}
      />
    )
  }

  return (
    <Button
      type="button"
      size="icon-sm"
      variant="ghost"
      onClick={toggleTheme}
      title={isDark ? 'Dark theme (click for light)' : 'Light theme (click for dark)'}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {isDark ? <Moon /> : <Sun />}
    </Button>
  )
}

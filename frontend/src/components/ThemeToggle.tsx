import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/lib/theme'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

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

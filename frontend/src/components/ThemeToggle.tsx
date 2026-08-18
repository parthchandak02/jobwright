import { Moon, Sun, Monitor } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme, type Theme } from '@/lib/theme'

const LABELS: Record<Theme, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
}

export function ThemeToggle() {
  const { theme, cycleTheme } = useTheme()
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor

  return (
    <Button
      type="button"
      size="icon-sm"
      variant="ghost"
      onClick={cycleTheme}
      title={`Theme: ${LABELS[theme]} (click to cycle)`}
      aria-label={`Theme ${LABELS[theme]}. Click to cycle light, dark, system.`}
    >
      <Icon />
    </Button>
  )
}

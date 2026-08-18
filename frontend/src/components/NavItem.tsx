import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type Props = {
  active: boolean
  label: string
  count: number
  onClick: () => void
  countVariant?: 'secondary' | 'outline'
}

export function NavItem({
  active,
  label,
  count,
  onClick,
  countVariant = 'outline',
}: Props) {
  return (
    <button
      type="button"
      className={cn(
        'flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors',
        active
          ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
          : 'hover:bg-sidebar-accent/60',
      )}
      onClick={onClick}
    >
      {label}
      <Badge variant={countVariant}>{count}</Badge>
    </button>
  )
}

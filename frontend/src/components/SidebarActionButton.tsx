import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  icon: LucideIcon
  label: string
  onClick: () => void
  active?: boolean
}

export function SidebarActionButton({
  icon: Icon,
  label,
  onClick,
  active = false,
}: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent/60',
        active && 'bg-sidebar-accent/70 font-medium',
      )}
    >
      <Icon className="size-4 shrink-0" />
      <span className="sidebar-label flex-1 text-left">{label}</span>
    </button>
  )
}

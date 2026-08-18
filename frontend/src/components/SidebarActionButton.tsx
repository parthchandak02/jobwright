import type { LucideIcon } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type Props = {
  icon: LucideIcon
  label: string
  onClick: () => void
  collapsed?: boolean
  active?: boolean
}

export function SidebarActionButton({
  icon: Icon,
  label,
  onClick,
  collapsed = false,
  active = false,
}: Props) {
  const button = (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex w-full items-center gap-2 rounded-md text-sm transition-colors hover:bg-sidebar-accent/60',
        active && 'bg-sidebar-accent/70 font-medium',
        collapsed ? 'justify-center px-1 py-2' : 'px-3 py-2',
      )}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span className="min-w-0 flex-1 truncate text-left">{label}</span>}
    </button>
  )

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    )
  }

  return button
}

import type { LucideIcon } from 'lucide-react'
import { Loader2, MoreHorizontal } from 'lucide-react'
import { Button, type ButtonProps } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

export type DrawerAction = {
  key: string
  label: string
  short: string
  icon: LucideIcon
  variant: NonNullable<ButtonProps['variant']>
  href?: string
  onClick?: () => void
  disabled?: boolean
  busy?: boolean
}

export function ActionButton({ action, className, compact }: { action: DrawerAction; className?: string; compact?: boolean }) {
  const Icon = action.busy ? Loader2 : action.icon
  const content = (
    <>
      <Icon className={cn(action.busy && 'animate-spin')} aria-hidden />
      <span className={cn(compact && 'truncate')}>{compact ? action.short : action.label}</span>
    </>
  )
  const cls = cn(compact && 'h-14 min-w-0 flex-1 flex-col gap-1 px-1 text-micro has-[>svg]:px-1', className)
  if (action.href) {
    return (
      <Button asChild variant={action.variant} className={cls}>
        <a href={action.href} target="_blank" rel="noreferrer" aria-label={compact ? action.label : undefined}>
          {content}
        </a>
      </Button>
    )
  }
  return (
    <Button
      type="button"
      variant={action.variant}
      className={cls}
      disabled={action.disabled}
      onClick={action.onClick}
      aria-label={compact ? action.label : undefined}
    >
      {content}
    </Button>
  )
}

/** Inline action row (desktop; hidden on phone where PhoneActionBar takes over). */
export function DesktopActions({ actions }: { actions: DrawerAction[] }) {
  if (!actions.length) return null
  return (
    <div className="hidden flex-wrap gap-2 md:flex">
      {actions.map((a) => (
        <ActionButton key={a.key} action={a} />
      ))}
    </div>
  )
}

/** Sticky bottom bar on phone: up to four actions, the rest under More. */
export function PhoneActionBar({ actions }: { actions: DrawerAction[] }) {
  if (!actions.length) return null
  const lead = actions.find((a) => a.variant === 'ai' || a.variant === 'primary')
  const shown = actions.length > 4 ? actions.slice(0, 3) : actions
  const more = actions.length > 4 ? actions.slice(3) : []
  return (
    <div className="flex shrink-0 gap-1 border-t border-border bg-background px-2 pt-1.5 pb-[calc(0.375rem+var(--safe-bottom))] shadow-e1 md:hidden">
      {shown.map((a) => (
        <ActionButton key={a.key} action={a === lead ? a : { ...a, variant: 'ghost' }} compact />
      ))}
      {more.length ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" className="h-14 flex-1 flex-col gap-1 px-1 text-micro">
              <MoreHorizontal aria-hidden /> More
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top">
            {more.map((a) => (
              <DropdownMenuItem key={a.key} disabled={a.disabled} onSelect={() => a.onClick?.()}>
                <a.icon /> {a.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  )
}

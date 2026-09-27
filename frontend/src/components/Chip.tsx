import type { LucideIcon } from 'lucide-react'
import { X } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type ChipProps = {
  children: ReactNode
  icon?: LucideIcon
  /** Muted label (NA / empty states). */
  muted?: boolean
  /** CSS custom property for a semantic tint, e.g. `--stage-applied`, `--destructive`, `--success`. */
  tone?: string
  iconClassName?: string
  title?: string
  className?: string
  /** `sm`: dense status pill (board, table, drawer). `md`: 28px (32px on phone) value chip for forms. */
  size?: 'sm' | 'md'
  /** Renders a remove control with a 32px hit area. */
  onRemove?: () => void
  removeLabel?: string
  /** Extra control after the label, e.g. a DropdownMenu trigger. Keep it an icon, never a second label. */
  trailing?: ReactNode
}

function removeAriaLabel(children: ReactNode, removeLabel?: string): string {
  if (removeLabel) return removeLabel
  if (typeof children === 'string') return children
  return 'item'
}

export function Chip({
  children,
  icon: Icon,
  muted,
  tone,
  iconClassName,
  title,
  className,
  size = 'sm',
  onRemove,
  removeLabel,
  trailing,
}: ChipProps) {
  const toneStyle = tone ? ({ '--tone': `var(${tone})` } as CSSProperties) : undefined

  return (
    <span
      data-slot="chip"
      className={cn(
        'border',
        size === 'sm'
          ? 'job-card-chip'
          : 'inline-flex h-8 max-w-full items-center gap-1.5 rounded-full px-3 text-micro md:h-7 md:px-2.5',
        tone ? 'tone-tint' : 'border-border bg-surface-muted',
        !tone && (muted ? 'text-muted-foreground' : 'text-foreground'),
        onRemove && (size === 'sm' ? 'pr-1.5' : 'pr-2 md:pr-1.5'),
        className,
      )}
      style={toneStyle}
      title={title}
    >
      {Icon && (
        <Icon className={cn('size-3 shrink-0', !tone && 'text-muted-foreground', iconClassName)} aria-hidden />
      )}
      <span className={cn('min-w-0', typeof children === 'string' && 'truncate')}>{children}</span>
      {trailing}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className={cn(
            'relative ml-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full transition-colors duration-(--dur-1) after:absolute after:-inset-2 focus-visible:outline-offset-0',
            tone
              ? 'text-current/70 hover:bg-current/15 hover:text-current'
              : 'text-muted-foreground hover:bg-foreground/10 hover:text-foreground',
          )}
          aria-label={`Remove ${removeAriaLabel(children, removeLabel)}`}
        >
          <X className="size-3" aria-hidden />
        </button>
      )}
    </span>
  )
}

export function ValueChip(props: Omit<ChipProps, 'size'>) {
  return <Chip {...props} size="md" />
}

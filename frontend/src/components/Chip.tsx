import type { LucideIcon } from 'lucide-react'
import { X } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Props = {
  children: ReactNode
  icon?: LucideIcon
  /** Render label in muted color (for NA / empty states). */
  muted?: boolean
  /** CSS custom-property token (e.g. --stage-applied) for lane-tinted chips. */
  tone?: string
  /** Extra classes for the leading icon only (e.g. semantic status color). */
  iconClassName?: string
  /** Native title for hover tooltip / accessibility. */
  title?: string
  className?: string
  /** When set, renders a small remove control. */
  onRemove?: () => void
  /** Accessible label for remove (defaults to string children). */
  removeLabel?: string
}

/**
 * Reusable status pill for job cards, table rows, and drawer metadata.
 * Always icon-led; use `tone` for lane-colored stage chips.
 */
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
  onRemove,
  removeLabel,
}: Props) {
  const toneStyle: CSSProperties | undefined = tone
    ? {
        borderColor: `color-mix(in srgb, var(${tone}) 42%, transparent)`,
        backgroundColor: `color-mix(in srgb, var(${tone}) 16%, transparent)`,
        color: `var(${tone})`,
      }
    : undefined

  return (
    <span
      className={cn(
        'job-card-chip border',
        tone
          ? 'font-semibold backdrop-blur-sm'
          : 'border-border/60 bg-background/40 backdrop-blur-sm',
        muted && !tone ? 'text-muted-foreground' : !tone ? 'text-foreground' : undefined,
        className,
      )}
      style={toneStyle}
      title={title}
    >
      {Icon && (
        <Icon
          className={cn('size-3 shrink-0', !tone && 'text-muted-foreground', iconClassName)}
          aria-hidden
        />
      )}
      <span className={cn('min-w-0', typeof children === 'string' && 'truncate')}>{children}</span>
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className={cn(
            '-mr-0.5 ml-0.5 inline-flex shrink-0 rounded-full p-0.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
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

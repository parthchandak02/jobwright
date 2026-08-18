import type { LucideIcon } from 'lucide-react'
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
}

/**
 * Reusable status pill for job cards, table rows, and drawer metadata.
 * Always icon-led; use `tone` for lane-colored stage chips.
 */
export function Chip({ children, icon: Icon, muted, tone, iconClassName, title, className }: Props) {
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
      <span className="truncate">{children}</span>
    </span>
  )
}

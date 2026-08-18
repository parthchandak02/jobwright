import { Pencil } from 'lucide-react'
import { scoreBadgeStyle, scoreTextStyle } from '@/lib/scoreColor'
import { cn } from '@/lib/utils'

type Props = {
  score: number | null | undefined
  className?: string
  /** Compact chip (kanban) vs inline table text */
  variant?: 'chip' | 'text'
  /** User overrode the AI score */
  userModified?: boolean
}

export function ScoreBadge({ score, className, variant = 'chip', userModified }: Props) {
  const label = score ?? '—'

  if (variant === 'text') {
    return (
      <span
        className={cn(
          'font-semibold',
          score == null && 'text-muted-foreground',
          className,
        )}
        style={scoreTextStyle(score)}
      >
        {label}
        {userModified ? <span className="ml-1 text-[10px] opacity-70">*</span> : null}
      </span>
    )
  }

  return (
    <span
      className={cn(
        'relative inline-flex h-6 min-w-6 items-center justify-center rounded-lg text-xs font-bold tabular-nums',
        'backdrop-blur-sm transition-[box-shadow,transform] duration-200',
        score == null &&
          'bg-muted/60 text-muted-foreground shadow-[inset_0_0_0_1px_oklch(0.5_0_0/0.12)] dark:bg-muted/40',
        userModified && 'ring-2 ring-primary/50 ring-offset-1 ring-offset-background',
        className,
      )}
      style={scoreBadgeStyle(score)}
    >
      {label}
      {userModified ? (
        <Pencil
          className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full bg-primary p-0.5 text-primary-foreground shadow-sm"
          aria-hidden
        />
      ) : null}
    </span>
  )
}

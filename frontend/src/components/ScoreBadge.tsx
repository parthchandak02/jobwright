import { cn } from '@/lib/utils'

type Props = {
  score: number | null | undefined
  className?: string
  /** Compact chip (kanban) vs inline table text */
  variant?: 'chip' | 'text'
}

export function scoreTone(score: number | null | undefined) {
  if (score == null) return 'muted' as const
  if (score >= 8) return 'high' as const
  if (score >= 7) return 'mid' as const
  return 'low' as const
}

const CHIP: Record<ReturnType<typeof scoreTone>, string> = {
  muted: 'bg-muted text-muted-foreground ring-black/5 dark:ring-white/10',
  high: 'bg-emerald-600 text-white ring-white/25 dark:bg-emerald-500',
  mid: 'bg-sky-600 text-white ring-white/25 dark:bg-sky-500',
  low: 'bg-amber-500 text-white ring-white/25 dark:bg-amber-500',
}

const TEXT: Record<ReturnType<typeof scoreTone>, string> = {
  muted: 'text-muted-foreground',
  high: 'font-semibold text-emerald-700 dark:text-emerald-400',
  mid: 'font-semibold text-sky-700 dark:text-sky-400',
  low: 'font-semibold text-amber-700 dark:text-amber-400',
}

export function ScoreBadge({ score, className, variant = 'chip' }: Props) {
  const tone = scoreTone(score)
  const label = score ?? '—'

  if (variant === 'text') {
    return <span className={cn(TEXT[tone], className)}>{label}</span>
  }

  return (
    <span
      className={cn(
        'inline-flex h-6 min-w-6 items-center justify-center rounded-md text-xs font-bold shadow-sm ring-1 ring-inset',
        CHIP[tone],
        className,
      )}
    >
      {label}
    </span>
  )
}

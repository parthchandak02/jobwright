import { FUNNEL_STAGES, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  disabled?: boolean
  onMove: (toStage: string) => void
  className?: string
}

/** Every lane in one row; tap any to move there (scrolls on narrow screens). */
export function StagePicker({ stage, disabled, onMove, className }: Props) {
  return (
    <div className={cn('-mx-1 flex gap-1 overflow-x-auto px-1 pb-1', className)} role="radiogroup" aria-label="Stage">
      {FUNNEL_STAGES.map((s) => {
        const active = s === stage
        const tone = laneTone(s)
        return (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled || active}
            onClick={() => onMove(s)}
            className={cn(
              'shrink-0 rounded-md border px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-default',
              active ? 'shadow-sm' : 'border-transparent hover:border-border/60 hover:bg-accent/50',
            )}
            style={
              active
                ? { color: tone, borderColor: `color-mix(in srgb, ${tone} 45%, transparent)`, backgroundColor: `color-mix(in srgb, ${tone} 12%, transparent)` }
                : { color: `color-mix(in srgb, ${tone} 75%, var(--muted-foreground))` }
            }
          >
            {STAGE_LABELS[s] || s}
          </button>
        )
      })}
    </div>
  )
}

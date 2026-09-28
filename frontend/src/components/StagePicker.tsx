import type { CSSProperties } from 'react'
import { FUNNEL_STAGES, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  disabled?: boolean
  onMove: (toStage: string) => void
  className?: string
}

export function StagePicker({ stage, disabled, onMove, className }: Props) {
  return (
    <div
      className={cn('scrollbar-none -mx-1 flex gap-1.5 overflow-x-auto px-1 py-0.5', className)}
      role="radiogroup"
      aria-label="Stage"
    >
      {FUNNEL_STAGES.map((s) => {
        const active = s === stage
        return (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled || active}
            onClick={() => onMove(s)}
            style={{ '--lane': laneTone(s), '--tone': laneTone(s) } as CSSProperties}
            className={cn(
              'inline-flex h-11 shrink-0 items-center gap-2 rounded-full border px-3.5 text-label whitespace-nowrap transition-colors duration-(--dur-1) ease-out disabled:cursor-default md:h-8 md:px-3',
              active
                ? 'tone-tint'
                : 'border-border bg-surface text-muted-foreground hover:bg-surface-muted hover:text-foreground disabled:opacity-60',
            )}
          >
            <span aria-hidden className="size-2 rounded-full bg-(--lane)" />
            {STAGE_LABELS[s] || s}
          </button>
        )
      })}
    </div>
  )
}

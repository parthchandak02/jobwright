import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { FUNNEL_STAGES, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  disabled?: boolean
  onMove: (toStage: string) => void
  className?: string
}

function StageMoveButton({
  direction,
  targetStage,
  disabled,
  onMove,
}: {
  direction: 'prev' | 'next'
  targetStage: string
  disabled?: boolean
  onMove: (toStage: string) => void
}) {
  const label = STAGE_LABELS[targetStage] || targetStage
  const tone = laneTone(targetStage)

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      disabled={disabled}
      onClick={() => onMove(targetStage)}
      className="h-7 shrink-0 gap-0.5 border border-transparent px-2 hover:border-border/50 hover:bg-accent/60"
      title={`Move to ${label}`}
    >
      {direction === 'prev' ? (
        <>
          <ChevronLeft className="size-3.5 shrink-0 text-muted-foreground" />
          <span
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: tone }}
          >
            {label}
          </span>
        </>
      ) : (
        <>
          <span
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: tone }}
          >
            {label}
          </span>
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
        </>
      )}
    </Button>
  )
}

export function DrawerStageNav({ stage, disabled, onMove, className }: Props) {
  const idx = FUNNEL_STAGES.indexOf(stage as (typeof FUNNEL_STAGES)[number])
  const prev = idx > 0 ? FUNNEL_STAGES[idx - 1] : null
  const next = idx >= 0 && idx < FUNNEL_STAGES.length - 1 ? FUNNEL_STAGES[idx + 1] : null

  return (
    <div className={cn('grid grid-cols-[1fr_auto_1fr] items-center gap-2', className)}>
      <div className="flex justify-start">
        {prev ? (
          <StageMoveButton
            direction="prev"
            targetStage={prev}
            disabled={disabled}
            onMove={onMove}
          />
        ) : null}
      </div>

      <span
        className="shrink-0 text-xs font-bold uppercase tracking-wider"
        style={{ color: laneTone(stage) }}
      >
        {STAGE_LABELS[stage] || stage}
      </span>

      <div className="flex justify-end">
        {next ? (
          <StageMoveButton
            direction="next"
            targetStage={next}
            disabled={disabled}
            onMove={onMove}
          />
        ) : null}
      </div>
    </div>
  )
}

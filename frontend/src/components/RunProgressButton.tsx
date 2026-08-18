import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatElapsed, type AutoSearch } from '@/lib/useAutoSearch'
import { cn } from '@/lib/utils'

type Props = {
  run: AutoSearch
  idleLabel: string
  onClick: () => void
  titleIdle: string
  titleActive: string
  stageLabels: Record<string, string>
  className?: string
}

/** Idle Sparkles CTA that switches to elapsed time, stage, and a progress bar while a run is live. */
export function RunProgressButton({
  run,
  idleLabel,
  onClick,
  titleIdle,
  titleActive,
  stageLabels,
  className,
}: Props) {
  return (
    <Button
      type="button"
      size="sm"
      onClick={onClick}
      title={run.active ? titleActive : titleIdle}
      className={cn('relative min-w-[7.5rem] justify-start overflow-hidden', className)}
    >
      {run.active ? (
        <>
          <Loader2 className="animate-spin" />
          <span className="font-mono tabular-nums">{formatElapsed(run.elapsedMs)}</span>
          <span className="truncate opacity-80">
            {run.currentStage ? stageLabels[run.currentStage] ?? run.currentStage : 'Starting'}
          </span>
          <span className="absolute inset-x-0 bottom-0 h-[3px] bg-primary-foreground/25">
            <span
              className="block h-full bg-primary-foreground/80 transition-[width] duration-500 ease-out"
              style={{ width: `${Math.max(Math.round(run.progress * 100), 4)}%` }}
            />
          </span>
        </>
      ) : (
        <>
          <Sparkles />
          {idleLabel}
        </>
      )}
    </Button>
  )
}

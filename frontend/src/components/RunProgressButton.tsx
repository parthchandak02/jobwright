import type { CSSProperties } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { laneTone } from '@/lib/api'
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
  variant?: 'default' | 'prepare'
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
  variant = 'default',
}: Props) {
  const prepare = variant === 'prepare'

  return (
    <Button
      type="button"
      size="sm"
      variant={prepare ? 'outline' : 'default'}
      onClick={onClick}
      title={run.active ? titleActive : titleIdle}
      style={prepare ? ({ '--lane': laneTone('prepare') } as CSSProperties) : undefined}
      className={cn(
        'relative min-w-[7.5rem] justify-start overflow-hidden',
        prepare && run.active && 'border-[color:var(--lane)]',
        className,
      )}
    >
      {run.active ? (
        <>
          <Loader2 className={cn('animate-spin', prepare && 'text-[color:var(--lane)]')} />
          <span className="font-mono tabular-nums">{formatElapsed(run.elapsedMs)}</span>
          <span className="truncate opacity-80">
            {run.currentStage ? stageLabels[run.currentStage] ?? run.currentStage : 'Starting'}
          </span>
          <span
            className={cn(
              'absolute inset-x-0 bottom-0 h-[3px]',
              prepare ? 'bg-[color:var(--lane)]/25' : 'bg-current/25',
            )}
          >
            <span
              className={cn(
                'block h-full transition-[width] duration-500 ease-out',
                prepare ? 'bg-[color:var(--lane)]' : 'bg-current/80',
              )}
              style={{ width: `${Math.max(Math.round(run.progress * 100), 4)}%` }}
            />
          </span>
        </>
      ) : (
        <>
          <Sparkles className={prepare ? 'text-[color:var(--lane)]' : undefined} />
          {idleLabel}
        </>
      )}
    </Button>
  )
}

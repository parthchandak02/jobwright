import { useRef, type KeyboardEvent, type MouseEvent, type PointerEvent } from 'react'
import { CheckIcon } from 'lucide-react'
import { JobCardView } from '@/components/JobCardView'
import type { JobCard } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  job: JobCard
  showStage?: boolean
  /** Selection mode: tapping the card toggles it instead of opening it. */
  selecting: boolean
  selected: boolean
  onOpen: (url: string) => void
  onToggle: (job: JobCard) => void
  /** Long-press outside selection mode: start selecting with this job. */
  onLongPress?: (job: JobCard) => void
  onScoreSaved?: () => void
}

const LONG_PRESS_MS = 500
const MOVE_TOLERANCE = 8

/** Phone list card that can be selected (tap in selection mode, or long-press to start). */
export function SelectableCard({ job, showStage, selecting, selected, onOpen, onToggle, onLongPress, onScoreSaved }: Props) {
  const timer = useRef<number | undefined>(undefined)
  const start = useRef<{ x: number; y: number } | null>(null)
  const fired = useRef(false)

  const cancel = () => {
    window.clearTimeout(timer.current)
    start.current = null
  }

  const pressHandlers = onLongPress
    ? {
        onPointerDown: (e: PointerEvent) => {
          if (e.pointerType === 'mouse') return
          fired.current = false
          start.current = { x: e.clientX, y: e.clientY }
          timer.current = window.setTimeout(() => {
            fired.current = true
            start.current = null
            navigator.vibrate?.(10)
            onLongPress(job)
          }, LONG_PRESS_MS)
        },
        onPointerMove: (e: PointerEvent) => {
          const s = start.current
          if (s && Math.hypot(e.clientX - s.x, e.clientY - s.y) > MOVE_TOLERANCE) cancel()
        },
        onPointerUp: cancel,
        onPointerCancel: cancel,
        onContextMenu: (e: MouseEvent) => {
          if (fired.current || start.current) e.preventDefault()
        },
        // The tap that ends a long-press must not also open (or toggle) the job.
        onClickCapture: (e: MouseEvent) => {
          if (!fired.current) return
          fired.current = false
          e.preventDefault()
          e.stopPropagation()
        },
      }
    : {}

  if (!selecting) {
    return (
      <div className="select-none [-webkit-touch-callout:none]" {...pressHandlers}>
        <JobCardView
          job={job}
          stage={job.funnel_stage}
          showStage={showStage}
          onOpen={() => onOpen(job.url)}
          onScoreSaved={onScoreSaved}
        />
      </div>
    )
  }

  const company = job.company || job.site
  return (
    <div
      role="checkbox"
      aria-checked={selected}
      aria-label={`${job.title || 'Untitled'}${company ? `, ${company}` : ''}`}
      tabIndex={0}
      onClick={() => onToggle(job)}
      onKeyDown={(e: KeyboardEvent) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault()
          onToggle(job)
        }
      }}
      className={cn(
        'flex cursor-pointer items-stretch gap-2 rounded-lg select-none [-webkit-touch-callout:none]',
        // The card keeps its own look; selected = accent border + tint.
        selected && '[&_[data-card]>div]:border-primary [&_[data-card]>div]:bg-accent/60',
      )}
      {...pressHandlers}
    >
      <span aria-hidden className="flex w-8 shrink-0 items-start justify-center pt-3.5">
        <span
          className={cn(
            'flex size-5 items-center justify-center rounded-full border transition-colors duration-(--dur-1) ease-out',
            selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong bg-surface',
          )}
        >
          {selected ? <CheckIcon className="size-3.5" strokeWidth={3} /> : null}
        </span>
      </span>
      {/* inert: the score pill and listing link inside the card can't be hit or focused while selecting. */}
      <div data-card className="min-w-0 flex-1" inert>
        <JobCardView job={job} stage={job.funnel_stage} showStage={showStage} focusable={false} />
      </div>
    </div>
  )
}

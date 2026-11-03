import { useCallback } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { CSSProperties, KeyboardEvent, MouseEvent, PointerEvent } from 'react'
import { JobSummary } from '@/components/JobSummary'
import { JobCard, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  job: JobCard
  stage?: string
  onOpen?: (job: JobCard) => void
  dragging?: boolean
  onScoreSaved?: () => void
  showStage?: boolean
  /**
   * The card is its own button (Tab stop, Enter/Space opens). Off when a wrapper
   * owns focus, e.g. the sortable board card.
   */
  focusable?: boolean
}

function stopCardOpen(e: MouseEvent | PointerEvent) {
  e.stopPropagation()
}

function cardLabel(job: JobCard) {
  return `Open ${job.title || 'job'} at ${job.company || 'unknown company'}`
}

export function JobCardView({ job, stage, onOpen, dragging, onScoreSaved, showStage, focusable = true }: Props) {
  const lane = stage ? laneTone(stage) : undefined
  const asButton = Boolean(onOpen) && focusable

  return (
    <div
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      className={cn(
        'relative cursor-pointer overflow-hidden rounded-lg border border-border bg-surface py-3 pr-3 pl-3.5 text-foreground transition-[border-color,box-shadow] duration-(--dur-1) ease-out hover:border-border-strong hover:shadow-e1',
        dragging && 'cursor-grabbing rotate-1 border-border-strong shadow-e1',
      )}
      onClick={() => onOpen?.(job)}
      onKeyDown={
        asButton
          ? (e) => {
              if (e.key === 'Enter' || (e.key === ' ' && e.target === e.currentTarget)) {
                e.preventDefault()
                onOpen?.(job)
              }
            }
          : undefined
      }
      role={asButton ? 'button' : undefined}
      tabIndex={asButton ? 0 : undefined}
      aria-label={asButton ? cardLabel(job) : undefined}
    >
      {lane ? <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-(--lane)" /> : null}
      {showStage && stage ? (
        <p className="lane-label mb-1.5 text-micro font-semibold tracking-wide uppercase">{STAGE_LABELS[stage] || stage}</p>
      ) : null}
      <JobSummary job={job} onScoreSaved={onScoreSaved} onLinkClick={stopCardOpen} />
    </div>
  )
}

export function SortableJobCard({
  job,
  stage,
  onOpen,
  onScoreSaved,
}: {
  job: JobCard
  stage: string
  onOpen: (j: JobCard) => void
  onScoreSaved?: () => void
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: job.url,
    transition: {
      duration: 180,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
    },
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }
  // The wrapper is the one Tab stop for the card: dnd-kit's role/tabIndex/aria
  // (Space picks up for a keyboard move), and Enter opens the job. It is also the
  // activator node, so Space on the score button or the listing link inside the
  // card never starts a drag.
  const ref = useCallback(
    (node: HTMLDivElement | null) => {
      setNodeRef(node)
      setActivatorNodeRef(node)
    },
    [setNodeRef, setActivatorNodeRef],
  )
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && e.target === e.currentTarget && !isDragging) {
      e.preventDefault()
      onOpen(job)
      return
    }
    listeners?.onKeyDown?.(e)
  }

  return (
    <div
      ref={ref}
      style={style}
      {...attributes}
      {...listeners}
      onKeyDown={onKeyDown}
      aria-label={cardLabel(job)}
      className="touch-manipulation rounded-lg"
    >
      {isDragging ? (
        <div className="min-h-[6.5rem] rounded-lg border border-dashed border-border-strong bg-surface-muted" aria-hidden />
      ) : (
        <JobCardView job={job} stage={stage} onOpen={onOpen} onScoreSaved={onScoreSaved} focusable={false} />
      )}
    </div>
  )
}

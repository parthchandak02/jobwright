import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { CSSProperties, MouseEvent, PointerEvent } from 'react'
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
}

function stopCardOpen(e: MouseEvent | PointerEvent) {
  e.stopPropagation()
}

export function JobCardView({ job, stage, onOpen, dragging, onScoreSaved, showStage }: Props) {
  const lane = stage ? laneTone(stage) : undefined

  return (
    <div
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      className={cn(
        'relative cursor-pointer overflow-hidden rounded-lg border border-border bg-surface py-3 pr-3 pl-3.5 text-foreground transition-[border-color,box-shadow] duration-(--dur-1) ease-out hover:border-border-strong hover:shadow-e1',
        dragging && 'cursor-grabbing rotate-1 border-border-strong shadow-e1',
      )}
      onClick={() => onOpen?.(job)}
      onKeyDown={(e) => {
        if (onOpen && (e.key === 'Enter' || (e.key === ' ' && e.target === e.currentTarget))) {
          e.preventDefault()
          onOpen(job)
        }
      }}
      role={onOpen ? 'button' : undefined}
      tabIndex={onOpen ? 0 : undefined}
      aria-label={onOpen ? `Open ${job.title || 'job'} at ${job.company || 'unknown company'}` : undefined}
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
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
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
  const { role: _role, tabIndex: _tabIndex, ...dragAttributes } = attributes

  if (isDragging) {
    return (
      <div ref={setNodeRef} style={style} className="touch-manipulation" {...dragAttributes} {...listeners}>
        <div className="min-h-[6.5rem] rounded-lg border border-dashed border-border-strong bg-surface-muted" aria-hidden />
      </div>
    )
  }

  return (
    <div ref={setNodeRef} style={style} {...dragAttributes} {...listeners} className="touch-manipulation">
      <JobCardView job={job} stage={stage} onOpen={onOpen} onScoreSaved={onScoreSaved} />
    </div>
  )
}

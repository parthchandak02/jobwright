import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { JobSummary } from '@/components/JobSummary'
import { cn } from '@/lib/utils'
import { JobCard, laneTone } from '@/lib/api'
import type { CSSProperties, MouseEvent, PointerEvent } from 'react'

type Props = {
  job: JobCard
  stage?: string
  onOpen?: (job: JobCard) => void
  dragging?: boolean
  onScoreSaved?: () => void
}

function stopCardOpen(e: MouseEvent | PointerEvent) {
  e.stopPropagation()
}

export function JobCardView({ job, stage, onOpen, dragging, onScoreSaved }: Props) {
  const lane = stage ? laneTone(stage) : undefined

  return (
    <div
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      className={cn(
        'glass job-card-pad relative cursor-pointer rounded-xl',
        lane && 'lane-card',
        dragging
          ? 'glass-strong cursor-grabbing ring-2 ring-[color:var(--lane)] shadow-[var(--glass-shadow-hover)] rotate-[0.75deg] scale-[1.02]'
          : 'glass-interactive',
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
  const lane = laneTone(stage)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: job.url,
    transition: {
      duration: 200,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
    },
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }
  // The card itself is the single focus target (Enter opens it); keyboard users
  // move stages from the drawer, so the drag wrapper stays out of the tab order.
  const { role: _role, tabIndex: _tabIndex, ...dragAttributes } = attributes

  if (isDragging) {
    return (
      <div
        ref={setNodeRef}
        style={{ ...style, '--lane': lane } as CSSProperties}
        className="touch-manipulation"
        {...dragAttributes}
        {...listeners}
      >
        <div
          className="min-h-[7.5rem] rounded-xl border-2 border-dashed border-[color:var(--lane)]/35 bg-[color-mix(in_srgb,var(--lane)_8%,transparent)]"
          aria-hidden
        />
      </div>
    )
  }

  return (
    <div ref={setNodeRef} style={style} {...dragAttributes} {...listeners} className="touch-manipulation">
      <JobCardView job={job} stage={stage} onOpen={onOpen} onScoreSaved={onScoreSaved} />
    </div>
  )
}

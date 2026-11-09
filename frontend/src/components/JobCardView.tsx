import { memo, useCallback, useMemo } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { CSSProperties, KeyboardEvent, MouseEvent, PointerEvent } from 'react'
import { JobSummary, type TitleButtonProps } from '@/components/JobSummary'
import { JobCard, laneTone, STAGE_LABELS } from '@/lib/api'
import { JOB_KEY_ATTR, useSelectedJob } from '@/lib/jobPanel'
import { cn } from '@/lib/utils'

type Props = {
  job: JobCard
  stage?: string
  onOpen?: (job: JobCard) => void
  dragging?: boolean
  /** Called with this card's job, so one stable callback serves every card. */
  onScoreSaved?: (job: JobCard) => void
  showStage?: boolean
  /**
   * The card's title is its open button (a Tab stop; Enter, Space or a click anywhere on the
   * card opens). Off when the card is only a picture of a job (drag overlay, selection mode).
   */
  focusable?: boolean
  /** Extra props for the open button: the sortable card's dnd-kit activator. Keep it stable. */
  openButton?: TitleButtonProps
}

function stopCardOpen(e: MouseEvent | PointerEvent) {
  e.stopPropagation()
}

function cardLabel(job: JobCard) {
  return `Open ${job.title || 'job'} at ${job.company || 'unknown company'}`
}

/**
 * A job on the board or the phone list. The title is a real <button> whose hit area stretches
 * over the card (`.job-card-open`), so the score button and listing link sit beside it instead
 * of inside a button. Memoized: with 300+ cards a drag step must not re-render every card.
 */
export const JobCardView = memo(function JobCardView({
  job,
  stage,
  onOpen,
  dragging,
  onScoreSaved,
  showStage,
  focusable = true,
  openButton,
}: Props) {
  const lane = stage ? laneTone(stage) : undefined
  const opens = Boolean(onOpen) && focusable
  // The job open in the desktop panel (the overlay copy while dragging never shows it).
  const selected = useSelectedJob(job.job_id) && !dragging && Boolean(onOpen)
  const scoreSaved = useMemo(() => (onScoreSaved ? () => onScoreSaved(job) : undefined), [onScoreSaved, job])

  const titleButton: TitleButtonProps | undefined = opens
    ? {
        ...openButton,
        className: 'job-card-open',
        onClick: () => onOpen?.(job),
        'aria-label': cardLabel(job),
        'aria-current': selected ? 'true' : undefined,
      }
    : undefined

  return (
    <div
      style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
      className={cn(
        'relative overflow-hidden rounded-lg border border-border bg-surface p-3 text-foreground transition-[border-color,box-shadow] duration-(--dur-1) ease-out hover:border-border-strong hover:shadow-e1',
        opens && 'cursor-pointer',
        dragging && 'cursor-grabbing rotate-1 border-border-strong shadow-e1',
        selected && 'job-card-selected',
      )}
      // A sortable card's wrapper carries the job key; a plain card carries it itself.
      {...(opens && !openButton ? { [JOB_KEY_ATTR]: job.job_id } : {})}
    >
      {showStage && stage ? (
        <p className="mb-1.5 flex items-center gap-1.5 text-micro font-medium text-muted-foreground">
          <span aria-hidden className="size-1.5 rounded-full bg-(--lane)" />
          {STAGE_LABELS[stage] || stage}
        </p>
      ) : null}
      <JobSummary
        job={job}
        onScoreSaved={scoreSaved}
        onLinkClick={stopCardOpen}
        titleButton={titleButton}
        showLink={false}
        stage={showStage ? undefined : stage}
      />
    </div>
  )
})

export const SortableJobCard = memo(function SortableJobCard({
  job,
  stage,
  onOpen,
  onScoreSaved,
}: {
  job: JobCard
  stage: string
  onOpen: (j: JobCard) => void
  onScoreSaved?: (j: JobCard) => void
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
  // Pointer drags start anywhere on the card (the wrapper). The keyboard side lives on the
  // title button, the card's one Tab stop: dnd-kit's role, aria and instructions; Space picks
  // up and drops, arrows move, Escape cancels; Enter is a plain button press that opens the job.
  // Being the activator node also means Space on the score button or listing link never drags.
  const dragKeyDown = listeners?.onKeyDown
  const pointerListeners = useMemo(() => {
    if (!listeners) return undefined
    const { onKeyDown: _keys, ...rest } = listeners
    return rest
  }, [listeners])
  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === 'Enter') return
      dragKeyDown?.(e)
    },
    [dragKeyDown],
  )
  const openButton = useMemo<TitleButtonProps>(
    () => ({ ...attributes, ref: setActivatorNodeRef, onKeyDown }),
    [attributes, setActivatorNodeRef, onKeyDown],
  )

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...pointerListeners}
      {...{ [JOB_KEY_ATTR]: job.job_id }}
      className={cn('job-card-slot relative touch-manipulation rounded-lg', isDragging && '[&>:first-child]:opacity-0')}
    >
      {/* While lifted, the card stays mounted (it holds keyboard focus) under a drop placeholder. */}
      <JobCardView job={job} stage={stage} onOpen={onOpen} onScoreSaved={onScoreSaved} openButton={openButton} />
      {isDragging ? (
        <div
          className="absolute inset-0 rounded-lg border border-dashed border-border-strong bg-surface-muted"
          aria-hidden
        />
      ) : null}
    </div>
  )
})

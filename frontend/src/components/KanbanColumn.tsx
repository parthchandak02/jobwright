import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Inbox } from 'lucide-react'
import type { CSSProperties } from 'react'
import { JobCard, laneTone } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'
import { SortableJobCard } from './JobCardView'

type Props = {
  stage: string
  label: string
  jobs: JobCard[]
  total?: number
  isDropTarget?: boolean
  isDragging?: boolean
  searching?: boolean
  onOpen: (job: JobCard) => void
  onScoreSaved?: () => void
}

const EMPTY_COPY: Record<string, { title: string; body: string }> = {
  backlog: { title: 'No new jobs', body: 'New matches land here after each daily search.' },
  prepare: { title: 'Nothing to prepare', body: 'Move a job here when you want a tailored resume and letter.' },
  applied: { title: 'Nothing applied yet', body: 'After you apply, tap “I applied” or drag the job here.' },
  in_progress: { title: 'No interviews yet', body: 'Move a job here once the company gets back to you.' },
  offer: { title: 'No offers yet', body: 'Offers you get will show up here.' },
  closed: { title: 'Nothing closed', body: 'Jobs you pass on or hear back about end up here.' },
}

export function KanbanColumn({
  stage,
  label,
  jobs,
  total,
  isDropTarget,
  isDragging,
  searching,
  onOpen,
  onScoreSaved,
}: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  const lane = laneTone(stage)
  const highlighted = isOver || isDropTarget
  const Icon = NAV_ICONS[stage] || Inbox
  const copy = searching
    ? { title: 'No matches', body: 'Nothing in this stage matches your search.' }
    : EMPTY_COPY[stage] || EMPTY_COPY.backlog

  return (
    <section
      aria-label={`${label}, ${jobs.length} job${jobs.length === 1 ? '' : 's'}`}
      style={{ '--lane': lane, '--tone': lane } as CSSProperties}
      className="flex w-[17.5rem] shrink-0 flex-col"
    >
      <header className="flex h-8 items-center gap-2 px-1.5">
        <span aria-hidden className="size-2 shrink-0 rounded-full bg-(--lane)" />
        <h2 className="lane-label min-w-0 truncate text-micro font-semibold tracking-wide uppercase">{label}</h2>
        <span className="text-micro font-medium text-muted-foreground tabular-nums">
          {total && total > jobs.length ? `${jobs.length} of ${total}` : jobs.length}
        </span>
      </header>
      <div
        ref={setNodeRef}
        className={cn(
          'flex min-h-[min(70vh,520px)] flex-1 flex-col gap-2 rounded-lg border border-transparent p-1 transition-colors duration-(--dur-2) ease-out',
          highlighted && 'tone-tint',
        )}
      >
        <SortableContext items={jobs.map((j) => j.url)} strategy={verticalListSortingStrategy}>
          {jobs.map((job) => (
            <SortableJobCard key={job.url} job={job} stage={stage} onOpen={onOpen} onScoreSaved={onScoreSaved} />
          ))}
        </SortableContext>
        {jobs.length === 0 ? (
          <div
            className={cn(
              'flex flex-col items-center rounded-lg border border-dashed px-4 py-8 text-center transition-colors duration-(--dur-2) ease-out',
              isDragging ? 'border-(--lane)' : 'border-border-strong',
            )}
          >
            <Icon className="mb-2.5 size-5 text-subtle-foreground" strokeWidth={1.75} aria-hidden />
            {isDragging ? (
              <p className="text-label text-foreground">{highlighted ? 'Release to move here' : `Drop here to move to ${label}`}</p>
            ) : (
              <>
                <p className="text-label text-foreground">{copy.title}</p>
                <p className="mt-1 text-caption text-muted-foreground">{copy.body}</p>
              </>
            )}
          </div>
        ) : null}
      </div>
    </section>
  )
}

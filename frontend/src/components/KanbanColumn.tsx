import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import type { CSSProperties } from 'react'
import { cn } from '@/lib/utils'
import { JobCard, laneTone } from '@/lib/api'
import { SortableJobCard } from './JobCardView'

type Props = {
  stage: string
  label: string
  jobs: JobCard[]
  isDropTarget?: boolean
  isDragging?: boolean
  onOpen: (job: JobCard) => void
  onScoreSaved?: () => void
}

export function KanbanColumn({
  stage,
  label,
  jobs,
  isDropTarget,
  isDragging,
  onOpen,
  onScoreSaved,
}: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  const lane = laneTone(stage)
  const highlighted = isOver || isDropTarget

  return (
    <section
      style={{ '--lane': lane } as CSSProperties}
      className={cn(
        'flex w-72 shrink-0 flex-col rounded-xl transition-[background-color,box-shadow] duration-200',
        highlighted && 'bg-[color-mix(in_srgb,var(--lane)_10%,transparent)] shadow-[inset_0_0_0_2px_color-mix(in_srgb,var(--lane)_45%,transparent)]',
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border/50 px-1.5 pb-2 pt-0.5">
        <h2 className="truncate text-xs font-bold uppercase tracking-wider text-[color:var(--lane)]">
          {label}
        </h2>
        <span className="shrink-0 text-xs font-semibold tabular-nums text-[color:var(--lane)]/70">
          {jobs.length}
        </span>
      </header>
      <div
        ref={setNodeRef}
        className={cn(
          'flex min-h-[min(70vh,520px)] flex-1 flex-col gap-2 overflow-y-auto px-0.5 py-2 transition-colors duration-200',
          highlighted && 'bg-[color-mix(in_srgb,var(--lane)_4%,transparent)]',
        )}
      >
        <SortableContext items={jobs.map((j) => j.url)} strategy={verticalListSortingStrategy}>
          {jobs.map((job) => (
            <SortableJobCard
              key={job.url}
              job={job}
              stage={stage}
              onOpen={onOpen}
              onScoreSaved={onScoreSaved}
            />
          ))}
        </SortableContext>
        {jobs.length === 0 && (
          <div
            className={cn(
              'mx-1 flex flex-1 items-center justify-center rounded-lg border border-dashed px-3 py-8 text-center text-xs transition-colors duration-200',
              highlighted || isDragging
                ? 'border-[color:var(--lane)]/50 bg-[color-mix(in_srgb,var(--lane)_6%,transparent)] text-[color:var(--lane)]'
                : 'border-border/60 text-muted-foreground',
            )}
          >
            {highlighted ? 'Release to drop' : 'Drop jobs here'}
          </div>
        )}
      </div>
    </section>
  )
}

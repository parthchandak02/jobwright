import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import type { CSSProperties } from 'react'
import { cn } from '@/lib/utils'
import { JobCard, STAGE_TONE } from '@/lib/api'
import { SortableJobCard } from './JobCardView'

type Props = {
  stage: string
  label: string
  jobs: JobCard[]
  onOpen: (job: JobCard) => void
}

export function KanbanColumn({ stage, label, jobs, onOpen }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  const toneVar = STAGE_TONE[stage] || STAGE_TONE.backlog
  const tone = `var(${toneVar})`

  return (
    <section
      ref={setNodeRef}
      style={
        {
          '--lane': tone,
        } as CSSProperties
      }
      className={cn(
        'flex w-72 shrink-0 flex-col rounded-lg transition-colors',
        isOver && 'bg-[color-mix(in_oklch,var(--lane)_8%,transparent)]',
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border/50 px-1.5 pb-2">
        <h2 className="truncate text-xs font-bold uppercase tracking-wider text-[color:var(--lane)]">
          {label}
        </h2>
        <span className="shrink-0 text-xs font-semibold tabular-nums text-[color:var(--lane)]/70">
          {jobs.length}
        </span>
      </header>
      <div className="flex min-h-[140px] flex-1 flex-col gap-2 overflow-y-auto px-0.5 py-2">
        <SortableContext items={jobs.map((j) => j.url)} strategy={verticalListSortingStrategy}>
          {jobs.map((job) => (
            <SortableJobCard key={job.url} job={job} onOpen={onOpen} />
          ))}
        </SortableContext>
        {jobs.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">Drop jobs here</p>
        )}
      </div>
    </section>
  )
}

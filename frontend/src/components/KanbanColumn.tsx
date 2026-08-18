import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import type { CSSProperties } from 'react'
import { Badge } from '@/components/ui/badge'
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
        'flex w-72 shrink-0 flex-col rounded-2xl border backdrop-blur-md',
        'border-l-4 border-l-[color:var(--lane)]',
        'bg-[color-mix(in_oklch,var(--lane)_8%,transparent)]',
        isOver
          ? 'border-2 border-dashed border-[color:var(--lane)] bg-[color-mix(in_oklch,var(--lane)_16%,transparent)] ring-2 ring-[color:var(--lane)]/30'
          : 'border-border/60',
      )}
    >
      <header
        className={cn(
          'flex items-center justify-between gap-2 rounded-t-2xl border-b border-border/50 px-3 py-2.5',
          'bg-[color-mix(in_oklch,var(--lane)_14%,transparent)]',
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="size-2 shrink-0 rounded-full shadow-[0_0_8px_0_var(--lane)]"
            style={{ backgroundColor: tone }}
            aria-hidden
          />
          <h2 className="truncate text-sm font-semibold text-foreground">{label}</h2>
        </div>
        <Badge
          variant="secondary"
          className="border border-[color:var(--lane)]/40 bg-[color-mix(in_oklch,var(--lane)_18%,transparent)]"
        >
          {jobs.length}
        </Badge>
      </header>
      <div className="flex min-h-[140px] flex-1 flex-col gap-2 overflow-y-auto p-2">
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

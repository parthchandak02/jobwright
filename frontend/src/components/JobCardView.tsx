import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Building2, DollarSign, MapPin } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { MetaField } from '@/components/MetaField'
import { ScoreBadge } from '@/components/ScoreBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import { cn } from '@/lib/utils'
import { JobCard } from '@/lib/api'

type Props = {
  job: JobCard
  onOpen?: (job: JobCard) => void
  dragging?: boolean
}

function scoreRationale(job: JobCard): string {
  const parts = [job.keywords, job.reasoning].map((s) => s?.trim()).filter(Boolean)
  return parts.join(' — ') || 'No score rationale yet.'
}

export function JobCardView({ job, onOpen, dragging }: Props) {
  return (
    <div
      className={cn(
        'glass glass-interactive relative cursor-pointer rounded-xl p-3',
        dragging && 'ring-2 ring-ring',
      )}
      onClick={() => onOpen?.(job)}
    >
      {/* Score: top-right, hover reveals the rationale */}
      <div className="absolute right-2.5 top-2.5 z-10">
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
              className="cursor-help"
            >
              <ScoreBadge score={job.fit_score} className="h-7 min-w-7 rounded-lg text-sm" />
            </span>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p className="font-medium text-foreground">
              Fit score{job.fit_score != null ? `: ${job.fit_score}/10` : ' unavailable'}
            </p>
            <p className="mt-1 text-muted-foreground">{scoreRationale(job)}</p>
          </TooltipContent>
        </Tooltip>
      </div>

      <div className="space-y-2.5">
        <div className="min-w-0 pr-9">
          <h3 className="truncate text-sm font-semibold leading-snug text-foreground">
            {job.title || 'Untitled'}
          </h3>
          <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
            <Building2 className="size-3 shrink-0" />
            {job.company || job.site || 'Unknown'}
          </p>
        </div>

        <div className="space-y-1.5">
          <WorkModelBadge workModel={job.work_model} />
          <MetaField icon={MapPin} label="Location" value={job.location} />
          <MetaField icon={DollarSign} label="Salary" value={job.salary} />
        </div>

        <JobMetaBadges job={job} />
      </div>
    </div>
  )
}

export function SortableJobCard({ job, onOpen }: { job: JobCard; onOpen: (j: JobCard) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: job.url,
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.35 : 1,
  }
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners} className="touch-none">
      <JobCardView job={job} onOpen={onOpen} />
    </div>
  )
}

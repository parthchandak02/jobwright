import { JobKeyChips } from '@/components/JobMetaBadges'
import { placeLine } from '@/components/JobSummary'
import { ScoreEditor } from '@/components/ScoreEditor'
import { StageBadge } from '@/components/StageBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import type { JobCard } from '@/lib/api'
import { JOB_KEY_ATTR, useSelectedJob } from '@/lib/jobPanel'
import { cn } from '@/lib/utils'

type Props = {
  job: JobCard
  onOpen: (url: string) => void
  onScoreSaved?: () => void
}

/**
 * One desktop row. The whole row opens the job on click; the title is a real
 * button so keyboard (Enter / Space) and screen readers reach it.
 */
export function JobsTableRow({ job, onOpen, onScoreSaved }: Props) {
  const company = job.company || job.site
  const selected = useSelectedJob(job.job_id)
  return (
    <tr
      className={cn(
        'cursor-pointer border-t border-border transition-colors duration-(--dur-1) first:border-t-0 hover:bg-surface-muted',
        selected && 'jobs-table-row-selected',
      )}
      aria-current={selected ? 'true' : undefined}
      {...{ [JOB_KEY_ATTR]: job.job_id }}
      onClick={() => onOpen(job.url)}
    >
      <td onClick={(e) => e.stopPropagation()}>
        <ScoreEditor job={job} onSaved={onScoreSaved} />
      </td>
      <td>
        <button
          type="button"
          className="block w-full rounded-sm text-left font-medium break-words text-foreground underline-offset-2 hover:underline"
          onClick={(e) => {
            e.stopPropagation()
            onOpen(job.url)
          }}
        >
          <span className="line-clamp-2">{job.title || 'Untitled'}</span>
          {company ? <span className="sr-only">, {company}</span> : null}
        </button>
        <span className="mt-1 flex flex-wrap gap-1.5 empty:hidden">
          <JobKeyChips job={job} max={1} kinds={['alert', 'info']} />
        </span>
      </td>
      <td className="text-muted-foreground">
        <span className="block truncate">{company || '—'}</span>
      </td>
      <td className="text-muted-foreground">
        <span className="block truncate" title={placeLine(job)}>
          {job.location || 'Not stated'}
        </span>
      </td>
      <td>
        <StageBadge stage={job.funnel_stage} />
      </td>
      <td>
        <WorkModelBadge workModel={job.work_model} />
      </td>
      <td className="text-muted-foreground">
        <span className="block truncate capitalize">{job.source === 'manual' ? 'Added by you' : job.source}</span>
      </td>
      <td>
        <div className="flex min-w-0 flex-wrap gap-1">
          <JobKeyChips job={job} kinds={['materials']} />
        </div>
      </td>
    </tr>
  )
}

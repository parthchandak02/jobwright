import { Copy, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { MatchExplanation } from '@/components/MatchExplanation'
import { RateJob } from '@/components/RateJob'
import { jobPath, OUTCOME_LABELS, type JobCard } from '@/lib/api'

function closedText(job: JobCard): string | null {
  if (job.funnel_stage !== 'closed' || job.duplicate_of || !(job.outcome || job.close_reason)) return null
  return [
    job.outcome ? OUTCOME_LABELS[job.outcome] || job.outcome.replace('_', ' ') : null,
    job.close_reason ? (job.close_reason === 'no_response' ? 'No response' : job.close_reason) : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

/** Match explanation, why it was closed, and the "Is this a good match?" rating. */
export function MatchCard({ job, onRated }: { job: JobCard; onRated: (updated: JobCard) => void }) {
  const closed = closedText(job)
  return (
    <div className="surface space-y-4 rounded-lg p-4 md:p-5">
      <MatchExplanation job={job} />
      {job.funnel_stage === 'closed' && job.duplicate_of ? (
        <p className="flex items-center gap-2 text-body text-muted-foreground">
          <Copy className="size-4 shrink-0" aria-hidden />
          <span>
            Closed as a duplicate of{' '}
            <Link to={jobPath(job.duplicate_of.job_id)} className="font-medium text-foreground underline underline-offset-2">
              {job.duplicate_of.title || 'another posting'}
            </Link>
          </span>
        </p>
      ) : closed ? (
        <p className="flex items-center gap-2 text-body text-muted-foreground">
          <XCircle className="size-4 shrink-0" aria-hidden /> Closed: {closed}
        </p>
      ) : null}
      <div className="border-t border-border pt-4">
        <RateJob job={job} onRated={onRated} />
      </div>
    </div>
  )
}

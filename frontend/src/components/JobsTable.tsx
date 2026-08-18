import { Badge } from '@/components/ui/badge'
import { ScoreBadge } from '@/components/ScoreBadge'
import { JobCard, STAGE_LABELS } from '@/lib/api'

type Props = {
  jobs: JobCard[]
  onOpen: (url: string) => void
}

export function JobsTable({ jobs, onOpen }: Props) {
  if (jobs.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-10 text-center shadow-sm">
        <p className="text-sm font-medium text-foreground">No jobs in this view</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Try another stage filter or run the pipeline to discover roles.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="sticky top-0 bg-muted/80 text-muted-foreground backdrop-blur">
          <tr>
            <th className="p-3 font-medium">Score</th>
            <th className="p-3 font-medium">Title</th>
            <th className="p-3 font-medium">Company</th>
            <th className="p-3 font-medium">Stage</th>
            <th className="p-3 font-medium">Source</th>
            <th className="p-3 font-medium">Response</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr
              key={j.url}
              className="cursor-pointer border-t hover:bg-accent/40"
              onClick={() => onOpen(j.url)}
            >
              <td className="p-3">
                <ScoreBadge score={j.fit_score} variant="text" />
              </td>
              <td className="p-3 font-medium">{j.title}</td>
              <td className="p-3 text-muted-foreground">{j.company}</td>
              <td className="p-3">
                <Badge variant="secondary">
                  {STAGE_LABELS[j.funnel_stage] || j.funnel_stage}
                </Badge>
              </td>
              <td className="p-3 text-muted-foreground">{j.source}</td>
              <td className="p-3">
                {j.first_response_at ? <Badge variant="warning">Yes</Badge> : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

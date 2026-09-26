import { AlertTriangle, Ban, MapPin, Sparkles, TrendingUp } from 'lucide-react'
import { Chip } from '@/components/Chip'
import { ScoreBadge } from '@/components/ScoreBadge'
import type { JobCard } from '@/lib/api'
import { useDealbreakerLabels } from '@/lib/reasons'

function prettyId(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const SENIORITY: Record<string, string> = {
  too_junior: 'Below your level',
  match: 'Right level',
  stretch: 'A stretch',
  too_senior: 'Above your level',
}

/** Why the scorer gave this job its score: rules it tripped, fit, confidence, reasoning. */
export function MatchExplanation({ job }: { job: JobCard }) {
  const labels = useDealbreakerLabels()
  const label = (id: string) => labels[id] || prettyId(id)
  const deals = job.dealbreakers || []
  const concerns = (job.concerns || []).filter((c) => !deals.includes(c))
  const hasV2 = job.score_tier != null || deals.length > 0 || job.seniority != null
  const confidence = job.score_confidence
  // The stored reasoning ends with the applied caps ("[dealbreaker: …]"); chips show those.
  const reasoning = (job.reasoning || '').replace(/\s*\[[^\]]*\]\s*$/, '').trim()

  if (job.ai_fit_score == null && job.fit_score == null) {
    return <p className="text-sm text-muted-foreground">Not scored yet. It will be scored on the next search.</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ScoreBadge score={job.ai_fit_score ?? job.fit_score} className="h-7 min-w-7 rounded-lg text-sm" />
        <span className="text-sm font-medium">
          {job.ai_fit_score != null && job.ai_fit_score >= 7
            ? 'Strong match'
            : job.ai_fit_score != null && job.ai_fit_score >= 5
              ? 'Partial match'
              : 'Weak match'}
        </span>
        {confidence != null ? (
          <span className="text-xs text-muted-foreground">{Math.round(confidence * 100)}% sure</span>
        ) : null}
        {job.score_user_modified ? <Chip icon={Sparkles}>You rated it {job.user_fit_score}</Chip> : null}
      </div>

      {hasV2 ? (
        <div className="flex flex-wrap gap-1.5">
          {deals.map((d) => (
            <Chip key={d} icon={Ban} tone="--destructive" title={`Dealbreaker (capped the score): ${label(d)}`}>
              {label(d)}
            </Chip>
          ))}
          {concerns.map((c) => (
            <Chip key={c} icon={AlertTriangle} title={`Partly matches a dealbreaker: ${label(c)}`}>
              Partly: {label(c)}
            </Chip>
          ))}
          {job.location_ok === false ? (
            <Chip icon={MapPin} tone="--destructive">
              Location doesn’t work
            </Chip>
          ) : null}
          {job.seniority ? <Chip icon={TrendingUp}>{SENIORITY[job.seniority] || job.seniority}</Chip> : null}
        </div>
      ) : null}

      {reasoning ? <p className="text-sm leading-relaxed text-foreground/90">{reasoning}</p> : null}
    </div>
  )
}

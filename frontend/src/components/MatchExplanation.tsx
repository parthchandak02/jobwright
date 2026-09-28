import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, Ban, CircleCheck, MapPinOff, TrendingDown, TrendingUp } from 'lucide-react'
import { prettyId } from '@/components/JobMetaBadges'
import { ScoreBadge } from '@/components/ScoreBadge'
import type { JobCard } from '@/lib/api'
import { useDealbreakerLabels } from '@/lib/reasons'
import { cn } from '@/lib/utils'

const SENIORITY: Record<string, { text: string; icon: LucideIcon; tone: 'ok' | 'note' }> = {
  too_junior: { text: 'The level looks below yours.', icon: TrendingDown, tone: 'note' },
  match: { text: 'The level matches yours.', icon: CircleCheck, tone: 'ok' },
  stretch: { text: 'The level is a stretch above yours.', icon: TrendingUp, tone: 'note' },
  too_senior: { text: 'The level looks above yours.', icon: TrendingUp, tone: 'note' },
}

type Point = { key: string; icon: LucideIcon; text: string; tone: 'bad' | 'note' | 'ok' }

const POINT_TONE: Record<Point['tone'], string> = {
  bad: 'text-destructive',
  note: 'text-warning',
  ok: 'text-success',
}

export function MatchExplanation({ job }: { job: JobCard }) {
  const labels = useDealbreakerLabels()
  const label = (id: string) => labels[id] || prettyId(id)
  const deals = job.dealbreakers || []
  const concerns = (job.concerns || []).filter((c) => !deals.includes(c))
  const confidence = job.score_confidence
  const reasoning = (job.reasoning || '').replace(/\s*\[[^\]]*\]\s*$/, '').trim()
  const score = job.ai_fit_score ?? job.fit_score

  if (job.ai_fit_score == null && job.fit_score == null) {
    return (
      <div className="space-y-2">
        <ScoreBadge score={null} label="long" />
        <p className="text-body text-muted-foreground">Not scored yet. It will be scored on the next search.</p>
      </div>
    )
  }

  const points: Point[] = [
    ...deals.map((d) => ({ key: `d-${d}`, icon: Ban, tone: 'bad' as const, text: `Breaks your dealbreaker: ${label(d)}.` })),
    ...(job.location_ok === false
      ? [{ key: 'loc', icon: MapPinOff, tone: 'bad' as const, text: 'The location doesn’t work for you.' }]
      : []),
    ...concerns.map((c) => ({ key: `c-${c}`, icon: AlertTriangle, tone: 'note' as const, text: `Partly matches a dealbreaker: ${label(c)}.` })),
    ...(job.seniority && SENIORITY[job.seniority]
      ? [{ key: 'level', icon: SENIORITY[job.seniority].icon, tone: SENIORITY[job.seniority].tone, text: SENIORITY[job.seniority].text }]
      : []),
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <ScoreBadge score={score} label="long" className="h-7 px-2.5 text-caption" />
        {confidence != null ? (
          <span className="text-caption text-muted-foreground tabular-nums">{Math.round(confidence * 100)}% sure</span>
        ) : null}
      </div>

      {reasoning ? <p className="text-body text-foreground">{reasoning}</p> : null}

      {points.length ? (
        <ul className="space-y-1.5">
          {points.map((p) => (
            <li key={p.key} className="flex items-start gap-2 text-body text-foreground">
              <p.icon className={cn('mt-[0.2rem] size-4 shrink-0', POINT_TONE[p.tone])} aria-hidden />
              <span className="min-w-0">{p.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

import { Banknote, ExternalLink, MapPin } from 'lucide-react'
import type { MouseEvent, PointerEvent } from 'react'
import { JobKeyChips } from '@/components/JobMetaBadges'
import { ScoreEditor } from '@/components/ScoreEditor'
import { workModelLabel } from '@/components/WorkModelBadge'
import { Button } from '@/components/ui/button'
import type { JobCard } from '@/lib/api'

type Props = {
  job: JobCard
  onScoreSaved?: () => void
  onLinkClick?: (e: MouseEvent | PointerEvent) => void
}

export function listingHref(job: JobCard): string | null {
  const raw = (job.application_url || job.url || '').trim()
  if (!raw || raw === 'None' || raw === 'null') return null
  return raw
}

export function placeLine(job: Pick<JobCard, 'location' | 'work_model'>): string {
  const work = workModelLabel(job.work_model)
  const loc = job.location?.trim()
  if (loc && work && !loc.toLowerCase().includes(work.toLowerCase())) return `${loc} · ${work}`
  return loc || work || 'Location not stated'
}

export function JobSummary({ job, onScoreSaved, onLinkClick }: Props) {
  const href = listingHref(job)
  const salary = job.salary?.trim()

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-sm leading-snug font-semibold text-foreground">{job.title || 'Untitled'}</h3>
          <p className="mt-0.5 truncate text-caption text-muted-foreground">{job.company || job.site || 'Unknown company'}</p>
        </div>
        <ScoreEditor job={job} onSaved={onScoreSaved} className="-mt-px" />
      </div>

      <div className="flex items-end gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="space-y-0.5 text-caption text-muted-foreground">
            <p className="flex min-w-0 items-center gap-1.5">
              <MapPin className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate">{placeLine(job)}</span>
            </p>
            {salary ? (
              <p className="flex min-w-0 items-center gap-1.5">
                <Banknote className="size-3.5 shrink-0" aria-hidden />
                <span className="truncate">{salary}</span>
              </p>
            ) : null}
          </div>
          <div className="flex min-w-0 flex-wrap gap-1.5 empty:hidden">
            <JobKeyChips job={job} />
          </div>
        </div>
        {href ? (
          <Button
            asChild
            type="button"
            size="icon-sm"
            variant="ghost"
            className="-mr-1.5 -mb-1 size-7 text-muted-foreground hover:text-foreground md:size-7"
            onClick={onLinkClick}
            onPointerDown={onLinkClick}
          >
            <a href={href} target="_blank" rel="noreferrer" aria-label={`Open ${job.title || 'job'} posting`}>
              <ExternalLink className="size-3.5" />
            </a>
          </Button>
        ) : null}
      </div>
    </div>
  )
}

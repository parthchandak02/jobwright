import { Building2, DollarSign, ExternalLink, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  JobCardBody,
  JobCardChips,
  JobCardFooter,
  JobCardHeader,
  JobCardLinkAnchor,
  JobCardMeta,
  JobCardScoreAnchor,
  JobCardSubtitle,
  JobCardTitle,
} from '@/components/JobCardLayout'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { MetaField } from '@/components/MetaField'
import { ScoreEditor } from '@/components/ScoreEditor'
import { SponsorshipBadge } from '@/components/SponsorshipBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import type { JobCard } from '@/lib/api'
import type { MouseEvent, PointerEvent } from 'react'

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

/** Shared title, company, meta rows, chips, score, and listing link used by cards and drawer. */
export function JobSummary({ job, onScoreSaved, onLinkClick }: Props) {
  const href = listingHref(job)

  return (
    <>
      <JobCardScoreAnchor>
        <ScoreEditor
          job={job}
          onSaved={onScoreSaved}
          className="flex size-[var(--job-card-action-size)] items-center justify-center"
        />
      </JobCardScoreAnchor>

      {href ? (
        <JobCardLinkAnchor>
          <Button
            asChild
            type="button"
            size="icon-sm"
            variant="ghost"
            className="size-[var(--job-card-action-size)] shrink-0 text-muted-foreground hover:text-foreground"
            onClick={onLinkClick}
            onPointerDown={onLinkClick}
          >
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${job.title || 'job'} listing`}
            >
              <ExternalLink className="size-3.5" />
            </a>
          </Button>
        </JobCardLinkAnchor>
      ) : null}

      <JobCardBody>
        <JobCardHeader>
          <JobCardTitle>{job.title || 'Untitled'}</JobCardTitle>
          <JobCardSubtitle>
            <Building2 className="size-3 shrink-0" />
            {job.company || job.site || 'Unknown'}
          </JobCardSubtitle>
        </JobCardHeader>

        <JobCardMeta>
          <MetaField icon={MapPin} label="Location" value={job.location} />
          <MetaField icon={DollarSign} label="Salary" value={job.salary} />
        </JobCardMeta>

        <JobCardFooter className={href ? 'job-card-footer--with-link' : undefined}>
          <JobCardChips>
            <WorkModelBadge workModel={job.work_model} />
            <SponsorshipBadge status={job.sponsorship_status} />
            <JobMetaBadges job={job} />
          </JobCardChips>
        </JobCardFooter>
      </JobCardBody>
    </>
  )
}

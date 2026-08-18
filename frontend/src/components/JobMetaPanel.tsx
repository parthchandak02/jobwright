import { DollarSign, MapPin } from 'lucide-react'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { JobCardChips, JobCardMeta } from '@/components/JobCardLayout'
import { MetaField } from '@/components/MetaField'
import { SponsorshipBadge } from '@/components/SponsorshipBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import type { JobCard } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  job: Pick<JobCard, 'location' | 'salary' | 'work_model' | 'sponsorship_status' | 'source' | 'has_resume' | 'has_cover' | 'outcome' | 'whatsapp_notified_at'>
  className?: string
}

/** Shared location/salary rows + status chips for cards and drawer. */
export function JobMetaPanel({ job, className }: Props) {
  return (
    <div className={cn('job-card-stack', className)}>
      <JobCardMeta>
        <MetaField icon={MapPin} label="Location" value={job.location} />
        <MetaField icon={DollarSign} label="Salary" value={job.salary} />
      </JobCardMeta>
      <JobCardChips>
        <WorkModelBadge workModel={job.work_model} />
        <SponsorshipBadge status={job.sponsorship_status} />
        <JobMetaBadges job={job} />
      </JobCardChips>
    </div>
  )
}

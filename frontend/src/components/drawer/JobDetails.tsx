import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { DrawerSection } from '@/components/DrawerSection'
import { workModelLabel } from '@/components/WorkModelBadge'
import type { JobCard } from '@/lib/api'
import { fmtDay } from './format'

const SPONSORSHIP: Record<string, string> = {
  required: 'Employer would need to sponsor',
  not_required: 'US citizens or green card holders only',
  not_found: 'Not mentioned',
}

function foundText(job: JobCard): string {
  const day = fmtDay(job.discovered_at)
  if (job.source === 'manual') return `Added by you${day ? ` · ${day}` : ''}`
  return [day, job.site ? `on ${job.site}` : null].filter(Boolean).join(' ')
}

export function JobDetails({ job }: { job: JobCard }) {
  return (
    <DrawerSection title="Details">
      <DetailGrid className="space-y-2">
        <DetailRow label="Location" value={job.location || 'Not stated'} />
        <DetailRow label="Work model" value={workModelLabel(job.work_model) || 'Not stated'} />
        <DetailRow label="Pay" value={job.salary || 'Not stated'} />
        <DetailRow label="Sponsorship" value={SPONSORSHIP[job.sponsorship_status] || SPONSORSHIP.not_found} />
        <DetailRow label="Found" value={foundText(job)} />
        {job.applied_at ? <DetailRow label="Applied" value={fmtDay(job.applied_at)} /> : null}
        {job.whatsapp_notified_at ? <DetailRow label="On WhatsApp" value={`Sent ${fmtDay(job.whatsapp_notified_at)}`} /> : null}
        {job.is_dead ? <DetailRow label="Posting" value="No longer accepting applications" /> : null}
      </DetailGrid>
    </DrawerSection>
  )
}

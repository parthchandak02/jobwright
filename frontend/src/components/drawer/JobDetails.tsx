import type { ReactNode } from 'react'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { DrawerSection } from '@/components/DrawerSection'
import { placeLine } from '@/components/JobSummary'
import type { JobCard } from '@/lib/api'
import { compactPay } from '@/lib/pay'
import { fmtDay } from './format'

const SPONSORSHIP: Record<string, string> = {
  required: 'Employer would need to sponsor',
  not_required: 'US citizens or green card holders only',
}

function foundText(job: JobCard): string {
  const day = fmtDay(job.discovered_at)
  if (job.source === 'manual') return `Added by you${day ? ` · ${day}` : ''}`
  return [day, job.site ? `on ${job.site}` : null].filter(Boolean).join(' ')
}

/** Facts about the job. Rows with nothing useful to say are left out. */
export function JobDetails({ job, stage }: { job: JobCard; stage?: ReactNode }) {
  const pay = compactPay(job.salary)
  const sponsorship = SPONSORSHIP[job.sponsorship_status]
  return (
    <DrawerSection title="Details">
      <DetailGrid className="space-y-2">
        {stage ? (
          <div className="grid grid-cols-[6.5rem_1fr] items-center gap-x-3 text-body">
            <dt className="text-muted-foreground">Stage</dt>
            <dd className="min-w-0">{stage}</dd>
          </div>
        ) : null}
        <DetailRow label="Where" value={placeLine(job)} />
        {pay ? <DetailRow label="Pay" value={pay} /> : null}
        {sponsorship ? <DetailRow label="Visa" value={sponsorship} /> : null}
        <DetailRow label="Found" value={foundText(job)} />
        {job.applied_at ? <DetailRow label="Applied" value={fmtDay(job.applied_at)} /> : null}
        {job.whatsapp_notified_at ? <DetailRow label="On WhatsApp" value={`Sent ${fmtDay(job.whatsapp_notified_at)}`} /> : null}
        {job.is_dead ? <DetailRow label="Posting" value="Closed" /> : null}
      </DetailGrid>
    </DrawerSection>
  )
}

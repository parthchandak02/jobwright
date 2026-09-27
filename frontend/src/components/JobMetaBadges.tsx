import type { LucideIcon } from 'lucide-react'
import {
  Ban,
  BellRing,
  CheckCheck,
  CheckCircle,
  FileText,
  Ghost,
  Mail,
  PenLine,
  Undo2,
  XCircle,
} from 'lucide-react'
import { Chip } from '@/components/Chip'
import type { JobCard } from '@/lib/api'

type Props = {
  job: Pick<
    JobCard,
    | 'source'
    | 'has_resume'
    | 'has_cover'
    | 'outcome'
    | 'is_dead'
    | 'whatsapp_notified_at'
    | 'followup_due'
    | 'applied_days_ago'
  >
}

function formatNotified(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export function followUpLabel(days: number | null | undefined): string {
  if (days == null) return 'Follow up?'
  return `Follow up? Applied ${days} day${days === 1 ? '' : 's'} ago`
}

const OUTCOME_ICONS: Record<string, LucideIcon> = {
  accepted: CheckCircle,
  rejected: XCircle,
  withdrawn: Undo2,
  ghosted: Ghost,
  cancelled: Ban,
}

export function JobMetaBadges({ job }: Props) {
  const hasAny =
    job.source === 'manual' ||
    job.has_resume ||
    job.has_cover ||
    job.outcome ||
    job.is_dead ||
    job.whatsapp_notified_at ||
    job.followup_due
  if (!hasAny) return null

  const outcomeIcon = job.outcome
    ? OUTCOME_ICONS[job.outcome.toLowerCase()] || Ban
    : undefined

  return (
    <>
      {job.followup_due && (
        <Chip icon={BellRing} tone="--stage-in-progress" title="No reply yet. A short follow-up note can help.">
          {followUpLabel(job.applied_days_ago)}
        </Chip>
      )}
      {job.is_dead && (
        <Chip
          icon={Ban}
          tone="--destructive"
          title="Posting is dead: no longer accepting applications (checked automatically)"
        >
          DEAD
        </Chip>
      )}
      {job.source === 'manual' && (
        <Chip icon={PenLine}>manual</Chip>
      )}
      {job.has_resume && (
        <Chip icon={FileText} title="Tailored resume generated">resume</Chip>
      )}
      {job.has_cover && (
        <Chip icon={Mail} title="Cover letter generated">cover</Chip>
      )}
      {job.whatsapp_notified_at && (
        <Chip
          icon={CheckCheck}
          tone="--stage-offer"
          title={`Notified on WhatsApp ${formatNotified(job.whatsapp_notified_at)}`}
        >
          WhatsApp
        </Chip>
      )}
      {job.outcome && (
        <Chip icon={outcomeIcon} muted>
          {job.outcome}
        </Chip>
      )}
    </>
  )
}

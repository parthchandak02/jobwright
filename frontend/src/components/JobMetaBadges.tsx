import type { LucideIcon } from 'lucide-react'
import {
  Ban,
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
    'source' | 'has_resume' | 'has_cover' | 'outcome' | 'whatsapp_notified_at'
  >
}

function formatNotified(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
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
    job.whatsapp_notified_at
  if (!hasAny) return null

  const outcomeIcon = job.outcome
    ? OUTCOME_ICONS[job.outcome.toLowerCase()] || Ban
    : undefined

  return (
    <>
      {job.source === 'manual' && (
        <Chip icon={PenLine}>manual</Chip>
      )}
      {job.has_resume && (
        <Chip icon={FileText}>resume</Chip>
      )}
      {job.has_cover && (
        <Chip icon={Mail}>cover</Chip>
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

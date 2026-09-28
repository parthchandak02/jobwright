import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  Ban,
  BellRing,
  CheckCircle,
  Copy,
  FileCheck2,
  FileText,
  Ghost,
  Mail,
  MapPinOff,
  OctagonAlert,
  PenLine,
  Undo2,
  XCircle,
} from 'lucide-react'
import { Chip } from '@/components/Chip'
import { OUTCOME_LABELS, type JobCard } from '@/lib/api'
import { useDealbreakerLabels } from '@/lib/reasons'

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
  duplicate: Copy,
}

export type JobChip = {
  key: string
  label: string
  icon: LucideIcon
  tone?: string
  muted?: boolean
  title?: string
  kind: 'alert' | 'materials' | 'info'
}

export function prettyId(id: string): string {
  return id.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export function jobChips(job: JobCard, dealLabels: Record<string, string>): JobChip[] {
  const chips: JobChip[] = []
  const closed = job.funnel_stage === 'closed'
  if (job.is_dead && !closed) {
    chips.push({ key: 'dead', kind: 'alert', label: 'Posting closed', icon: Ban, tone: '--destructive', title: 'No longer accepting applications (checked automatically)' })
  }
  if (job.followup_due) {
    chips.push({ key: 'followup', kind: 'alert', label: 'Follow up', icon: BellRing, tone: '--stage-in-progress', title: `${followUpLabel(job.applied_days_ago)}. No reply yet.` })
  }
  const deal = (job.dealbreakers || [])[0]
  if (deal && !closed) {
    const name = dealLabels[deal] || prettyId(deal)
    chips.push({ key: 'deal', kind: 'alert', label: name, icon: Ban, tone: '--destructive', title: `Dealbreaker: ${name}` })
  } else if (job.location_ok === false && !closed) {
    chips.push({ key: 'location', kind: 'alert', label: 'Location doesn’t work', icon: MapPinOff, tone: '--destructive' })
  }
  if (closed && job.duplicate_of) {
    chips.push({ key: 'dup', kind: 'info', label: 'Duplicate', icon: Copy, muted: true, title: `Duplicate of ${job.duplicate_of.title || 'another posting'}` })
  } else if (closed && job.outcome) {
    const o = job.outcome.toLowerCase()
    chips.push({ key: 'outcome', kind: 'info', label: OUTCOME_LABELS[o] || prettyId(o), icon: OUTCOME_ICONS[o] || Ban, muted: true })
  }
  if (job.has_resume && job.has_cover) {
    chips.push({ key: 'both', kind: 'materials', label: 'Resume + letter', icon: FileCheck2, title: 'Tailored resume and cover letter ready' })
  } else if (job.has_resume) {
    chips.push({ key: 'resume', kind: 'materials', label: 'Resume ready', icon: FileText, title: 'Tailored resume ready' })
  } else if (job.has_cover) {
    chips.push({ key: 'cover', kind: 'materials', label: 'Letter ready', icon: Mail, title: 'Tailored cover letter ready' })
  }
  const concern = (job.concerns || []).find((c) => !(job.dealbreakers || []).includes(c))
  if (concern && !closed) {
    const name = dealLabels[concern] || prettyId(concern)
    chips.push({ key: 'concern', kind: 'info', label: `Partly: ${name}`, icon: AlertTriangle, title: `Partly matches a dealbreaker: ${name}` })
  }
  if (job.sponsorship_status === 'not_required') {
    chips.push({ key: 'sponsor', kind: 'info', label: 'No sponsorship', icon: OctagonAlert, title: 'Needs US citizenship or a green card' })
  }
  if (job.source === 'manual') {
    chips.push({ key: 'manual', kind: 'info', label: 'Added by you', icon: PenLine })
  }
  return chips
}

function renderChip(c: JobChip) {
  return (
    <Chip key={c.key} icon={c.icon} tone={c.tone} muted={c.muted} title={c.title} className="max-w-full">
      {c.label}
    </Chip>
  )
}

export function JobKeyChips({ job, max = 2, kinds }: { job: JobCard; max?: number; kinds?: JobChip['kind'][] }) {
  const labels = useDealbreakerLabels()
  const chips = jobChips(job, labels).filter((c) => !kinds || kinds.includes(c.kind))
  if (!chips.length) return null
  return <>{chips.slice(0, max).map(renderChip)}</>
}

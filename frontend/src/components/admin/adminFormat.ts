import { toast } from 'sonner'
import type { AccessSyncResult, AdminOverviewUser } from '@/lib/api'

export function reportAccessSync(result: AccessSyncResult | undefined) {
  if (result && !result.ok) toast.error(`Cloudflare Access sync failed: ${result.error}`)
}

export type PersonStatus = 'ok' | 'warn' | 'fail' | 'pending' | 'none'

export function personStatus(u: AdminOverviewUser): PersonStatus {
  if (u.error) return 'fail'
  if (!u.setup_complete) return 'pending'
  const level = u.health?.level
  if (level === 'fail') return 'fail'
  if (level === 'warn') return 'warn'
  if (level === 'ok') return 'ok'
  return 'none'
}

export const STATUS_LABEL: Record<PersonStatus, string> = {
  ok: 'Healthy',
  warn: 'Warning',
  fail: 'Problem',
  pending: 'Setup pending',
  none: 'No daily list yet',
}

export const STATUS_TONE: Record<PersonStatus, string | undefined> = {
  ok: '--stage-offer',
  warn: '--stage-in-progress',
  fail: '--destructive',
  pending: undefined,
  none: undefined,
}

export function fmtTime(hour: number | null, minute: number | null): string {
  if (hour == null) return '—'
  return new Date(2000, 0, 1, hour, minute ?? 0).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function toTimeValue(hour: number | null, minute: number | null): string {
  if (hour == null) return ''
  return `${String(hour).padStart(2, '0')}:${String(minute ?? 0).padStart(2, '0')}`
}

const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })

export function fmtTokens(n: number): string {
  return compact.format(n)
}

export function fmtCost(cost: AdminOverviewUser['cost_30d'] | null | undefined): string {
  if (!cost) return '—'
  if (cost.cost_usd != null) return `$${cost.cost_usd.toFixed(2)}`
  return cost.tokens ? `${compact.format(cost.tokens)} tok` : '—'
}

export function fmtTopN(n: number): string {
  return n ? `top ${n}` : 'all'
}

function dayLabel(d: Date): string {
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function fmtLastBrief(u: AdminOverviewUser): string {
  const b = u.last_brief
  if (!b?.at) return 'No daily list sent yet'
  const d = new Date(b.at)
  const when = `${dayLabel(d)} ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  if (b.status === 'failed') return `${when} · failed`
  if (b.status === 'skipped') return `${when} · nothing new to send`
  return `${when} · ${b.notified ?? 0} sent`
}

export function scheduleLabel(hour: number, minute: number): string {
  return `Every day at ${fmtTime(hour, minute)}`
}

export function chatName(name: string | null | undefined): string | null {
  return name ? name.replace(/^whatsapp:/, '') : null
}

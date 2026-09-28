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
  const brief = u.last_brief
  if (brief?.status === 'failed') return 'fail'
  if (brief?.at) return 'ok'
  return 'none'
}

export const STATUS_LABEL: Record<PersonStatus, string> = {
  ok: 'Healthy',
  warn: 'Needs attention',
  fail: 'Problem',
  pending: 'Setup pending',
  none: 'No list sent yet',
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

export function fmtUsd(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v > 0 && v < 0.01) return '<$0.01'
  return `$${v.toFixed(2)}`
}

/** AI usage in plain words: cost when priced, otherwise the token count. */
export function fmtUsage(cost: AdminOverviewUser['cost_30d'] | null | undefined): string {
  if (!cost) return '—'
  if (cost.cost_usd != null) return fmtUsd(cost.cost_usd)
  return cost.tokens ? `${compact.format(cost.tokens)} tokens` : 'None'
}

export function usageTitle(cost: AdminOverviewUser['cost_30d'] | null | undefined): string | undefined {
  if (!cost?.tokens) return undefined
  const priced = cost.cost_usd != null ? ` (about ${fmtUsd(cost.cost_usd)})` : ''
  return `${cost.tokens.toLocaleString()} tokens in the last 30 days${priced}`
}

export function fmtTopN(n: number): string {
  return n ? `Top ${n}` : 'All'
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
  if (!b?.at) return 'No list sent yet'
  const d = new Date(b.at)
  const when = `${dayLabel(d)} ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  if (b.status === 'failed') return `${when} · failed`
  if (b.status === 'skipped') return `${when} · nothing new to send`
  const n = b.notified ?? 0
  return `${when} · ${n} job${n === 1 ? '' : 's'} sent`
}

export function scheduleLabel(hour: number, minute: number): string {
  return `Every day at ${fmtTime(hour, minute)}`
}

const RAW_ID = /^(whatsapp:)?[\d+\-@.a-z]*\d{6,}[\d@.a-z]*$/i

function lastDigits(s: string): string {
  const digits = s.replace(/\D/g, '')
  return digits.slice(-4)
}

/** Chat name for display. Raw ids (no name from WhatsApp) become "Unnamed group · …4902". */
export function chatDisplay(
  name: string | null | undefined,
  target?: string | null,
  type?: 'group' | 'dm' | null,
): { label: string; unnamed: boolean } | null {
  const clean = name?.replace(/^whatsapp:/, '').trim()
  if (clean && !RAW_ID.test(clean)) return { label: clean, unnamed: false }
  const raw = clean || target?.replace(/^whatsapp:/, '') || ''
  if (!raw) return null
  const group = type ? type === 'group' : raw.includes('@g.us') || raw.replace(/\D/g, '').length > 15
  const tail = lastDigits(raw)
  return { label: `${group ? 'Unnamed group' : 'Direct chat'}${tail ? ` · …${tail}` : ''}`, unnamed: true }
}

export function chatName(name: string | null | undefined, target?: string | null): string | null {
  return chatDisplay(name, target)?.label ?? null
}

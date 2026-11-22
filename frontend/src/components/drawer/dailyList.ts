import type { JobCard } from '@/lib/api'

/** Lists older than this are history, not something she is working through. */
export const DAILY_LIST_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

type ListJob = Pick<JobCard, 'job_id' | 'whatsapp_notified_at' | 'funnel_stage' | 'fit_score' | 'title'>

export type DailyList<J extends ListJob = ListJob> = {
  /** The send's stamp (every job in one WhatsApp message shares it). */
  sentAt: string
  /** 1-based place of the open job on the list. */
  position: number
  total: number
  /** Previous job before the open one (in list order) that is not Applied or Closed; null when none. */
  prev: J | null
  /** Next job after the open one (wrapping round) that is not Applied or Closed; null when none. */
  next: J | null
  /** Every job on the list is Applied (or later) or Closed. */
  done: boolean
}

const OPEN_STAGES = new Set(['backlog', 'prepare'])

/**
 * The daily WhatsApp list the open job came on: jobs sharing its ``whatsapp_notified_at``, in
 * the list's order (best match first, as notify sends them), or null when the job was not on a
 * list. Send order is not stored, so ties keep a stable job_id order.
 */
export function dailyListFor<J extends ListJob>(jobs: J[], jobId: string | null | undefined): DailyList<J> | null {
  if (!jobId) return null
  const open = jobs.find((j) => j.job_id === jobId)
  const sentAt = open?.whatsapp_notified_at
  if (!sentAt) return null
  const list = jobs
    .filter((j) => j.whatsapp_notified_at === sentAt)
    .sort((a, b) => (b.fit_score ?? -1) - (a.fit_score ?? -1) || a.job_id.localeCompare(b.job_id))
  const at = list.findIndex((j) => j.job_id === jobId)
  const prev =
    list
      .slice(0, at)
      .reverse()
      .find((j) => OPEN_STAGES.has(j.funnel_stage)) ?? null
  const rest = [...list.slice(at + 1), ...list.slice(0, at)]
  const next = rest.find((j) => OPEN_STAGES.has(j.funnel_stage)) ?? null
  const done = list.every((j) => !OPEN_STAGES.has(j.funnel_stage))
  return { sentAt, position: at + 1, total: list.length, prev, next, done }
}

/** Whether a send is recent enough to step through (the last 7 days). */
export function isRecentList(sentAt: string, now: Date = new Date()): boolean {
  const t = new Date(sentAt).getTime()
  return Number.isFinite(t) && now.getTime() - t <= DAILY_LIST_MAX_AGE_MS
}

/** "today's list", "yesterday's list", else the weekday, e.g. "Tue's list". */
export function listDayLabel(sentAt: string, now: Date = new Date()): string {
  const sent = new Date(sentAt)
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const daysAgo = Math.round((day(now) - day(sent)) / 86_400_000)
  if (daysAgo <= 0) return "today's list"
  if (daysAgo === 1) return "yesterday's list"
  return `${sent.toLocaleDateString(undefined, { weekday: 'short' })}'s list`
}

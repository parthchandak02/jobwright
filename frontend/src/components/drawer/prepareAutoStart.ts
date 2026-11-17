/** True when ``iso`` falls on the same UTC calendar day as ``now``. */
export function isUtcToday(iso: string | null | undefined, now: Date = new Date()): boolean {
  if (!iso) return false
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return false
  return d.toISOString().slice(0, 10) === now.toISOString().slice(0, 10)
}

/**
 * Whether opening a job should start the same prepare run as the Prepare button.
 *
 * Only today's WhatsApp daily-list picks (notified today), backlog/prepare, no
 * materials, after the drawer job + materials match the open key. Skips when
 * auto-Prepare already claimed today (server stamp).
 */
export function shouldAutoStartPrepare(input: {
  jobId: string | null | undefined
  jobKey: string | null | undefined
  /** Materials fetch finished for this jobKey (not a stale prior job). */
  materialsReady: boolean
  funnelStage: string | null | undefined
  hasResume: boolean
  hasCover: boolean
  /** Markdown already loaded in the drawer (covers a stale has_resume flag). */
  hasResumeMd?: boolean
  hasCoverMd?: boolean
  /** Stamped when the job was on today's WhatsApp list. */
  whatsappNotifiedAt?: string | null
  /** Server claim: auto-Prepare already fired today. */
  prepareAutoStartedAt?: string | null
  now?: Date
}): boolean {
  if (!input.jobKey || input.jobId !== input.jobKey) return false
  if (!input.materialsReady) return false
  if (input.funnelStage !== 'backlog' && input.funnelStage !== 'prepare') return false
  if (input.hasResume || input.hasCover || input.hasResumeMd || input.hasCoverMd) return false
  const now = input.now ?? new Date()
  if (!isUtcToday(input.whatsappNotifiedAt, now)) return false
  if (isUtcToday(input.prepareAutoStartedAt, now)) return false
  return true
}

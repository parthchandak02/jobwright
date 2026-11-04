/** Helpers for the daily-list cron (5 fields: minute hour day-of-month month day-of-week). */

export const DEFAULT_CRON = '0 7 * * *'

function fields(cron: string | undefined | null): string[] | null {
  const parts = (cron || DEFAULT_CRON).trim().split(/\s+/)
  return parts.length === 5 ? parts : null
}

function single(field: string, max: number): number | null {
  if (!/^\d{1,2}$/.test(field)) return null
  const n = Number(field)
  return n <= max ? n : null
}

/** "HH:MM" when minute and hour are single numbers, else null (custom schedule such as "0 *\/3 * * *"). */
export function cronToTime(cron: string | undefined | null): string | null {
  const f = fields(cron)
  if (!f) return null
  const m = single(f[0], 59)
  const h = single(f[1], 23)
  if (m == null || h == null) return null
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** True when the time picker can edit this schedule without losing anything. */
export function isSimpleTimeCron(cron: string | undefined | null): boolean {
  return cronToTime(cron) != null
}

/**
 * Replace only the minute and hour of `cron` with `time` ("HH:MM"); day-of-month, month and
 * day-of-week are kept. Returns null for a bad time or a schedule the picker can't edit.
 */
export function withCronTime(cron: string | undefined | null, time: string): string | null {
  const f = fields(cron)
  const match = /^(\d{1,2}):(\d{2})$/.exec(time.trim())
  if (!f || !match || !isSimpleTimeCron(cron)) return null
  const h = Number(match[1])
  const m = Number(match[2])
  if (h > 23 || m > 59) return null
  return [String(m), String(h), f[2], f[3], f[4]].join(' ')
}

/** Plain words for which days a simple-time schedule runs on ("Every day", "Weekdays", or null when custom). */
export function cronDays(cron: string | undefined | null): string | null {
  const f = fields(cron)
  if (!f) return null
  const [, , dom, month, dow] = f
  if (dom !== '*' || month !== '*') return null
  if (dow === '*' || dow === '0-6' || dow === '1-7') return 'Every day'
  if (dow === '1-5' || dow === 'mon-fri' || dow === 'MON-FRI') return 'Weekdays'
  if (dow === '0,6' || dow === '6,0' || dow === 'sat,sun' || dow === 'SAT,SUN') return 'Weekends'
  return null
}

import type { ApplyVia, ConnectedClaude } from '@/lib/api'

/** "today", "yesterday", "3 days ago", or a date, from a unix time in seconds. */
export function relativeDay(seconds: number | null | undefined, now: Date = new Date()): string {
  if (!seconds) return 'never'
  const then = new Date(seconds * 1000)
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOf(now) - startOf(then)) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** One line for a connected Claude: what it may do and when it was last used. */
export function describeClient(c: ConnectedClaude, now: Date = new Date()): string {
  const may = c.scopes.includes('apply')
    ? 'can apply for you'
    : c.scopes.includes('jobs:write')
      ? 'can change your board'
      : 'can read your board'
  return `${may} · connected ${relativeDay(c.created_at, now)} · last used ${relativeDay(c.last_used_at, now)}`
}

export const APPLY_VIA_OPTIONS: { value: ApplyVia; label: string; hint: string }[] = [
  {
    value: 'connector',
    label: 'My Claude',
    hint: 'Your own Claude fills applications in your browser, with your saved answers only.',
  },
  { value: 'off', label: 'Nobody', hint: 'No applications are sent for you. You can still apply by hand.' },
  { value: 'server', label: 'jobwright', hint: 'The operator’s server applies for you (admins only).' },
]

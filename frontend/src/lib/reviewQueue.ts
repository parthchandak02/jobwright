import type { BoardResponse, JobCard } from '@/lib/api'

/** Quick review (`/review`): one Backlog job at a time, best match first. Pure helpers. */

export type ReviewAnswer = 'interested' | 'not_for_me' | 'skip'
export type ReviewFilter = 'strong' | 'all'

/** "Strong only" chip: the same 7+ line as the score pill's "Strong". */
export const STRONG_MIN = 7

/** Backlog jobs the person hasn't rated yet. */
export function isReviewable(job: Pick<JobCard, 'funnel_stage' | 'user_fit_score'>): boolean {
  return (job.funnel_stage || 'backlog') === 'backlog' && job.user_fit_score == null
}

/** Best AI score first (unscored last), then more confident, then newest. */
export function compareForReview(a: JobCard, b: JobCard): number {
  const sa = a.fit_score ?? -1
  const sb = b.fit_score ?? -1
  if (sa !== sb) return sb - sa
  const ca = a.score_confidence ?? 0
  const cb = b.score_confidence ?? 0
  if (ca !== cb) return cb - ca
  return (b.discovered_at || '').localeCompare(a.discovered_at || '')
}

/** Unrated Backlog jobs in review order. */
export function buildQueue(board: BoardResponse | null): JobCard[] {
  if (!board) return []
  return (board.columns.backlog || []).filter(isReviewable).sort(compareForReview)
}

/** How many Backlog jobs still need a look (the board's "Review N" button). */
export function reviewCount(board: BoardResponse | null): number {
  if (!board) return 0
  return (board.columns.backlog || []).reduce((n, j) => n + (isReviewable(j) ? 1 : 0), 0)
}

export function inFilter(job: Pick<JobCard, 'fit_score'>, filter: ReviewFilter): boolean {
  return filter === 'all' || (job.fit_score ?? 0) >= STRONG_MIN
}

/**
 * Keep the session's order stable while the board refreshes: ids already in the
 * session stay where they were; new reviewable jobs are slotted in by score after them.
 */
export function mergeQueue(prevIds: string[], fresh: JobCard[]): string[] {
  const known = new Set(prevIds)
  return [...prevIds, ...fresh.filter((j) => !known.has(j.job_id)).map((j) => j.job_id)]
}

export type ReviewPosition = {
  /** Job to show now, or null when everything in the filter is answered. */
  current: string | null
  /** 1-based number of the current job ("12 of 143"); equals answered + 1. */
  number: number
  answered: number
  total: number
}

export function reviewPosition(
  ids: string[],
  jobs: Record<string, Pick<JobCard, 'fit_score'> | undefined>,
  answers: Record<string, ReviewAnswer | undefined>,
  filter: ReviewFilter,
): ReviewPosition {
  let total = 0
  let answered = 0
  let current: string | null = null
  for (const id of ids) {
    const job = jobs[id]
    if (!job || !inFilter(job, filter)) continue
    total += 1
    if (answers[id]) answered += 1
    else if (current == null) current = id
  }
  return { current, number: Math.min(answered + 1, total), answered, total }
}

/** The next unanswered ids after `current` (to prefetch descriptions). */
export function upcoming(
  ids: string[],
  jobs: Record<string, Pick<JobCard, 'fit_score'> | undefined>,
  answers: Record<string, ReviewAnswer | undefined>,
  filter: ReviewFilter,
  count = 2,
): string[] {
  const out: string[] = []
  for (const id of ids) {
    const job = jobs[id]
    if (!job || answers[id] || !inFilter(job, filter)) continue
    out.push(id)
    if (out.length > count) break
  }
  return out.slice(1)
}

export type SessionCounts = Record<ReviewAnswer, number>

export function sessionCounts(answers: Record<string, ReviewAnswer | undefined>): SessionCounts {
  const counts: SessionCounts = { interested: 0, not_for_me: 0, skip: 0 }
  for (const a of Object.values(answers)) if (a) counts[a] += 1
  return counts
}

/** Forget skips so the skipped jobs come round again. */
export function clearSkips(answers: Record<string, ReviewAnswer | undefined>): Record<string, ReviewAnswer> {
  const next: Record<string, ReviewAnswer> = {}
  for (const [id, a] of Object.entries(answers)) if (a && a !== 'skip') next[id] = a
  return next
}

export type ReviewKey = ReviewAnswer | 'undo' | 'posting' | 'open' | { reason: number }

/** Keyboard map. Returns null for keys the page should ignore (typing, other shortcuts). */
export function keyAction(e: Pick<KeyboardEvent, 'key' | 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey'>): ReviewKey | null {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'z') return 'undo'
  if (e.metaKey || e.ctrlKey || e.altKey) return null
  switch (e.key) {
    case 'ArrowRight':
    case 'i':
    case 'I':
      return 'interested'
    case 'ArrowLeft':
    case 'n':
    case 'N':
      return 'not_for_me'
    case 'ArrowDown':
    case 's':
    case 'S':
      return 'skip'
    case 'u':
    case 'U':
      return 'undo'
    case 'o':
    case 'O':
      return 'posting'
    case 'f':
    case 'F':
      return 'open'
  }
  if (/^[1-9]$/.test(e.key)) return { reason: Number(e.key) - 1 }
  return null
}

/** Horizontal swipe result: commit when dragged past `threshold` px, else snap back. */
export function swipeAnswer(dx: number, threshold: number): ReviewAnswer | null {
  if (dx >= threshold) return 'interested'
  if (dx <= -threshold) return 'not_for_me'
  return null
}

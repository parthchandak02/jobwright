/** Away at least this long before "Did you apply?" is worth asking. */
export const MIN_AWAY_MS = 30_000

/** One tap on Open posting: which job, when she left, and whether we already asked. */
export type PostingVisit = { jobId: string; leftAt: number; asked: boolean }

/**
 * Whether returning to the tab should ask "Did you apply?" for the open job.
 *
 * Only for the job whose posting she opened, still in Backlog or Prepare, after at
 * least ``minAwayMs`` away, and once per visit (``asked`` covers Not yet).
 */
export function shouldAskApplied(input: {
  visit: PostingVisit | null
  jobId: string | null | undefined
  funnelStage: string | null | undefined
  now: number
  minAwayMs?: number
}): boolean {
  const { visit } = input
  if (!visit || visit.asked) return false
  if (!input.jobId || visit.jobId !== input.jobId) return false
  if (input.funnelStage !== 'backlog' && input.funnelStage !== 'prepare') return false
  return input.now - visit.leftAt >= (input.minAwayMs ?? MIN_AWAY_MS)
}

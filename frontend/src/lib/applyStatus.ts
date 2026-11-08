import type { ApplyPick } from '@/lib/api'

/** One sentence about an automatic-apply pick for the job drawer (null = say nothing). */
export function pickSummary(pick: ApplyPick, now: Date = new Date()): string | null {
  const when = new Date(pick.apply_after)
  const time = when.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  switch (pick.status) {
    case 'planned':
      return when > now ? `jobwright will apply to this job at ${time}.` : 'jobwright is about to apply to this job.'
    case 'running':
      return 'jobwright is applying to this job now.'
    case 'vetoed':
      return 'You skipped this job for automatic applications.'
    case 'applied':
      return 'jobwright applied to this job and saw the confirmation.'
    case 'failed':
      return 'jobwright tried to apply to this job but could not confirm it went through.'
    case 'skipped':
      return 'jobwright skipped this job; it needs something from you.'
    default:
      return null
  }
}

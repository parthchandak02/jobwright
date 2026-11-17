/**
 * Whether opening a job should start the same prepare run as the Prepare button
 * (backlog/prepare, no tailored resume or cover yet).
 */
export function shouldAutoStartPrepare(input: {
  funnelStage: string | null | undefined
  hasResume: boolean
  hasCover: boolean
  /** Markdown already loaded in the drawer (covers a stale has_resume flag). */
  hasResumeMd?: boolean
  hasCoverMd?: boolean
}): boolean {
  if (input.funnelStage !== 'backlog' && input.funnelStage !== 'prepare') return false
  if (input.hasResume || input.hasCover || input.hasResumeMd || input.hasCoverMd) return false
  return true
}

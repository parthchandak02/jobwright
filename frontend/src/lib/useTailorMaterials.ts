import { toast } from 'sonner'
import { useCallback, useEffect } from 'react'
import { listRuns, startJobTailorCover, startJobTailorResume } from '@/lib/api'
import { useRunTracker, type AutoSearch } from '@/lib/useRunStream'
import { errorMessage } from '@/lib/utils'

export type TailorScope = 'resume' | 'cover'

export const RESUME_TAILOR_STAGES = ['tailor', 'docx'] as const
export const COVER_TAILOR_STAGES = ['cover', 'docx'] as const

const STAGES_BY_SCOPE: Record<TailorScope, readonly string[]> = {
  resume: RESUME_TAILOR_STAGES,
  cover: COVER_TAILOR_STAGES,
}

/**
 * Per-job resume or cover tailor run with SSE logs (built on `useRunTracker`).
 */
export function useTailorMaterials(
  jobKey: string | undefined,
  scope: TailorScope,
  onDone: () => void,
): AutoSearch {
  const run = useRunTracker({ onDone: () => onDone(), stages: STAGES_BY_SCOPE[scope] })
  const { state, begin, attach, fail, reset } = run

  // Reattach to a tailor run for this job that is still going (drawer reopened,
  // page reloaded) instead of showing idle and inviting a duplicate run.
  useEffect(() => {
    reset()
    if (!jobKey) return
    let cancelled = false
    const kind = scope === 'resume' ? 'tailor_resume' : 'tailor_cover'
    listRuns()
      .then((runs) => {
        if (cancelled) return
        const live = runs.find((r) => r.running && r.job_id === jobKey && (r.kind === kind || r.kind === 'tailor'))
        if (live) attach(live, Date.parse(live.started_at) || Date.now())
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [jobKey, scope, attach, reset])

  const start = useCallback(
    (arg?: unknown) => {
      const instructions = typeof arg === 'string' ? arg : undefined
      if (!jobKey || state === 'starting' || state === 'running') return
      begin()
      void (async () => {
        try {
          attach(
            scope === 'resume'
              ? await startJobTailorResume(jobKey, instructions)
              : await startJobTailorCover(jobKey, instructions),
          )
        } catch (e) {
          toast.error(errorMessage(e))
          fail()
        }
      })()
    },
    [jobKey, scope, state, begin, attach, fail],
  )

  return {
    state,
    active: run.active,
    handle: run.handle,
    log: run.log,
    rc: run.rc,
    stages: run.stages,
    currentStage: run.currentStage,
    completedCount: run.completedCount,
    progress: run.progress,
    elapsedMs: run.elapsedMs,
    stopping: run.stopping,
    start,
    stop: run.stop,
  }
}

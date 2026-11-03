import { toast } from 'sonner'
import { useCallback, useEffect, useRef } from 'react'
import { listRuns, startRun, type RunHandle, type RunRecord } from '@/lib/api'
import { useRunTracker, type AutoSearch } from '@/lib/useRunStream'
import { errorMessage } from '@/lib/utils'

/** Every stage a run can report, in order (a run uses a subset). */
export const FULL_PIPELINE = [
  'discover',
  'enrich',
  'score',
  'portfolio',
  'tailor',
  'cover',
  'docx',
  'connect',
] as const

/** Human labels for pipeline run stages (not Kanban lanes; see api.STAGE_LABELS). */
export const RUN_STAGE_LABELS: Record<string, string> = {
  discover: 'Discovering',
  enrich: 'Enriching',
  score: 'Scoring',
  portfolio: 'Portfolio',
  tailor: 'Tailoring',
  cover: 'Cover letters',
  docx: 'Exporting',
  connect: 'Connections',
}

export type { AutoSearch, AutoSearchState } from '@/lib/useRunStream'

/** Format ms as m:ss (or h:mm:ss past an hour). */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

function handleFromRecord(r: RunRecord): RunHandle {
  return {
    run_id: r.run_id,
    pid: r.pid,
    log_path: r.log_path,
    user: r.user,
    stages: r.stages,
    kind: r.kind,
  }
}

function isAutoSearchRun(r: RunRecord): boolean {
  if (r.kind === 'pipeline') return true
  if (r.kind) return false
  return (r.stages || []).includes('discover')
}

/**
 * Owns a single Auto Search pipeline run. Kept at the App level so the header
 * button and the dialog observe the same live run: progress, elapsed time, and
 * logs survive the dialog being closed and reopened. Streaming and progress
 * come from `useRunTracker`. Polls GET /api/runs so a run started from another
 * tab or from the API/CLI still shows as running on this dashboard.
 */
export function useAutoSearch(onDone: () => void): AutoSearch {
  const onDoneRef = useRef(onDone)
  const run = useRunTracker({ onDone: () => onDoneRef.current(), fallbackStages: FULL_PIPELINE })
  const { state, stopping, begin, attach, fail, finish } = run
  const handleRef = useRef(run.handle)
  const stateRef = useRef(state)
  onDoneRef.current = onDone
  handleRef.current = run.handle
  stateRef.current = state

  const adopt = useCallback(
    (r: RunRecord) => attach(handleFromRecord(r), Date.parse(r.started_at) || Date.now()),
    [attach],
  )

  // Pick up runs started from another tab, CLI, or the API (including after refresh).
  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      const st = stateRef.current
      if (st === 'starting' || stopping || document.hidden) return
      try {
        const runs = await listRuns()
        if (cancelled) return
        const live = runs.find((r) => r.running && isAutoSearchRun(r))
        if (!live) {
          // API restart (or process exit) drops SSE before `done`. Stop the
          // header timer instead of sitting on "Starting" forever.
          if (st === 'running') finish()
          return
        }
        const attached = handleRef.current?.run_id === live.run_id && st === 'running'
        if (!attached) adopt(live)
      } catch {
        /* polling is best-effort */
      }
    }
    void tick()
    const id = window.setInterval(() => void tick(), 3000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [adopt, finish, stopping])

  const start = useCallback(() => {
    if (state === 'starting' || state === 'running') return
    begin()
    void (async () => {
      try {
        const existing = (await listRuns()).find((r) => r.running && isAutoSearchRun(r))
        if (existing) {
          adopt(existing)
          return
        }
        attach(await startRun([], { min_score: 7, workers: 2 }))
      } catch (e) {
        toast.error(errorMessage(e))
        fail()
      }
    })()
  }, [state, adopt, attach, begin, fail])

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
    stopping,
    start,
    stop: run.stop,
  }
}

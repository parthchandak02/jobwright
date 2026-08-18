import { useCallback, useEffect, useRef, useState } from 'react'
import { listRuns, startRun, stopRun, type RunHandle, type RunRecord } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/** Full pipeline the "Auto Search" action runs, in order. */
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

/** Human labels for the compact progress readout. */
export const STAGE_LABELS: Record<string, string> = {
  discover: 'Discovering',
  enrich: 'Enriching',
  score: 'Scoring',
  portfolio: 'Portfolio',
  tailor: 'Tailoring',
  cover: 'Cover letters',
  docx: 'Exporting',
  connect: 'Connections',
}

export type AutoSearchState =
  | 'idle'
  | 'starting'
  | 'running'
  | 'finished'
  | 'failed'
  | 'error'

export type AutoSearch = {
  state: AutoSearchState
  active: boolean
  handle: RunHandle | null
  log: string
  rc: number | null
  stages: string[]
  currentStage: string | null
  completedCount: number
  /** 0..1 approximate progress across the stage list. */
  progress: number
  elapsedMs: number
  stopping: boolean
  start: (arg?: unknown) => void
  stop: () => Promise<void>
}

function parseRC(line: string): number | null {
  const m = line.match(/RC=(-?\d+)/)
  return m ? Number(m[1]) : null
}

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
 * logs survive the dialog being closed and reopened. Progress is derived from
 * the verbose pipeline log (`STAGE: <name>` and `Stage '<name>' completed`).
 * Polls GET /api/runs so a run started from another tab or from the API/CLI
 * still shows as running on this dashboard.
 */
export function useAutoSearch(onDone: () => void): AutoSearch {
  const [state, setState] = useState<AutoSearchState>('idle')
  const [handle, setHandle] = useState<RunHandle | null>(null)
  const [log, setLog] = useState('')
  const [rc, setRc] = useState<number | null>(null)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [completedCount, setCompletedCount] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [stopping, setStopping] = useState(false)

  const startedAtRef = useRef<number | null>(null)
  const onDoneRef = useRef(onDone)
  const esRef = useRef<EventSource | null>(null)
  const stoppedRef = useRef(false)
  const handleRef = useRef<RunHandle | null>(null)
  const stateRef = useRef(state)
  onDoneRef.current = onDone
  handleRef.current = handle
  stateRef.current = state

  const runId = handle?.run_id ?? null
  const active = state === 'starting' || state === 'running'

  // Tick the elapsed timer once per second while a run is active.
  useEffect(() => {
    if (!active || startedAtRef.current == null) return
    const id = window.setInterval(() => {
      if (startedAtRef.current != null) {
        setElapsedMs(Date.now() - startedAtRef.current)
      }
    }, 500)
    return () => window.clearInterval(id)
  }, [active])

  // Stream logs and derive stage progress.
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/stream/${runId}`)
    esRef.current = es

    const handleLine = (line: string) => {
      const startM = line.match(/STAGE:\s*([a-z_]+)/)
      if (startM) setCurrentStage(startM[1])
      if (/Stage '([a-z_]+)' completed/.test(line)) {
        setCompletedCount((c) => c + 1)
      }
      if (line.includes('done RC=')) {
        const parsed = parseRC(line)
        setRc(parsed)
        setState(stoppedRef.current || parsed !== 0 ? 'failed' : 'finished')
      }
    }

    es.onmessage = (ev) => {
      setLog((prev) => prev + ev.data + '\n')
      handleLine(ev.data)
    }
    es.addEventListener('done', (ev) => {
      es.close()
      if (esRef.current === es) esRef.current = null
      const parsed = parseRC((ev as MessageEvent).data || '')
      setState((prev) => {
        if (prev === 'finished' || prev === 'failed') return prev
        if (stoppedRef.current) return 'failed'
        const code = parsed ?? 0
        setRc(code)
        return code === 0 ? 'finished' : 'failed'
      })
      onDoneRef.current()
    })
    es.onerror = () => {
      es.close()
      if (esRef.current === es) esRef.current = null
      setState((prev) => {
        if (stoppedRef.current) return 'failed'
        if (prev === 'finished' || prev === 'failed') return prev
        return 'error'
      })
    }
    return () => {
      es.close()
      if (esRef.current === es) esRef.current = null
    }
  }, [runId])

  const adopt = useCallback((r: RunRecord) => {
    stoppedRef.current = false
    const started = Date.parse(r.started_at) || Date.now()
    startedAtRef.current = started
    setElapsedMs(Math.max(0, Date.now() - started))
    setRc(null)
    setLog('')
    setCurrentStage(null)
    setCompletedCount(0)
    setHandle(handleFromRecord(r))
    setState('running')
  }, [])

  // Pick up runs started from another tab, CLI, or the API (including after refresh).
  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      const st = stateRef.current
      if (st === 'starting' || stopping) return
      try {
        const runs = await listRuns()
        if (cancelled) return
        const live = runs.find((r) => r.running && isAutoSearchRun(r))
        if (!live) return
        const current = handleRef.current?.run_id
        const attached = current === live.run_id && st === 'running'
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
  }, [adopt, stopping])

  const start = useCallback(() => {
    if (state === 'starting' || state === 'running') return
    stoppedRef.current = false
    setState('starting')
    setLog('')
    setRc(null)
    setCurrentStage(null)
    setCompletedCount(0)
    setElapsedMs(0)
    startedAtRef.current = Date.now()
    void (async () => {
      try {
        const existing = (await listRuns()).find((r) => r.running)
        if (existing) {
          adopt(existing)
          return
        }
        const res = await startRun([...FULL_PIPELINE], { min_score: 7, workers: 4 })
        setHandle(res)
        setState('running')
      } catch (e) {
        const { toast } = await import('sonner')
        toast.error(errorMessage(e))
        setState('error')
      }
    })()
  }, [state, adopt])

  const stop = useCallback(async () => {
    if (!runId) {
      const { toast } = await import('sonner')
      toast.error('No run to stop yet')
      return
    }
    stoppedRef.current = true
    esRef.current?.close()
    esRef.current = null
    setStopping(true)
    try {
      const res = await stopRun(runId)
      const { toast } = await import('sonner')
      toast.success(res.stopped ? 'Run stopped' : 'Stop requested (process may still be winding down)')
      setRc(res.returncode)
      setState('failed')
    } catch (e) {
      const { toast } = await import('sonner')
      toast.error(errorMessage(e))
      // Keep failed so the UI does not look like the run is still going.
      setState('failed')
    } finally {
      setStopping(false)
    }
  }, [runId])

  const total = FULL_PIPELINE.length
  const done = Math.min(completedCount, total)
  // Give partial credit for the stage currently running so the bar advances
  // between completions instead of sitting still through a long stage.
  const partial = active && currentStage && done < total ? 0.4 : 0
  const progress =
    state === 'finished'
      ? 1
      : Math.max(0, Math.min(1, (done + partial) / total))

  return {
    state,
    active,
    handle,
    log,
    rc,
    stages: [...FULL_PIPELINE],
    currentStage,
    completedCount: done,
    progress,
    elapsedMs,
    stopping,
    start,
    stop,
  }
}

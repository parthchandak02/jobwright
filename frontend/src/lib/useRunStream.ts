import { toast } from 'sonner'
import { useCallback, useEffect, useRef, useState } from 'react'
import { stopRun, type RunHandle } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

export type AutoSearchState = 'idle' | 'starting' | 'running' | 'finished' | 'failed' | 'error'

/** Live view of one pipeline run, in the shape RunProgressDialog / RunProgressButton read. */
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

/** How a run ended, passed to `onDone`. */
export type RunResult = { rc: number | null; failed: boolean }

/** Exit code from a `[done RC=n]` line (or any `RC=n`). */
export function parseRC(line: string): number | null {
  const m = line.match(/RC=(-?\d+)/)
  return m ? Number(m[1]) : null
}

const LOG_FLUSH_MS = 200

type TrackerOptions = {
  /** Called once when the stream reports the run is over. */
  onDone?: (result: RunResult) => void
  /** Stage list to show; overrides the handle's stages. */
  stages?: readonly string[]
  /** Stage list when neither `stages` nor the handle has one. */
  fallbackStages?: readonly string[]
}

/** The run view plus controls for hooks that start or adopt runs themselves. */
export type RunTracker = AutoSearch & {
  /** Show "starting" before the run handle exists. */
  begin: () => void
  /** Follow a run's SSE log; `startedAt` (ms epoch) for runs already going. */
  attach: (handle: RunHandle, startedAt?: number) => void
  /** Starting the run failed. */
  fail: () => void
  /** The run ended without a `done` event (API restart, process exit). */
  finish: () => void
  /** Back to idle and forget the run. */
  reset: () => void
}

const DEFAULT_FALLBACK = ['run'] as const

/**
 * The one SSE run follower. Streams `/api/stream/{run_id}`, derives stage
 * progress from the verbose pipeline log (`STAGE: <name>` and
 * `Stage '<name>' completed`), reads the exit code from `[done RC=n]`, ticks an
 * elapsed timer and stops runs. `useRunStream`, `useAutoSearch`,
 * `useTailorMaterials` and the drawer's prepare action are built on it.
 */
export function useRunTracker({
  onDone,
  stages: fixedStages,
  fallbackStages = DEFAULT_FALLBACK,
}: TrackerOptions = {}): RunTracker {
  const [state, setState] = useState<AutoSearchState>('idle')
  const [handle, setHandle] = useState<RunHandle | null>(null)
  // Bumped on every attach so re-adopting the same run reconnects its stream.
  const [attachSeq, setAttachSeq] = useState(0)
  const [log, setLog] = useState('')
  const [rc, setRc] = useState<number | null>(null)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [completed, setCompleted] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [stopping, setStopping] = useState(false)

  const startedAtRef = useRef<number | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const stoppedRef = useRef(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const runId = handle?.run_id ?? null
  const active = state === 'starting' || state === 'running'

  const clearProgress = useCallback(() => {
    setLog('')
    setRc(null)
    setCurrentStage(null)
    setCompleted(0)
  }, [])

  const begin = useCallback(() => {
    stoppedRef.current = false
    startedAtRef.current = Date.now()
    setElapsedMs(0)
    clearProgress()
    setState('starting')
  }, [clearProgress])

  const attach = useCallback(
    (h: RunHandle, startedAt?: number) => {
      stoppedRef.current = false
      const started = startedAt ?? startedAtRef.current ?? Date.now()
      startedAtRef.current = started
      setElapsedMs(Math.max(0, Date.now() - started))
      clearProgress()
      setHandle(h)
      setAttachSeq((n) => n + 1)
      setState('running')
    },
    [clearProgress],
  )

  const fail = useCallback(() => setState('error'), [])
  const finish = useCallback(() => setState('finished'), [])

  const reset = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    stoppedRef.current = false
    startedAtRef.current = null
    setHandle(null)
    setElapsedMs(0)
    setStopping(false)
    clearProgress()
    setState('idle')
  }, [clearProgress])

  // Elapsed timer while the run is going.
  useEffect(() => {
    if (!active || startedAtRef.current == null) return
    const id = window.setInterval(() => {
      if (startedAtRef.current != null) setElapsedMs(Date.now() - startedAtRef.current)
    }, 500)
    return () => window.clearInterval(id)
  }, [active])

  // Follow the log.
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/stream/${runId}`)
    esRef.current = es
    let finalRc: number | null = null
    let pending = ''
    let flushTimer: number | null = null
    const flushLog = () => {
      flushTimer = null
      if (!pending) return
      const chunk = pending
      pending = ''
      setLog((prev) => prev + chunk)
    }
    const detach = () => {
      if (flushTimer != null) window.clearTimeout(flushTimer)
      flushLog()
      es.close()
      if (esRef.current === es) esRef.current = null
    }

    es.onmessage = (ev) => {
      const line = String(ev.data)
      pending += line + '\n'
      if (flushTimer == null) flushTimer = window.setTimeout(flushLog, LOG_FLUSH_MS)
      const startM = line.match(/STAGE:\s*([a-z_]+)/)
      if (startM) setCurrentStage(startM[1])
      if (/Stage '([a-z_]+)' completed/.test(line)) setCompleted((c) => c + 1)
      if (line.includes('done RC=')) {
        finalRc = parseRC(line)
        setRc(finalRc)
        setState(stoppedRef.current || (finalRc !== null && finalRc !== 0) ? 'failed' : 'finished')
      }
    }
    es.addEventListener('done', (ev) => {
      detach()
      const code = finalRc ?? parseRC((ev as MessageEvent).data || '') ?? 0
      const failed = stoppedRef.current || code !== 0
      setRc(code)
      setState((prev) => (prev === 'finished' || prev === 'failed' ? prev : failed ? 'failed' : 'finished'))
      onDoneRef.current?.({ rc: code, failed })
    })
    es.onerror = () => {
      detach()
      setState((prev) => {
        if (stoppedRef.current) return 'failed'
        if (prev === 'finished' || prev === 'failed') return prev
        return 'error'
      })
    }
    return detach
  }, [runId, attachSeq])

  const stop = useCallback(async () => {
    if (!runId) {
      toast.error('No run to stop yet')
      return
    }
    stoppedRef.current = true
    esRef.current?.close()
    esRef.current = null
    setStopping(true)
    try {
      const res = await stopRun(runId)
      toast.success(res.stopped ? 'Run stopped' : 'Stop requested (process may still be winding down)')
      setRc(res.returncode)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      // Failed either way so the UI does not look like the run is still going.
      setState('failed')
      setStopping(false)
    }
  }, [runId])

  const stages = fixedStages?.length
    ? [...fixedStages]
    : handle?.stages?.length
      ? handle.stages
      : [...fallbackStages]
  const total = stages.length
  const done = Math.min(completed, total)
  // Partial credit for the stage in flight so the bar moves during long stages.
  const partial = active && currentStage && done < total ? 0.4 : 0
  const progress = state === 'finished' ? 1 : Math.max(0, Math.min(1, (done + partial) / total))

  return {
    state,
    active,
    handle,
    log,
    rc,
    stages,
    currentStage,
    completedCount: done,
    progress,
    elapsedMs,
    stopping,
    start: () => undefined,
    stop,
    begin,
    attach,
    fail,
    finish,
    reset,
  }
}

/** Attach to an already-started run (or none) and expose it in the RunProgressDialog shape. */
export function useRunStream(handle: RunHandle | null, onDone?: (result: RunResult) => void): AutoSearch {
  const tracker = useRunTracker({ onDone })
  const { attach, reset } = tracker
  const handleRef = useRef(handle)
  handleRef.current = handle
  const runId = handle?.run_id ?? null

  useEffect(() => {
    if (runId && handleRef.current) attach(handleRef.current, Date.now())
    else reset()
  }, [runId, attach, reset])

  return tracker
}

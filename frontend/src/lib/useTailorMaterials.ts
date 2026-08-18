import { useCallback, useEffect, useRef, useState } from 'react'
import { startJobTailor, stopRun, type RunHandle, type TailorInstructions } from '@/lib/api'
import { type AutoSearch, type AutoSearchState } from '@/lib/useAutoSearch'
import { errorMessage } from '@/lib/utils'

export const TAILOR_STAGES = ['tailor', 'cover', 'docx'] as const

function parseRC(line: string): number | null {
  const m = line.match(/RC=(-?\d+)/)
  return m ? Number(m[1]) : null
}

/**
 * Per-job tailor run with SSE logs. Same progress model as Auto Search.
 */
export function useTailorMaterials(jobUrl: string | undefined, onDone: () => void): AutoSearch {
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
  onDoneRef.current = onDone

  const runId = handle?.run_id ?? null
  const active = state === 'starting' || state === 'running'

  useEffect(() => {
    setState('idle')
    setHandle(null)
    setLog('')
    setRc(null)
    setCurrentStage(null)
    setCompletedCount(0)
    setElapsedMs(0)
    setStopping(false)
    stoppedRef.current = false
    startedAtRef.current = null
  }, [jobUrl])

  useEffect(() => {
    if (!active || startedAtRef.current == null) return
    const id = window.setInterval(() => {
      if (startedAtRef.current != null) {
        setElapsedMs(Date.now() - startedAtRef.current)
      }
    }, 500)
    return () => window.clearInterval(id)
  }, [active])

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

  const start = useCallback((arg?: unknown) => {
    const instructions = arg as Partial<TailorInstructions> | undefined
    if (!jobUrl || state === 'starting' || state === 'running') return
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
        const res = await startJobTailor(jobUrl, instructions)
        setHandle(res)
        setState('running')
      } catch (e) {
        const { toast } = await import('sonner')
        toast.error(errorMessage(e))
        setState('error')
      }
    })()
  }, [jobUrl, state])

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
      toast.success(
        res.stopped ? 'Run stopped' : 'Stop requested (process may still be winding down)',
      )
      setRc(res.returncode)
      setState('failed')
    } catch (e) {
      const { toast } = await import('sonner')
      toast.error(errorMessage(e))
      setState('failed')
    } finally {
      setStopping(false)
    }
  }, [runId])

  const total = TAILOR_STAGES.length
  const done = Math.min(completedCount, total)
  const partial = active && currentStage && done < total ? 0.4 : 0
  const progress =
    state === 'finished' ? 1 : Math.max(0, Math.min(1, (done + partial) / total))

  return {
    state,
    active,
    handle,
    log,
    rc,
    stages: [...TAILOR_STAGES],
    currentStage,
    completedCount: done,
    progress,
    elapsedMs,
    stopping,
    start,
    stop,
  }
}

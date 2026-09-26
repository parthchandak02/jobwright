import { toast } from 'sonner'
import { useEffect, useRef, useState } from 'react'
import { stopRun, type RunHandle } from '@/lib/api'
import type { AutoSearch, AutoSearchState } from '@/lib/useAutoSearch'
import { errorMessage } from '@/lib/utils'

function parseRC(line: string): number | null {
  const m = line.match(/RC=(-?\d+)/)
  return m ? Number(m[1]) : null
}

/** Attach to an already-started run and expose it in the RunProgressDialog shape. */
export function useRunStream(handle: RunHandle | null, onDone?: () => void): AutoSearch {
  const [state, setState] = useState<AutoSearchState>('idle')
  const [log, setLog] = useState('')
  const [rc, setRc] = useState<number | null>(null)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [completed, setCompleted] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [stopping, setStopping] = useState(false)
  const started = useRef(0)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  const runId = handle?.run_id ?? null

  useEffect(() => {
    setLog('')
    setRc(null)
    setCurrentStage(null)
    setCompleted(0)
    if (!runId) {
      setState('idle')
      return
    }
    setState('running')
    started.current = Date.now()
    const tick = window.setInterval(() => setElapsedMs(Date.now() - started.current), 500)
    const es = new EventSource(`/api/stream/${runId}`)
    es.onmessage = (ev) => {
      const line = String(ev.data)
      setLog((prev) => prev + line + '\n')
      const m = line.match(/STAGE:\s*([a-z_]+)/)
      if (m) setCurrentStage(m[1])
      if (/Stage '([a-z_]+)' completed/.test(line)) setCompleted((c) => c + 1)
      if (line.includes('done RC=')) {
        const code = parseRC(line)
        setRc(code)
        setState(code !== null && code !== 0 ? 'failed' : 'finished')
      }
    }
    es.addEventListener('done', () => {
      es.close()
      window.clearInterval(tick)
      onDoneRef.current?.()
    })
    es.onerror = () => {
      es.close()
      window.clearInterval(tick)
      setState((prev) => (prev === 'finished' || prev === 'failed' ? prev : 'error'))
    }
    return () => {
      es.close()
      window.clearInterval(tick)
    }
  }, [runId])

  const stages = handle?.stages?.length ? handle.stages : ['run']
  const active = state === 'running' || state === 'starting'
  return {
    state,
    active,
    handle,
    log,
    rc,
    stages,
    currentStage,
    completedCount: Math.min(completed, stages.length),
    progress: state === 'finished' ? 1 : Math.min(1, (completed + (active ? 0.4 : 0)) / stages.length),
    elapsedMs,
    stopping,
    start: () => undefined,
    stop: async () => {
      if (!runId) return
      setStopping(true)
      try {
        await stopRun(runId)
        setState('failed')
      } catch (e) {
        toast.error(errorMessage(e))
      } finally {
        setStopping(false)
      }
    },
  }
}

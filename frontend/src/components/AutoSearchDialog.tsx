import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Copy, Loader2, Sparkles, Square, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { startRun, stopRun, type RunHandle } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  /** Called once the run finishes (done RC=) so the board can refresh. */
  onDone: () => void
}

/** Full pipeline run for the header "Auto Search" primary action. */
const FULL_PIPELINE = [
  'discover',
  'enrich',
  'score',
  'portfolio',
  'tailor',
  'cover',
  'docx',
  'connect',
]

type RunState = 'starting' | 'running' | 'finished' | 'failed' | 'error'

/** Parse a return code from a `[done RC=n]` log line. */
function parseRC(line: string): number | null {
  const m = line.match(/RC=(-?\d+)/)
  return m ? Number(m[1]) : null
}

async function copyToClipboard(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label} copied`)
  } catch {
    toast.error('Copy failed')
  }
}

export function AutoSearchDialog({ open, onClose, onDone }: Props) {
  const [log, setLog] = useState('')
  const [handle, setHandle] = useState<RunHandle | null>(null)
  const [state, setState] = useState<RunState>('starting')
  const [rc, setRc] = useState<number | null>(null)
  const [stopping, setStopping] = useState(false)

  const logRef = useRef<HTMLPreElement>(null)
  const startedRef = useRef(false)
  const nearBottomRef = useRef(true)

  const runId = handle?.run_id ?? null
  const active = state === 'starting' || state === 'running'

  // Track whether the user is scrolled near the bottom so we only auto-scroll
  // when they haven't deliberately scrolled up to read.
  const onScroll = useCallback(() => {
    const el = logRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }, [])

  // Auto-scroll to bottom after log updates, but only if near the bottom.
  useEffect(() => {
    const el = logRef.current
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight
  }, [log])

  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/stream/${runId}`)
    es.onmessage = (ev) => {
      setLog((prev) => prev + ev.data + '\n')
      if (ev.data.includes('done RC=')) {
        const parsed = parseRC(ev.data)
        setRc(parsed)
        setState(parsed === 0 ? 'finished' : 'failed')
      }
    }
    es.addEventListener('done', (ev) => {
      es.close()
      const parsed = parseRC((ev as MessageEvent).data || '')
      setState((prev) => {
        if (prev === 'finished' || prev === 'failed') return prev
        const code = parsed ?? 0
        setRc(code)
        return code === 0 ? 'finished' : 'failed'
      })
      toast.success('Auto search complete')
      onDone()
    })
    es.onerror = () => {
      es.close()
      setState((prev) => (prev === 'finished' || prev === 'failed' ? prev : 'error'))
    }
    return () => es.close()
  }, [runId, onDone])

  useEffect(() => {
    if (!open) {
      startedRef.current = false
      setHandle(null)
      setLog('')
      setState('starting')
      setRc(null)
      setStopping(false)
      nearBottomRef.current = true
      return
    }
    if (startedRef.current) return
    startedRef.current = true
    setState('starting')
    setLog('')
    startRun(FULL_PIPELINE, { min_score: 7, workers: 4 })
      .then((res) => {
        setHandle(res)
        setState('running')
      })
      .catch((e) => {
        toast.error(errorMessage(e))
        setState('error')
      })
  }, [open])

  async function onStop() {
    if (!runId) return
    setStopping(true)
    try {
      const res = await stopRun(runId)
      toast.success(res.stopped ? 'Run stopped' : 'Stop requested')
      setRc(res.returncode)
      setState('failed')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setStopping(false)
    }
  }

  const statusLabel = (() => {
    switch (state) {
      case 'starting':
        return 'Starting…'
      case 'running':
        return handle ? `Running (PID ${handle.pid})` : 'Running…'
      case 'finished':
        return `Finished RC=${rc ?? 0}`
      case 'failed':
        return `Failed RC=${rc ?? 1}`
      case 'error':
        return 'Connection lost'
    }
  })()

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col gap-4 sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4" /> Auto Search
          </DialogTitle>
          <DialogDescription>
            Running the full pipeline: discover, enrich, score, tailor, cover, docx, and connect.
            Logs stream live.
          </DialogDescription>
        </DialogHeader>

        {/* Process header: run id, pid, log path. */}
        <div className="space-y-2 rounded-lg border bg-muted/40 p-3 text-xs">
          <div className="flex items-center gap-2">
            {active ? (
              <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
            ) : state === 'finished' ? (
              <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
            ) : (
              <XCircle className="size-3.5 shrink-0 text-destructive" />
            )}
            <span
              className={
                state === 'finished'
                  ? 'font-medium text-emerald-600 dark:text-emerald-500'
                  : state === 'failed' || state === 'error'
                    ? 'font-medium text-destructive'
                    : 'font-medium text-foreground'
              }
            >
              {statusLabel}
            </span>
          </div>
          <div className="grid gap-1.5 sm:grid-cols-[auto_1fr]">
            <span className="text-muted-foreground">Run ID</span>
            <span className="font-mono text-foreground">{handle?.run_id ?? '—'}</span>
            <span className="text-muted-foreground">PID</span>
            <span className="font-mono text-foreground">{handle?.pid ?? '—'}</span>
            <span className="text-muted-foreground">Log</span>
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="truncate font-mono text-foreground" title={handle?.log_path}>
                {handle?.log_path ?? '—'}
              </span>
              {handle?.log_path && (
                <button
                  type="button"
                  onClick={() => void copyToClipboard(handle.log_path, 'Log path')}
                  className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
                  title="Copy log path"
                  aria-label="Copy log path"
                >
                  <Copy className="size-3.5" />
                </button>
              )}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">Live logs (verbose)</span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!log}
              onClick={() => void copyToClipboard(log, 'Logs')}
            >
              <Copy /> Copy logs
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={!active || !runId || stopping}
              onClick={() => void onStop()}
            >
              {stopping ? <Loader2 className="animate-spin" /> : <Square />} Stop
            </Button>
          </div>
        </div>

        <pre
          ref={logRef}
          onScroll={onScroll}
          className="min-h-48 flex-1 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs text-foreground"
        >
          {log || 'Starting run…'}
        </pre>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {active ? (
              <>
                <Loader2 className="animate-spin" /> Running…
              </>
            ) : (
              'Close'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

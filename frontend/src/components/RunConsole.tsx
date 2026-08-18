import { useEffect, useRef, useState } from 'react'
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
import { Badge } from '@/components/ui/badge'
import { apiFetch } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  applyEnabled: boolean
  onClose: () => void
  onDone: () => void
}

const STAGE_OPTIONS = [
  'discover',
  'enrich',
  'score',
  'portfolio',
  'tailor',
  'cover',
  'docx',
  'connect',
]

export function RunConsole({ open, applyEnabled, onClose, onDone }: Props) {
  const [selected, setSelected] = useState<string[]>(['score', 'tailor', 'cover', 'docx'])
  const [log, setLog] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const logRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`/api/stream/${runId}`)
    es.onmessage = (ev) => {
      setLog((prev) => prev + ev.data + '\n')
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
    }
    es.addEventListener('done', () => {
      es.close()
      setBusy(false)
      onDone()
    })
    es.onerror = () => {
      es.close()
      setBusy(false)
    }
    return () => es.close()
  }, [runId, onDone])

  function toggle(stage: string) {
    setSelected((prev) =>
      prev.includes(stage) ? prev.filter((s) => s !== stage) : [...prev, stage],
    )
  }

  async function startRun() {
    setBusy(true)
    setLog('')
    try {
      const res = await apiFetch<{ run_id: string }>('/run', {
        method: 'POST',
        body: JSON.stringify({ stages: selected, min_score: 7, workers: 2 }),
      })
      setRunId(res.run_id)
    } catch (e) {
      toast.error(errorMessage(e))
      setBusy(false)
    }
  }

  async function startApply(dryRun: boolean) {
    setBusy(true)
    setLog('')
    try {
      const res = await apiFetch<{ run_id: string }>('/apply', {
        method: 'POST',
        body: JSON.stringify({ dry_run: dryRun, confirm: !dryRun, limit: 1 }),
      })
      setRunId(res.run_id)
    } catch (e) {
      toast.error(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col gap-4 sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Run console</DialogTitle>
          <DialogDescription>
            Trigger pipeline stages or gated apply. Logs stream live.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          {STAGE_OPTIONS.map((s) => (
            <Badge
              key={s}
              variant={selected.includes(s) ? 'default' : 'outline'}
              className={cn('cursor-pointer capitalize', selected.includes(s) && 'hover:bg-primary/90')}
              onClick={() => toggle(s)}
            >
              {s}
            </Badge>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy || selected.length === 0} onClick={() => void startRun()}>
            Run stages
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void startApply(true)}>
            Apply dry-run
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={busy || !applyEnabled}
            onClick={() => {
              if (window.confirm('Start live apply (limit 1)?')) void startApply(false)
            }}
          >
            Apply live
          </Button>
        </div>
        <pre
          ref={logRef}
          className="min-h-48 flex-1 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs text-foreground"
        >
          {log || 'Logs will stream here…'}
        </pre>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

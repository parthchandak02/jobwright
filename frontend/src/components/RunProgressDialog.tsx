import { useCallback, useEffect, useRef } from 'react'
import { CheckCircle2, Copy, Loader2, Sparkles, Square, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { JobCardChips } from '@/components/JobCardLayout'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { SectionLabel } from '@/components/SectionLabel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import { formatElapsed, type AutoSearch } from '@/lib/useAutoSearch'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  title: string
  description: string
  stageLabels: Record<string, string>
  run: AutoSearch
}

async function copyToClipboard(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label} copied`)
  } catch {
    toast.error('Copy failed')
  }
}

export function RunProgressDialog({
  open,
  onClose,
  title,
  description,
  stageLabels,
  run,
}: Props) {
  const {
    state,
    active,
    handle,
    log,
    rc,
    stages,
    currentStage,
    completedCount,
    progress,
    elapsedMs,
    stopping,
    stop,
  } = run

  const logRef = useRef<HTMLPreElement>(null)
  const nearBottomRef = useRef(true)

  const onScroll = useCallback(() => {
    const el = logRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }, [])

  useEffect(() => {
    const el = logRef.current
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight
  }, [log])

  const stageLabel = currentStage ? stageLabels[currentStage] ?? currentStage : null
  const stepText = active
    ? `Stage ${Math.min(completedCount + 1, stages.length)} of ${stages.length}${stageLabel ? ` · ${stageLabel}` : ''}`
    : state === 'finished'
      ? `All ${stages.length} stages complete`
      : `${completedCount} of ${stages.length} stages`

  const statusLabel = (() => {
    switch (state) {
      case 'idle':
        return 'Idle'
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

  const pct = Math.round(progress * 100)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] min-h-0 max-w-3xl flex-col gap-4 overflow-hidden sm:max-w-3xl">
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4" /> {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="job-card-stack shrink-0 rounded-lg border bg-muted/40 p-[var(--job-card-pad)]">
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2 font-medium">
              {active ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
              ) : state === 'finished' ? (
                <CheckCircle2 className="size-4 shrink-0 text-primary" />
              ) : (
                <XCircle className="size-4 shrink-0 text-destructive" />
              )}
              {stepText}
            </span>
            <span className="font-mono tabular-nums text-muted-foreground">
              {formatElapsed(elapsedMs)}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-border">
            <div
              className={cn(
                'h-full rounded-full transition-[width] duration-500 ease-out',
                state === 'failed' || state === 'error' ? 'bg-destructive' : 'bg-primary',
              )}
              style={{ width: `${Math.max(pct, active ? 4 : 0)}%` }}
            />
          </div>
          <JobCardChips>
            {stages.map((s, i) => {
              const doneStage = i < completedCount || state === 'finished'
              const activeStage = active && !doneStage && s === currentStage
              return (
                <Badge
                  key={s}
                  variant={doneStage ? 'success' : activeStage ? 'default' : 'outline'}
                  title={stageLabels[s] ?? s}
                  className={cn('capitalize', !doneStage && !activeStage && 'text-muted-foreground')}
                >
                  {s}
                </Badge>
              )
            })}
          </JobCardChips>

          <Separator />

          <DetailGrid>
            <DetailRow label="Status" value={statusLabel} />
            <DetailRow label="Run ID" value={handle?.run_id} />
            <DetailRow label="PID" value={handle?.pid != null ? String(handle.pid) : null} />
            <div className="grid grid-cols-[6.5rem_1fr] gap-x-3 text-sm">
              <dt className="text-muted-foreground">Log</dt>
              <dd className="flex min-w-0 items-center gap-1">
                <span className="min-w-0 truncate font-mono text-xs" title={handle?.log_path}>
                  {handle?.log_path?.trim() || '-'}
                </span>
                {handle?.log_path ? (
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => void copyToClipboard(handle.log_path, 'Log path')}
                    title="Copy log path"
                    aria-label="Copy log path"
                  >
                    <Copy />
                  </Button>
                ) : null}
              </dd>
            </div>
          </DetailGrid>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="flex shrink-0 items-center justify-between gap-2">
            <SectionLabel>Live logs</SectionLabel>
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
                type="button"
                size="sm"
                variant="destructive"
                disabled={!handle?.run_id || stopping || state === 'finished' || state === 'idle'}
                onClick={() => void stop()}
              >
                {stopping ? <Loader2 className="animate-spin" /> : <Square />} Stop
              </Button>
            </div>
          </div>

          <pre
            ref={logRef}
            onScroll={onScroll}
            className="min-h-0 flex-1 overflow-auto rounded-lg border bg-muted/40 p-[var(--job-card-pad)] font-mono text-xs text-foreground"
          >
            {log || 'Starting run…'}
          </pre>
        </div>
      </DialogContent>
    </Dialog>
  )
}

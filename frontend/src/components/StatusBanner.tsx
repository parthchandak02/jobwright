import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, X } from 'lucide-react'
import { getStatus, type AppStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

const DISMISS_KEY = 'jobwright-status-dismissed'

function summarize(s: AppStatus): { level: 'warn' | 'fail'; text: string; lines: string[] } | null {
  const lines: string[] = []
  let level: 'warn' | 'fail' | null = null
  if (s.last_run && !s.last_run.ok) {
    level = 'fail'
    for (const [stage, err] of Object.entries(s.last_run.errors || {})) lines.push(`${stage}: ${err}`)
  }
  if (s.health && s.health.level !== 'ok') {
    level = level === 'fail' || s.health.level === 'fail' ? 'fail' : 'warn'
    lines.push(...s.health.lines)
  }
  if (s.whatsapp_bridge !== 'connected') {
    level = level || 'warn'
    lines.push('WhatsApp is disconnected; the daily list will not be delivered until it reconnects.')
  }
  if (!level) return null
  const text =
    level === 'fail'
      ? 'The last job search had a problem. Your list may be incomplete.'
      : s.whatsapp_bridge !== 'connected' && lines.length === 1
        ? 'WhatsApp is disconnected right now.'
        : 'Heads up: something needs attention.'
  return { level, text, lines }
}

/** Thin banner when the last run failed, the ops report warned, or WhatsApp is down. */
export function StatusBanner() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState<string | null>(() => sessionStorage.getItem(DISMISS_KEY))

  useEffect(() => {
    void getStatus()
      .then(setStatus)
      .catch(() => undefined)
  }, [])

  const s = status ? summarize(status) : null
  const key = status ? `${status.last_run?.finished_at}|${status.health?.at}|${status.whatsapp_bridge}` : ''
  if (!s || dismissed === key) return null

  return (
    <div
      role="status"
      className={cn(
        'border-b px-4 py-2 text-xs',
        s.level === 'fail' ? 'border-destructive/40 bg-destructive/10' : 'border-amber-500/40 bg-amber-500/10',
      )}
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className={cn('size-3.5 shrink-0', s.level === 'fail' ? 'text-destructive' : 'text-amber-600')} />
        <span className="min-w-0 flex-1">{s.text}</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
          aria-expanded={open}
        >
          Details <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} />
        </button>
        <button
          type="button"
          aria-label="Dismiss"
          onClick={() => {
            sessionStorage.setItem(DISMISS_KEY, key)
            setDismissed(key)
          }}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
      {open ? (
        <ul className="mt-2 space-y-0.5 pl-5 text-muted-foreground">
          {s.lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

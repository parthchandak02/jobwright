import { useEffect, useState, type CSSProperties } from 'react'
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
  const first = lines[0] || 'Something needs attention.'
  const text =
    level === 'fail' && s.last_run && !s.last_run.ok
      ? 'The last job search had a problem, so your list may be incomplete.'
      : lines.length > 1
        ? `${first} (+${lines.length - 1} more)`
        : first
  return { level, text, lines }
}

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
      style={{ '--tone': s.level === 'fail' ? 'var(--destructive)' : 'var(--warning)' } as CSSProperties}
      className="tone-tint border-x-0 border-t-0 border-b px-4 py-2 text-caption"
    >
      <div className="flex items-center gap-3">
        <AlertTriangle className="size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 text-foreground">{s.text}</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="touch-target relative flex items-center gap-1 font-medium hover:underline"
          aria-expanded={open}
        >
          Details <ChevronDown className={cn('size-3.5 transition-transform duration-(--dur-2)', open && 'rotate-180')} />
        </button>
        <button
          type="button"
          aria-label="Dismiss"
          onClick={() => {
            sessionStorage.setItem(DISMISS_KEY, key)
            setDismissed(key)
          }}
          className="touch-target relative rounded-md p-0.5 hover:bg-current/10"
        >
          <X className="size-4" />
        </button>
      </div>
      {open ? (
        <ul className="mt-2 space-y-0.5 pl-7 text-foreground">
          {s.lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

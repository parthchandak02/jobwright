import { AlertCircle, Check, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export type SaveState = 'idle' | 'saving' | 'saved' | 'error'

type Props = {
  state: SaveState
  /** When the last save finished (Date or epoch ms). Drives "Saved · just now". */
  savedAt?: Date | number | null
  onRetry?: () => void
  /** Override the error text (default "Couldn't save"). */
  errorText?: string
  className?: string
}

function ago(at: number, now: number): string {
  const s = Math.max(0, Math.round((now - at) / 1000))
  if (s < 45) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  return new Date(at).toLocaleDateString()
}

/** Single autosave indicator for a section header: "Saving…", "Saved · just now", "Couldn't save · Retry". */
export function SaveStatus({ state, savedAt, onRetry, errorText = "Couldn't save", className }: Props) {
  const [now, setNow] = useState(() => Date.now())
  const at = savedAt == null ? null : typeof savedAt === 'number' ? savedAt : savedAt.getTime()

  useEffect(() => {
    if (state !== 'saved' || at == null) return
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [state, at])

  return (
    <span
      role="status"
      aria-live="polite"
      data-state={state}
      className={cn(
        'inline-flex min-h-6 items-center gap-1.5 text-caption tabular-nums',
        state === 'error' ? 'text-destructive' : 'text-muted-foreground',
        className,
      )}
    >
      {state === 'saving' ? (
        <>
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          Saving…
        </>
      ) : state === 'saved' ? (
        <>
          <Check className="size-3.5 text-success" aria-hidden />
          {at != null ? `Saved · ${ago(at, now)}` : 'Saved'}
        </>
      ) : state === 'error' ? (
        <>
          <AlertCircle className="size-3.5" aria-hidden />
          {errorText}
          {onRetry ? (
            <>
              <span aria-hidden>·</span>
              <button
                type="button"
                onClick={onRetry}
                className="touch-target relative font-medium underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </>
          ) : null}
        </>
      ) : null}
    </span>
  )
}

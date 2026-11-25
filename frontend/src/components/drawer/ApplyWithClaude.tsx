import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Copy, ExternalLink, MessagesSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { DrawerSection } from '@/components/DrawerSection'
import { Button } from '@/components/ui/button'
import { getConnector, type ConnectorStatus, type JobCard } from '@/lib/api'
import { buildApplyPrompt, CLAUDE_NEW_CHAT_URL } from '@/lib/claudeGuide'
import { writeClipboardText } from '@/lib/clipboard'
import { cn } from '@/lib/utils'

type Props = { job: Pick<JobCard, 'job_id' | 'title' | 'company'> }

/** Collapsed-by-default helper to start a Claude apply session for the open job. */
export function ApplyWithClaude({ job }: Props) {
  const [open, setOpen] = useState(false)
  const [connector, setConnector] = useState<ConnectorStatus | null>(null)
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<number | undefined>(undefined)

  const prompt = useMemo(() => buildApplyPrompt(job), [job])
  const connected = (connector?.clients.length ?? 0) > 0

  useEffect(() => {
    setOpen(false)
    setCopied(false)
    window.clearTimeout(timerRef.current)
    let live = true
    void getConnector()
      .then((c) => live && setConnector(c))
      .catch(() => live && setConnector(null))
    return () => { live = false }
  }, [job.job_id])

  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  async function copyPrompt() {
    const ok = await writeClipboardText(prompt)
    if (!ok) {
      toast.error('Copy failed')
      return
    }
    window.clearTimeout(timerRef.current)
    setCopied(true)
    toast.success('Copied')
    timerRef.current = window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <DrawerSection>
      <Button
        type="button" size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}
        className="-ml-3 text-muted-foreground" aria-expanded={open}
      >
        <MessagesSquare /> Apply with Claude
        <ChevronDown className={cn('transition-transform duration-(--dur-2)', open && 'rotate-180')} />
      </Button>
      {open ? (
        connected ? (
          <div className="mt-3 space-y-3">
            <div className="flex flex-col gap-3 rounded-lg border bg-surface-muted p-3 sm:flex-row sm:items-start">
              <p className="min-w-0 flex-1 text-body text-foreground">{prompt}</p>
              <Button
                type="button" size="sm" variant="secondary" aria-label={copied ? 'Prompt copied' : 'Copy prompt'}
                className="shrink-0 self-start" onClick={() => void copyPrompt()}
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                <span aria-live="polite">{copied ? 'Copied' : 'Copy prompt'}</span>
              </Button>
            </div>
            <div className="flex items-center justify-end">
              <Button asChild size="sm" variant="secondary">
                <a href={CLAUDE_NEW_CHAT_URL} target="_blank" rel="noreferrer">
                  Open Claude <ExternalLink className="size-3.5" aria-hidden />
                </a>
              </Button>
            </div>
          </div>
        ) : (
          <div className="surface mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
            <p className="text-body text-muted-foreground">Connect your Claude to let it fill this application in your browser.</p>
            <Button asChild size="sm" variant="secondary"><Link to="/profile?tab=claude">Connect Claude</Link></Button>
          </div>
        )
      ) : null}
    </DrawerSection>
  )
}

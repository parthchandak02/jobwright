import { useEffect, useState } from 'react'
import { ReasonChips } from '@/components/ReasonChips'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { OUTCOME_LABELS, OUTCOMES } from '@/lib/api'
import { useNotAFitReasons } from '@/lib/reasons'
import { cn } from '@/lib/utils'

export type DismissResult = { outcome: string; reasons: string[]; note: string }

type Props = {
  open: boolean
  jobTitle?: string | null
  /** Stage the job is leaving; "not for me" is the default before applying. */
  fromStage?: string
  onConfirm: (result: DismissResult) => void
  onCancel: () => void
}

export function DismissDialog({ open, jobTitle, fromStage, onConfirm, onCancel }: Props) {
  const beforeApplying = !fromStage || fromStage === 'backlog' || fromStage === 'prepare'
  const reasonsList = useNotAFitReasons()
  const [outcome, setOutcome] = useState<string>(beforeApplying ? 'not_interested' : 'rejected')
  const [reasons, setReasons] = useState<string[]>([])
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!open) return
    setOutcome(beforeApplying ? 'not_interested' : 'rejected')
    setReasons([])
    setNote('')
  }, [open, beforeApplying])

  const needsReason = outcome === 'not_interested'
  const canSubmit = !needsReason || reasons.length > 0 || note.trim().length > 0
  const options = beforeApplying ? OUTCOMES : OUTCOMES.filter((o) => o !== 'not_interested')

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{beforeApplying ? 'Close this job' : 'How did it end?'}</DialogTitle>
          <DialogDescription>{jobTitle ? `“${jobTitle}” moves to Closed.` : 'The job moves to Closed.'}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="What happened">
          {options.map((o) => {
            const active = outcome === o
            return (
              <button
                key={o}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setOutcome(o)}
                className={cn(
                  'flex min-h-11 items-center gap-2 rounded-md border px-3 text-left text-label transition-colors duration-(--dur-1) ease-out md:min-h-10',
                  active
                    ? 'border-primary bg-accent text-accent-foreground'
                    : 'border-border bg-surface text-foreground hover:bg-surface-muted',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'flex size-4 shrink-0 items-center justify-center rounded-full border',
                    active ? 'border-primary' : 'border-border-strong',
                  )}
                >
                  {active ? <span className="size-2 rounded-full bg-primary" /> : null}
                </span>
                {OUTCOME_LABELS[o] || o}
              </button>
            )
          })}
        </div>
        {needsReason ? (
          <div className="space-y-3">
            <div>
              <p className="text-label text-foreground">Why isn’t it a fit?</p>
              <p className="text-caption text-muted-foreground">Pick any that apply. This teaches the scorer to skip jobs like this.</p>
            </div>
            <ReasonChips options={reasonsList} selected={reasons} onChange={setReasons} />
            <Textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add another reason (optional)"
              aria-label="Other reason"
            />
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" disabled={!canSubmit} onClick={() => onConfirm({ outcome, reasons, note: note.trim() })}>
            Close job
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

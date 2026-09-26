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

/** Close a job with an outcome; "not for me" asks why so the scorer learns. */
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Close this job</DialogTitle>
          <DialogDescription>{jobTitle ? `“${jobTitle}”` : 'Choose what happened.'}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Outcome">
          {options.map((o) => (
            <button
              key={o}
              type="button"
              role="radio"
              aria-checked={outcome === o}
              onClick={() => setOutcome(o)}
              className={cn(
                'rounded-md border px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                outcome === o ? 'border-primary bg-primary/10 font-medium' : 'border-border/60 hover:bg-accent/60',
              )}
            >
              {OUTCOME_LABELS[o] || o}
            </button>
          ))}
        </div>
        {needsReason ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">Why? This teaches the scorer to skip jobs like this.</p>
            <ReasonChips options={reasonsList} selected={reasons} onChange={setReasons} />
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Other reason (optional)" />
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
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

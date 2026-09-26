import { useEffect, useState } from 'react'
import { Loader2, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'
import { ReasonChips } from '@/components/ReasonChips'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { clearRating, rateJob, type JobCard } from '@/lib/api'
import { GOOD_FIT_REASONS, useNotAFitReasons } from '@/lib/reasons'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  job: JobCard
  onRated: (job: JobCard) => void
  className?: string
}

type Mode = null | 'up' | 'down'

const UP_SCORE = 8
const DOWN_SCORE = 2

/**
 * One-tap relevance feedback. Every rating is kept and teaches the scorer:
 * it becomes an example for similar jobs on the very next scoring run.
 */
export function RateJob({ job, onRated, className }: Props) {
  const notAFit = useNotAFitReasons()
  const [mode, setMode] = useState<Mode>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [precise, setPrecise] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setMode(null)
    setReasons([])
    setNote('')
    setPrecise(null)
  }, [job.url])

  const rated = job.user_fit_score != null
  const ratedUp = rated && (job.user_fit_score ?? 0) >= 6

  async function submit(score: number) {
    if (!reasons.length && !note.trim()) {
      toast.error('Pick at least one reason so the scorer knows why.')
      return
    }
    setBusy(true)
    try {
      const updated = await rateJob(job, precise ?? score, reasons, note.trim())
      toast.success(score >= 6 ? 'Thanks. More jobs like this.' : 'Got it. Fewer jobs like this.')
      setMode(null)
      onRated(updated)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function undo() {
    setBusy(true)
    try {
      onRated(await clearRating(job))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Is this a good match?</span>
        <div className="flex gap-1.5">
          <Button
            type="button"
            size="sm"
            variant={mode === 'up' || (rated && ratedUp && !mode) ? 'default' : 'outline'}
            onClick={() => setMode(mode === 'up' ? null : 'up')}
            aria-pressed={mode === 'up'}
          >
            <ThumbsUp /> Yes
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'down' || (rated && !ratedUp && !mode) ? 'destructive' : 'outline'}
            onClick={() => setMode(mode === 'down' ? null : 'down')}
            aria-pressed={mode === 'down'}
          >
            <ThumbsDown /> Not for me
          </Button>
        </div>
        {rated && !mode ? (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            You rated {job.user_fit_score}/10
            {job.user_score_rationale ? ` · ${job.user_score_rationale}` : ''}
            <Button type="button" size="icon-sm" variant="ghost" onClick={() => void undo()} disabled={busy} aria-label="Remove my rating">
              <RotateCcw className="size-3.5" />
            </Button>
          </span>
        ) : null}
      </div>

      {mode ? (
        <div className="space-y-3 rounded-lg border border-border/60 p-3">
          <p className="text-xs text-muted-foreground">
            {mode === 'up' ? 'What makes it a good fit?' : 'Why isn’t it a fit?'} Pick any that apply.
          </p>
          <ReasonChips
            options={mode === 'up' ? GOOD_FIT_REASONS : notAFit}
            selected={reasons}
            onChange={setReasons}
            tone={mode === 'up' ? 'positive' : 'negative'}
          />
          <Textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Anything else? (optional)"
            className="text-sm"
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Exact score (optional)</span>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={precise === n}
                onClick={() => setPrecise(precise === n ? null : n)}
                className={cn(
                  'size-7 rounded-md border text-xs tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                  precise === n ? 'border-primary bg-primary/10 text-primary' : 'border-border/60 text-muted-foreground hover:bg-accent/60',
                )}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Button type="button" size="sm" disabled={busy} onClick={() => void submit(mode === 'up' ? UP_SCORE : DOWN_SCORE)}>
              {busy ? <Loader2 className="animate-spin" /> : null} Save rating
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setMode(null)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

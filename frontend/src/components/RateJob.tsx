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
const PRESSED = 'border-primary/40 bg-accent text-accent-foreground hover:bg-accent'

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
  const upOn = mode === 'up' || (rated && ratedUp && !mode)
  const downOn = mode === 'down' || (rated && !ratedUp && !mode)

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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-label text-foreground">Is this a good match?</span>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className={cn(upOn && PRESSED)}
            onClick={() => setMode(mode === 'up' ? null : 'up')}
            aria-pressed={upOn}
          >
            <ThumbsUp /> Yes
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className={cn(downOn && PRESSED)}
            onClick={() => setMode(mode === 'down' ? null : 'down')}
            aria-pressed={downOn}
          >
            <ThumbsDown /> No
          </Button>
        </div>
        {rated && !mode ? (
          <span className="flex min-w-0 items-center gap-1 text-caption text-muted-foreground">
            <span className="min-w-0">
              You rated it {job.user_fit_score}/10
              {job.user_score_rationale ? ` · ${job.user_score_rationale}` : ''}
            </span>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => void undo()}
              disabled={busy}
              aria-label="Remove my rating"
              title="Remove my rating"
            >
              <RotateCcw className="size-3.5" />
            </Button>
          </span>
        ) : null}
      </div>

      {mode ? (
        <div className="space-y-4 rounded-lg bg-surface-muted p-4">
          <div>
            <p className="text-label text-foreground">{mode === 'up' ? 'What makes it a good fit?' : 'Why isn’t it a fit?'}</p>
            <p className="text-caption text-muted-foreground">Pick any that apply. Similar jobs are scored with this next time.</p>
          </div>
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
            placeholder="Add anything else (optional)"
            aria-label="Anything else"
          />
          <div className="space-y-2">
            <p className="text-caption text-muted-foreground">Exact score (optional)</p>
            <div className="grid grid-cols-10 gap-1 md:flex md:gap-1.5" role="radiogroup" aria-label="Exact score">
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                <button
                  key={n}
                  type="button"
                  role="radio"
                  aria-checked={precise === n}
                  onClick={() => setPrecise(precise === n ? null : n)}
                  className={cn(
                    'h-10 rounded-md border text-caption tabular-nums transition-colors duration-(--dur-1) md:h-8 md:w-8',
                    precise === n
                      ? 'border-primary bg-accent font-medium text-accent-foreground'
                      : 'border-border bg-surface text-muted-foreground hover:text-foreground',
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
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

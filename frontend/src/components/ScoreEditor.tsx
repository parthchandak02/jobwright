import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { ScoreBadge } from '@/components/ScoreBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { apiFetch, jobPath } from '@/lib/api'
import { SCORE_LABEL, scoreLevel } from '@/lib/scoreColor'
import { cn, errorMessage } from '@/lib/utils'

type ScoreFields = {
  url: string
  job_id?: string | null
  fit_score: number | null
  ai_fit_score?: number | null
  user_fit_score?: number | null
  user_score_rationale?: string | null
  score_user_modified?: boolean
  keywords?: string
  reasoning?: string
}

type Props = {
  job: ScoreFields
  className?: string
  badgeClassName?: string
  label?: 'none' | 'short' | 'long'
  onSaved?: () => void
}

const SCORES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const

function aiReason(job: ScoreFields): string {
  return (job.reasoning || '').replace(/\s*\[[^\]]*\]\s*$/, '').trim()
}

export function ScoreEditor({ job, className, badgeClassName, label = 'short', onSaved }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [draftScore, setDraftScore] = useState<number | null>(job.fit_score ?? null)
  const [draftRationale, setDraftRationale] = useState(job.user_score_rationale || '')

  useEffect(() => {
    if (!open) return
    setDraftScore(job.fit_score ?? null)
    setDraftRationale(job.user_score_rationale || '')
  }, [open, job.fit_score, job.user_score_rationale])

  async function save() {
    if (draftScore == null) {
      toast.error('Pick a score from 1 to 10')
      return
    }
    const rationale = draftRationale.trim()
    if (!rationale) {
      toast.error('Add a short rationale so the scorer can learn from this')
      return
    }
    setBusy(true)
    try {
      await apiFetch(jobPath(job), {
        method: 'PATCH',
        body: JSON.stringify({
          user_fit_score: draftScore,
          user_score_rationale: rationale,
        }),
      })
      toast.success('Score updated')
      setOpen(false)
      onSaved?.()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function clearOverride() {
    setBusy(true)
    try {
      await apiFetch(jobPath(job), {
        method: 'PATCH',
        body: JSON.stringify({ clear_user_score: true }),
      })
      toast.success('Back to the AI score')
      setOpen(false)
      onSaved?.()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const aiScore = job.ai_fit_score ?? null
  const modified = Boolean(job.score_user_modified)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          className={cn('touch-target relative rounded-full transition-opacity duration-(--dur-1) hover:opacity-80', className)}
          aria-label={`Edit fit score${job.fit_score != null ? `: ${job.fit_score}` : ''}`}
        >
          <ScoreBadge score={job.fit_score} userModified={modified} label={label} className={badgeClassName} />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="left"
        className="w-80 space-y-4"
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-subheading">Your fit score</p>
            {modified ? <Badge variant="secondary">You edited</Badge> : null}
          </div>
          <p className="text-caption text-muted-foreground">
            Correct the score to teach the scorer. Your reason is reused on the next scoring run.
          </p>
        </div>

        {aiScore != null ? (
          <div className="flex items-center gap-2 rounded-md bg-surface-muted px-3 py-2 text-caption">
            <Sparkles className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="text-muted-foreground">AI scored</span>
            <ScoreBadge score={aiScore} label="long" />
          </div>
        ) : null}

        <div className="space-y-2">
          <Label className="text-label">Score</Label>
          <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Score">
            {SCORES.map((n) => {
              const active = draftScore === n
              return (
                <button
                  key={n}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={busy}
                  onClick={() => setDraftScore(n)}
                  className={cn(
                    'h-10 rounded-md border text-label tabular-nums transition-colors duration-(--dur-1) md:h-9',
                    active
                      ? 'border-primary bg-accent text-accent-foreground'
                      : 'border-border bg-surface text-foreground hover:bg-surface-muted',
                  )}
                >
                  {n}
                </button>
              )
            })}
          </div>
          {draftScore != null ? (
            <p className="text-caption text-muted-foreground">{SCORE_LABEL[scoreLevel(draftScore)]}</p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor={`score-rationale-${job.url}`} className="text-label">
            Why this score?
          </Label>
          <Textarea
            id={`score-rationale-${job.url}`}
            value={draftRationale}
            onChange={(e) => setDraftRationale(e.target.value)}
            placeholder="Say what the scorer got right or wrong"
            rows={3}
            disabled={busy}
          />
          {!modified && !draftRationale.trim() && aiReason(job) ? (
            <p className="text-caption text-muted-foreground">AI reason: {aiReason(job)}</p>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" className="flex-1" onClick={() => void save()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : 'Save score'}
          </Button>
          {modified ? (
            <Button size="sm" variant="ghost" onClick={() => void clearOverride()} disabled={busy}>
              Use AI score
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  )
}

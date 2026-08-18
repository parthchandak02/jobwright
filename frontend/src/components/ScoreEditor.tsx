import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { ScoreBadge } from '@/components/ScoreBadge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { apiFetch } from '@/lib/api'
import { getScoreColors } from '@/lib/scoreColor'
import { cn, errorMessage } from '@/lib/utils'

type ScoreFields = {
  url: string
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
  onSaved?: () => void
}

const SCORES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const

function scoreRationale(job: ScoreFields): string {
  if (job.user_score_rationale?.trim()) return job.user_score_rationale.trim()
  const parts = [job.keywords, job.reasoning].map((s) => s?.trim()).filter(Boolean)
  return parts.join(' — ') || 'No score rationale yet.'
}

export function ScoreEditor({ job, className, badgeClassName, onSaved }: Props) {
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
      await apiFetch(`/jobs/${encodeURIComponent(job.url)}`, {
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
      await apiFetch(`/jobs/${encodeURIComponent(job.url)}`, {
        method: 'PATCH',
        body: JSON.stringify({ clear_user_score: true }),
      })
      toast.success('Reverted to AI score')
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
          className={cn(
            'group rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring/60',
            className,
          )}
          aria-label={`Edit fit score${job.fit_score != null ? `: ${job.fit_score}` : ''}`}
        >
          <ScoreBadge
            score={job.fit_score}
            userModified={modified}
            className={cn(
              'h-7 min-w-7 rounded-lg text-sm transition-transform group-hover:scale-105',
              badgeClassName,
            )}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="left"
        className="w-80 space-y-3"
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold">Your fit score</p>
            {modified ? (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                You edited
              </span>
            ) : null}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Teach the scorer by correcting the fit. Your rationale is reused on the next scoring run.
          </p>
        </div>

        {aiScore != null ? (
          <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-background/40 px-2.5 py-2 text-xs">
            <Sparkles className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">AI scored</span>
            <ScoreBadge score={aiScore} className="h-6 min-w-6 text-xs" />
          </div>
        ) : null}

        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">Score</Label>
          <div className="grid grid-cols-5 gap-1.5">
            {SCORES.map((n) => {
              const active = draftScore === n
              const colors = getScoreColors(n)
              return (
                <button
                  key={n}
                  type="button"
                  disabled={busy}
                  onClick={() => setDraftScore(n)}
                  className={cn(
                    'h-9 rounded-lg text-sm font-semibold tabular-nums transition-all',
                    'bg-card/80 hover:scale-[1.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                    active ? 'ring-2 ring-primary/50' : 'ring-1 ring-border/40',
                  )}
                  style={{
                    color: colors.accent,
                    boxShadow: active
                      ? `inset 0 0 0 1px ${colors.ring}, 0 0 0 1px ${colors.soft}`
                      : `inset 0 0 0 1px ${colors.ring}`,
                  }}
                >
                  {n}
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`score-rationale-${job.url}`} className="text-xs text-muted-foreground">
            Why this score?
          </Label>
          <Textarea
            id={`score-rationale-${job.url}`}
            value={draftRationale}
            onChange={(e) => setDraftRationale(e.target.value)}
            placeholder="e.g. Strong ops match but title is too junior for my target level"
            rows={3}
            disabled={busy}
            className="resize-none border-border/50 bg-background/40 text-sm"
          />
        </div>

        {!modified && !draftRationale.trim() ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">{scoreRationale(job)}</p>
        ) : null}

        <div className="flex items-center gap-2 pt-1">
          <Button size="sm" className="flex-1" onClick={() => void save()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : 'Save'}
          </Button>
          {modified ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void clearOverride()}
              disabled={busy}
            >
              Revert
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  )
}

import { useEffect, useState } from 'react'
import { ChevronDown, History, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { DrawerSection } from '@/components/DrawerSection'
import { Button } from '@/components/ui/button'
import {
  getJobHistory,
  getJobLabels,
  STAGE_LABELS,
  type JobCard,
  type JobLabels,
  type StageHistoryEntry,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'
import { fmtWhen } from './format'

type HistoryData = { stages: StageHistoryEntry[]; labels: JobLabels }

function historyItems(history: HistoryData) {
  return [
    ...history.stages.map((h) => ({
      at: h.at,
      text: `${h.actor === 'human' ? 'You' : 'jobwright'} moved it ${
        h.from_stage ? `from ${STAGE_LABELS[h.from_stage] || h.from_stage} ` : ''
      }to ${STAGE_LABELS[h.to_stage] || h.to_stage}${h.note ? ` (${h.note})` : ''}`,
    })),
    ...history.labels.labels.map((l) => ({
      at: l.created_at,
      text:
        l.verdict === 'cleared'
          ? 'You removed your rating'
          : `You rated it ${l.label_score}/10${
              l.reasons?.length ? `: ${l.reasons.join(', ')}` : l.rationale ? `: ${l.rationale}` : ''
            }`,
    })),
    ...history.labels.machine_scores.map((m) => ({
      at: m.created_at,
      text: `Scored ${m.score}/10${m.run_kind === 'rescore' ? ' (rescore)' : ''}`,
    })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1))
}

/** Collapsed "History" toggle; stage moves, ratings and scores load on first open. */
export function JobHistory({ job }: { job: JobCard }) {
  const [open, setOpen] = useState(false)
  const [history, setHistory] = useState<HistoryData | null>(null)

  useEffect(() => {
    setOpen(false)
    setHistory(null)
  }, [job.job_id])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && !history) {
      try {
        const [h, l] = await Promise.all([getJobHistory(job), getJobLabels(job)])
        setHistory({ stages: h.history, labels: l })
      } catch (e) {
        toast.error(errorMessage(e))
      }
    }
  }

  const items = history ? historyItems(history) : []
  return (
    <DrawerSection>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => void toggle()}
        className="-ml-3 text-muted-foreground"
        aria-expanded={open}
      >
        <History /> History
        <ChevronDown className={cn('transition-transform duration-(--dur-2)', open && 'rotate-180')} />
      </Button>
      {open ? (
        history ? (
          <ul className="mt-3 space-y-2 text-caption">
            {items.map((e, i) => (
              <li key={i} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
                <span className="shrink-0 text-muted-foreground tabular-nums sm:w-44">{fmtWhen(e.at)}</span>
                <span className="text-foreground">{e.text}</span>
              </li>
            ))}
            {!items.length ? <li className="text-muted-foreground">No history yet.</li> : null}
          </ul>
        ) : (
          <p className="mt-3 flex items-center gap-2 text-caption text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Loading…
          </p>
        )
      ) : null}
    </DrawerSection>
  )
}

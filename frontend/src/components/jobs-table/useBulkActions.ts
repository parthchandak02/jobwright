import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { bulkJobs, type BulkRequest, type BulkResponse, type JobCard, STAGE_LABELS } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

export type BulkClose = { outcome: string; reasons: string[]; note: string }

function plural(n: number) {
  return `${n} ${n === 1 ? 'job' : 'jobs'}`
}

/** One undo request per lane (and outcome, for jobs that were already closed). */
export function undoRequests(res: BulkResponse, before: Map<string, JobCard>, wasClose: boolean): BulkRequest[] {
  const groups = new Map<string, BulkRequest>()
  for (const r of res.results) {
    if (!r.ok || !r.from_stage) continue
    const prev = before.get(r.job_id)
    const outcome = r.from_stage === 'closed' ? prev?.outcome || 'not_interested' : undefined
    const key = `${r.from_stage}|${outcome ?? ''}`
    let req = groups.get(key)
    if (!req) {
      req =
        r.from_stage === 'closed'
          ? { job_ids: [], action: 'close', outcome }
          : { job_ids: [], action: 'move', stage: r.from_stage, clear_dismiss_labels: wasClose }
      groups.set(key, req)
    }
    req.job_ids.push(r.job_id)
  }
  return [...groups.values()]
}

/**
 * Bulk move / close for the table selection. The server's cards are patched into
 * the board (`onCardsChanged`), and every action gets an Undo toast that puts each
 * job back in its old lane (clearing the "Not for me" label a bulk close recorded).
 */
export function useBulkActions(onCardsChanged: ((cards: JobCard[]) => void) | undefined, onDone: () => void) {
  const [busy, setBusy] = useState(false)

  const undo = useCallback(
    async (res: BulkResponse, before: Map<string, JobCard>, wasClose: boolean) => {
      try {
        const out = await Promise.all(undoRequests(res, before, wasClose).map(bulkJobs))
        onCardsChanged?.(out.flatMap((r) => r.jobs))
        toast.success(`Put ${plural(out.reduce((n, r) => n + r.updated, 0))} back`)
      } catch (e) {
        toast.error(errorMessage(e))
      }
    },
    [onCardsChanged],
  )

  const run = useCallback(
    async (jobs: JobCard[], req: Omit<BulkRequest, 'job_ids'>, done: (n: number) => string) => {
      if (jobs.length === 0 || busy) return
      setBusy(true)
      try {
        const before = new Map(jobs.map((j) => [j.job_id, j]))
        const res = await bulkJobs({ ...req, job_ids: jobs.map((j) => j.job_id) })
        onCardsChanged?.(res.jobs)
        onDone()
        const missed = jobs.length - res.updated
        const text = done(res.updated) + (missed > 0 ? `. ${plural(missed)} couldn’t be changed.` : '')
        toast.success(text, {
          action: res.updated > 0 ? { label: 'Undo', onClick: () => void undo(res, before, req.action === 'close') } : undefined,
        })
      } catch (e) {
        toast.error(errorMessage(e))
      } finally {
        setBusy(false)
      }
    },
    [busy, onCardsChanged, onDone, undo],
  )

  const move = useCallback(
    (jobs: JobCard[], stage: string) => {
      // Jobs already in that lane have nothing to move (and nothing to undo).
      const moving = jobs.filter((j) => j.funnel_stage !== stage)
      const label = STAGE_LABELS[stage] || stage
      return run(moving, { action: 'move', stage }, (n) => `Moved ${plural(n)} to ${label}`)
    },
    [run],
  )

  const close = useCallback(
    (jobs: JobCard[], result: BulkClose) =>
      run(
        jobs,
        { action: 'close', outcome: result.outcome, reasons: result.reasons, note: result.note || undefined },
        (n) => `Moved ${plural(n)} to Closed`,
      ),
    [run],
  )

  return { busy, move, close }
}

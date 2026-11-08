import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot } from 'lucide-react'
import { toast } from 'sonner'
import { Callout } from '@/components/drawer/Callout'
import { Button } from '@/components/ui/button'
import { apiFetch, vetoPick, type ApplyPick } from '@/lib/api'
import { errorMessage } from '@/lib/utils'
import { pickSummary } from '@/lib/applyStatus'

/** Job drawer: "jobwright will apply to this at 9:30" with Don't apply, or a link to the evidence. */
export function ApplyPlanCallout({ jobId }: { jobId: string }) {
  const [pick, setPick] = useState<ApplyPick | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    apiFetch<{ picks: ApplyPick[] }>(`/apply/picks?job=${encodeURIComponent(jobId)}`)
      .then((r) => setPick(r.picks[0] ?? null))
      .catch(() => setPick(null))
  }, [jobId])

  useEffect(load, [load])

  if (!pick) return null
  const summary = pickSummary(pick)
  if (!summary) return null
  return (
    <Callout
      icon={Bot}
      tone="--primary"
      actions={
        pick.status === 'planned' ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                await vetoPick(pick.id)
                toast.success('Skipped. jobwright will not apply to this job.')
                load()
              } catch (e) {
                toast.error(errorMessage(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            Don’t apply
          </Button>
        ) : pick.submission_id ? (
          <Button size="sm" variant="ghost" asChild>
            <Link to={`/apply/submissions/${pick.submission_id}`}>See what was sent</Link>
          </Button>
        ) : undefined
      }
    >
      {summary}
    </Callout>
  )
}

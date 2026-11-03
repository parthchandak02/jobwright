import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { listRuns, startJobTailor } from '@/lib/api'
import { useRunTracker } from '@/lib/useRunStream'
import { errorMessage } from '@/lib/utils'

/**
 * "Prepare resume + letter" for one job: starts the combined tailor run, or
 * picks up one that is already going, and follows it on the run stream (no
 * polling). `onDone` fires once when it ends.
 */
export function usePrepareMaterials(jobKey: string | null, onDone: () => void) {
  const [starting, setStarting] = useState(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const run = useRunTracker({
    fallbackStages: ['tailor', 'cover', 'docx'],
    onDone: ({ failed }) => {
      if (failed) toast.error('Preparing materials failed. Open Resume → Auto Tailor to see the log.')
      else toast.success('Resume and cover letter are ready.')
      onDoneRef.current()
    },
  })
  const { attach, reset, state } = run

  // Pick up a prepare run for this job that is still going (drawer reopened, page reloaded).
  useEffect(() => {
    reset()
    if (!jobKey) return
    let cancelled = false
    listRuns()
      .then((runs) => {
        const live = runs.find((r) => r.running && r.job_id === jobKey && r.kind === 'tailor')
        if (!cancelled && live) attach(live, Date.parse(live.started_at) || Date.now())
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [jobKey, attach, reset])

  // Lost the stream (API restart): stop showing "Preparing…" and refresh what is there.
  useEffect(() => {
    if (state !== 'error') return
    reset()
    onDoneRef.current()
  }, [state, reset])

  const start = useCallback(async () => {
    if (!jobKey) return
    setStarting(true)
    try {
      attach(await startJobTailor(jobKey), Date.now())
      toast.success('Preparing your resume and cover letter. This takes a few minutes.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setStarting(false)
    }
  }, [jobKey, attach])

  return { running: state === 'running', starting, start }
}

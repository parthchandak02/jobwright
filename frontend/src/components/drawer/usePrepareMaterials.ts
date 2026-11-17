import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { listRuns, startJobTailor } from '@/lib/api'
import { useRunTracker } from '@/lib/useRunStream'
import { errorMessage } from '@/lib/utils'

/**
 * "Prepare resume + letter" for one job: starts the combined tailor run, or
 * picks up one that is already going, and follows it on the run stream (no
 * polling). `onDone` fires once when it ends.
 *
 * When `autoStart` is true (drawer open on backlog/prepare with no materials),
 * starts the same run as the Prepare button after checking for a live one.
 */
export function usePrepareMaterials(
  jobKey: string | null,
  onDone: () => void,
  options?: { autoStart?: boolean },
) {
  const autoStart = Boolean(options?.autoStart)
  const [starting, setStarting] = useState(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  // One auto-start attempt per jobKey while this drawer instance is open.
  const autoStartedKeyRef = useRef<string | null>(null)

  const run = useRunTracker({
    fallbackStages: ['tailor', 'cover', 'docx'],
    onDone: ({ failed }) => {
      if (failed) toast.error('Preparing materials failed. Open Resume → Auto Tailor to see the log.')
      else toast.success('Resume and cover letter are ready.')
      onDoneRef.current()
    },
  })
  const { attach, reset, state } = run

  // Pick up a prepare run for this job that is still going (drawer reopened, page reloaded),
  // or auto-start when the drawer opened a job that still needs materials.
  useEffect(() => {
    reset()
    if (!jobKey) {
      autoStartedKeyRef.current = null
      return
    }
    let cancelled = false
    listRuns()
      .then(async (runs) => {
        if (cancelled) return
        const live = runs.find((r) => r.running && r.job_id === jobKey && r.kind === 'tailor')
        if (live) {
          attach(live, Date.parse(live.started_at) || Date.now())
          autoStartedKeyRef.current = jobKey
          return
        }
        if (!autoStart || autoStartedKeyRef.current === jobKey) return
        autoStartedKeyRef.current = jobKey
        setStarting(true)
        try {
          if (cancelled) return
          attach(await startJobTailor(jobKey), Date.now())
          toast.success('Preparing your resume and cover letter. This takes a few minutes.')
        } catch (e) {
          autoStartedKeyRef.current = null
          if (!cancelled) toast.error(errorMessage(e))
        } finally {
          if (!cancelled) setStarting(false)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [jobKey, attach, reset, autoStart])

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
      autoStartedKeyRef.current = jobKey
      toast.success('Preparing your resume and cover letter. This takes a few minutes.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setStarting(false)
    }
  }, [jobKey, attach])

  return { running: state === 'running', starting, start }
}

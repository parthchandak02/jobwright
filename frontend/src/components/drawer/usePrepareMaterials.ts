import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, listRuns, startJobTailor } from '@/lib/api'
import { useRunTracker } from '@/lib/useRunStream'
import { errorMessage } from '@/lib/utils'

/**
 * "Prepare resume + letter" for one job: starts the combined tailor run, or
 * picks up one that is already going, and follows it on the run stream (no
 * polling). `onDone` fires once when it ends.
 *
 * When `autoStart` is true (today's daily-list pick, no materials), starts the
 * same run as the Prepare button after checking for a live one. Failures stay
 * inline and never auto-retry; the server claim blocks a second auto that day.
 */
export function usePrepareMaterials(
  jobKey: string | null,
  onDone: () => void,
  options?: { autoStart?: boolean },
) {
  const autoStart = Boolean(options?.autoStart)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  // One auto-start attempt per jobKey for this mount. Set only after the
  // start call returns (success, 409, or error) so StrictMode's remount can
  // still pick up a live run via listRuns. Never cleared on failure.
  const autoStartedKeyRef = useRef<string | null>(null)

  const run = useRunTracker({
    fallbackStages: ['tailor', 'cover', 'docx'],
    onDone: ({ failed }) => {
      if (failed) {
        const msg =
          'Preparing materials failed. Use Prepare to try again, or open Resume → Auto Tailor for the log.'
        setError(msg)
        toast.error(msg)
      } else {
        setError(null)
        toast.success('Resume and cover letter are ready.')
      }
      onDoneRef.current()
    },
  })
  const { attach, reset, state } = run

  // Pick up a prepare run for this job that is still going (drawer reopened, page reloaded),
  // or auto-start when the drawer opened a daily-list job that still needs materials.
  useEffect(() => {
    reset()
    setError(null)
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
        setStarting(true)
        try {
          const handle = await startJobTailor(jobKey, undefined, { auto: true })
          autoStartedKeyRef.current = jobKey
          if (cancelled) return
          attach(handle, Date.now())
          toast.success('Preparing your resume and cover letter. This takes a few minutes.')
        } catch (e) {
          autoStartedKeyRef.current = jobKey
          // Already claimed today (refresh / StrictMode): attach a live run if any.
          if (e instanceof ApiError && e.status === 409 && e.code === 'prepare_auto_already') {
            if (cancelled) return
            const again = await listRuns().catch(() => [] as Awaited<ReturnType<typeof listRuns>>)
            const live2 = again.find((r) => r.running && r.job_id === jobKey && r.kind === 'tailor')
            if (live2) attach(live2, Date.parse(live2.started_at) || Date.now())
            return
          }
          if (!cancelled) setError(errorMessage(e))
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
    setError(null)
    try {
      attach(await startJobTailor(jobKey), Date.now())
      autoStartedKeyRef.current = jobKey
      toast.success('Preparing your resume and cover letter. This takes a few minutes.')
    } catch (e) {
      const msg = errorMessage(e)
      setError(msg)
      toast.error(msg)
    } finally {
      setStarting(false)
    }
  }, [jobKey, attach])

  const clearError = useCallback(() => setError(null), [])

  return { running: state === 'running', starting, start, error, clearError }
}

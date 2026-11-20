import { useEffect, useRef, useState } from 'react'

import { shouldAskApplied, type PostingVisit } from '@/components/drawer/appliedPrompt'

/**
 * Remembers an Open posting tap and, when the tab is visible again after time away,
 * asks "Did you apply?" for that job. ``asking`` is true only for the job shown now.
 */
export function useAppliedPrompt(jobId: string | null | undefined, funnelStage: string | null | undefined) {
  const visit = useRef<PostingVisit | null>(null)
  const current = useRef({ jobId, funnelStage })
  const [askedFor, setAskedFor] = useState<string | null>(null)

  useEffect(() => {
    current.current = { jobId, funnelStage }
  }, [jobId, funnelStage])

  useEffect(() => {
    function onVisibility() {
      const v = visit.current
      if (!v || v.asked) return
      if (document.visibilityState === 'hidden') {
        v.leftAt = Date.now()
        return
      }
      if (shouldAskApplied({ visit: v, ...current.current, now: Date.now() })) {
        v.asked = true
        setAskedFor(v.jobId)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const stillBefore = funnelStage === 'backlog' || funnelStage === 'prepare'
  return {
    asking: !!jobId && askedFor === jobId && stillBefore,
    onOpenPosting: () => {
      if (!jobId || !stillBefore) return
      visit.current = { jobId, leftAt: Date.now(), asked: false }
      setAskedFor(null)
    },
    hide: () => setAskedFor(null),
  }
}

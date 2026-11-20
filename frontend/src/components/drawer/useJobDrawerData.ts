import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { ConnectionsData } from '@/components/ConnectionsPanel'
import type { MaterialsData } from '@/components/MaterialsPanel'
import { shouldShowContactDetails } from '@/components/drawer/contactDetails'
import {
  apiFetch,
  getBaseMaterials,
  getPersonalDetails,
  jobPath,
  type BaseMaterials,
  type JobCard,
} from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/**
 * Everything the drawer shows for one job: the card, its tailored materials,
 * connections, and the base resume / cover samples (cached for the session).
 * Late responses for a job that is no longer open are dropped.
 *
 * `ready` is true only after job + materials for the current `jobKey` have
 * settled (so auto-Prepare does not read a prior job's materials).
 */
export function useJobDrawerData(jobKey: string | null) {
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<MaterialsData | null>(null)
  const [base, setBase] = useState<BaseMaterials | null>(null)
  const [connections, setConnections] = useState<ConnectionsData | null>(null)
  const [personal, setPersonal] = useState<Record<string, string> | null>(null)
  const [ready, setReady] = useState(false)
  const loadSeq = useRef(0)

  const load = useCallback(async (key: string) => {
    const seq = ++loadSeq.current
    setReady(false)
    const j = await apiFetch<JobCard>(jobPath(key))
    if (seq !== loadSeq.current) return
    setJob(j)
    const [mRes, cRes, bRes, pRes] = await Promise.allSettled([
      apiFetch<MaterialsData>(`${jobPath(key)}/materials`),
      apiFetch<ConnectionsData>(`${jobPath(key)}/connections`),
      getBaseMaterials(),
      shouldShowContactDetails(j.funnel_stage) ? getPersonalDetails() : Promise.resolve(null),
    ])
    if (seq !== loadSeq.current) return
    setMaterials(mRes.status === 'fulfilled' ? mRes.value : null)
    setConnections(cRes.status === 'fulfilled' ? cRes.value : null)
    setBase(bRes.status === 'fulfilled' ? bRes.value : null)
    setPersonal(pRes.status === 'fulfilled' ? pRes.value : null)
    setReady(true)
  }, [])

  useEffect(() => {
    if (!jobKey) {
      loadSeq.current++
      setJob(null)
      setMaterials(null)
      setBase(null)
      setConnections(null)
      setPersonal(null)
      setReady(false)
      return
    }
    // Drop prior job data on the same mount (App keeps one drawer instance).
    setJob(null)
    setMaterials(null)
    setConnections(null)
    setPersonal(null)
    setReady(false)
    void load(jobKey).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  useEffect(() => {
    if (!jobKey || !job || personal !== null || !shouldShowContactDetails(job.funnel_stage)) return
    let cancelled = false
    void getPersonalDetails()
      .then((p) => {
        if (!cancelled) setPersonal(p)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [jobKey, job, personal])

  /** Refetch the open job (after a tailor run, a connection change…). */
  const reload = useCallback(() => {
    if (jobKey) void load(jobKey).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  return { job, setJob, materials, base, connections, personal, ready, reload }
}

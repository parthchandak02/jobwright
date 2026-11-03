import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { ConnectionsData } from '@/components/ConnectionsPanel'
import type { MaterialsData } from '@/components/MaterialsPanel'
import { apiFetch, getBaseMaterials, jobPath, type BaseMaterials, type JobCard } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/**
 * Everything the drawer shows for one job: the card, its tailored materials,
 * connections, and the base resume / cover samples (cached for the session).
 * Late responses for a job that is no longer open are dropped.
 */
export function useJobDrawerData(jobKey: string | null) {
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<MaterialsData | null>(null)
  const [base, setBase] = useState<BaseMaterials | null>(null)
  const [connections, setConnections] = useState<ConnectionsData | null>(null)
  const loadSeq = useRef(0)

  const load = useCallback(async (key: string) => {
    const seq = ++loadSeq.current
    const j = await apiFetch<JobCard>(jobPath(key))
    if (seq !== loadSeq.current) return
    setJob(j)
    const [mRes, cRes, bRes] = await Promise.allSettled([
      apiFetch<MaterialsData>(`${jobPath(key)}/materials`),
      apiFetch<ConnectionsData>(`${jobPath(key)}/connections`),
      getBaseMaterials(),
    ])
    if (seq !== loadSeq.current) return
    setMaterials(mRes.status === 'fulfilled' ? mRes.value : null)
    setConnections(cRes.status === 'fulfilled' ? cRes.value : null)
    setBase(bRes.status === 'fulfilled' ? bRes.value : null)
  }, [])

  useEffect(() => {
    if (!jobKey) {
      loadSeq.current++
      setJob(null)
      setMaterials(null)
      setBase(null)
      setConnections(null)
      return
    }
    setJob(null)
    void load(jobKey).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  /** Refetch the open job (after a tailor run, a connection change…). */
  const reload = useCallback(() => {
    if (jobKey) void load(jobKey).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  return { job, setJob, materials, base, connections, reload }
}

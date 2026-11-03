import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { SaveState } from '@/components/SaveStatus'
import { saveJobNotes, type JobCard } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

const NOTES_SAVE_MS = 800

/**
 * Autosaved notes for the open job. Saving only PATCHes the job: notes are not
 * on the board card, so the board is not refetched.
 */
export function useJobNotes(job: JobCard | null) {
  const [notes, setNotes] = useState('')
  const [state, setState] = useState<SaveState>('idle')
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const saved = useRef('')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobRef = useRef(job)
  jobRef.current = job
  const jobId = job?.job_id ?? null

  // New job: take its notes. Reloads of the same job keep what is being typed.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current)
    const initial = jobRef.current?.notes || ''
    setNotes(initial)
    saved.current = initial
    setState('idle')
  }, [jobId])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const persist = useCallback(async (next: string) => {
    const current = jobRef.current
    if (!current || next === saved.current) return
    setState('saving')
    try {
      await saveJobNotes(current, next)
      saved.current = next
      setState('saved')
      setSavedAt(Date.now())
    } catch (e) {
      setState('error')
      toast.error(errorMessage(e))
    }
  }, [])

  const onChange = useCallback(
    (next: string) => {
      setNotes(next)
      setState('idle')
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => void persist(next), NOTES_SAVE_MS)
    },
    [persist],
  )

  const flush = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    void persist(notes)
  }, [persist, notes])

  return { notes, state, savedAt, onChange, flush, retry: flush }
}

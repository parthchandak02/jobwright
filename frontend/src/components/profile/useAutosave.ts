import { useCallback, useEffect, useRef, useState } from 'react'
import type { SaveState } from '@/components/SaveStatus'

type Options<T, R> = {
  ms?: number
  onSaved?: (result: R, value: T) => void
  onError?: (error: unknown) => void
}

export function useAutosave<T, R = unknown>(save: (value: T) => Promise<R>, { ms = 700, onSaved, onError }: Options<T, R> = {}) {
  const [state, setState] = useState<SaveState>('idle')
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const saveRef = useRef(save)
  const onSavedRef = useRef(onSaved)
  const onErrorRef = useRef(onError)
  const timer = useRef<number | undefined>(undefined)
  const pending = useRef<{ value: T } | null>(null)
  const last = useRef<{ value: T } | null>(null)
  const seq = useRef(0)

  useEffect(() => {
    saveRef.current = save
    onSavedRef.current = onSaved
    onErrorRef.current = onError
  })

  const run = useCallback(async (value: T) => {
    const id = ++seq.current
    last.current = { value }
    setState('saving')
    try {
      const result = await saveRef.current(value)
      if (id !== seq.current) return
      setSavedAt(Date.now())
      setState(pending.current ? 'saving' : 'saved')
      onSavedRef.current?.(result, value)
    } catch (e) {
      if (id !== seq.current) return
      setState('error')
      onErrorRef.current?.(e)
    }
  }, [])

  const flush = useCallback(() => {
    window.clearTimeout(timer.current)
    const p = pending.current
    pending.current = null
    if (p) void run(p.value)
  }, [run])

  const schedule = useCallback(
    (value: T) => {
      pending.current = { value }
      setState('saving')
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(flush, ms)
    },
    [flush, ms],
  )

  const retry = useCallback(() => {
    const v = pending.current ?? last.current
    if (!v) return
    pending.current = null
    void run(v.value)
  }, [run])

  useEffect(
    () => () => {
      window.clearTimeout(timer.current)
      const p = pending.current
      pending.current = null
      if (p) void saveRef.current(p.value).catch(() => undefined)
    },
    [],
  )

  return { state, savedAt, schedule, flush, retry }
}

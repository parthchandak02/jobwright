import { useCallback, useEffect, useRef } from 'react'
import { holdUnsaved } from '@/lib/unsavedWork'

/** Debounce `fn`; a pending call is flushed on unmount so edits are never dropped. */
export function useDebouncedCallback<T>(fn: (value: T) => void, ms = 600): (value: T) => void {
  const fnRef = useRef(fn)
  const timer = useRef<number | undefined>(undefined)
  const pending = useRef<{ value: T } | null>(null)
  // While a call waits, the update check won't reload the page.
  const release = useRef<(() => void) | null>(null)

  useEffect(() => {
    fnRef.current = fn
  }, [fn])

  useEffect(
    () => () => {
      window.clearTimeout(timer.current)
      const p = pending.current
      pending.current = null
      release.current?.()
      release.current = null
      if (p) fnRef.current(p.value)
    },
    [],
  )

  return useCallback(
    (value: T) => {
      pending.current = { value }
      release.current ??= holdUnsaved()
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => {
        const p = pending.current
        pending.current = null
        release.current?.()
        release.current = null
        if (p) fnRef.current(p.value)
      }, ms)
    },
    [ms],
  )
}

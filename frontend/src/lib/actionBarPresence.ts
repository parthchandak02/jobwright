import { useEffect, useSyncExternalStore } from 'react'

/*
 * How many sticky ActionBars are on screen, so the toaster can sit above them instead of
 * covering their right end (bulk bar, unsaved changes).
 */
let shown = 0
const listeners = new Set<() => void>()

function emit() {
  for (const cb of listeners) cb()
}

/** Call from an ActionBar while it is shown. */
export function useRegisterActionBar(open: boolean) {
  useEffect(() => {
    if (!open) return
    shown += 1
    emit()
    return () => {
      shown -= 1
      emit()
    }
  }, [open])
}

export function useActionBarShown(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => {
        listeners.delete(cb)
      }
    },
    () => shown > 0,
    () => false,
  )
}

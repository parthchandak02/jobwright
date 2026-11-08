import { useEffect } from 'react'

/*
 * Edits that are typed but not saved yet (autosave waiting or failed, debounced admin edits), so the
 * update check never reloads the page over them. Counts holds; nothing here is rendered.
 */
let holds = 0

/** Take a hold while something is unsaved; call the returned function once it is saved. */
export function holdUnsaved(): () => void {
  holds += 1
  let released = false
  return () => {
    if (released) return
    released = true
    holds -= 1
  }
}

/** Hold while `active` is true (e.g. an autosave state of "saving" or "error"). */
export function useUnsavedWhile(active: boolean) {
  useEffect(() => (active ? holdUnsaved() : undefined), [active])
}

export function hasUnsavedWork(): boolean {
  return holds > 0
}

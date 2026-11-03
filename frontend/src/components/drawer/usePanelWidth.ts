import { useCallback, useState, useSyncExternalStore } from 'react'
import {
  clampPanelWidth,
  defaultPanelWidth,
  PANEL_MIN,
  PANEL_WIDTH_KEY,
  panelMax,
  parseStoredWidth,
} from '@/lib/jobPanel'

function subscribe(cb: () => void) {
  window.addEventListener('resize', cb)
  return () => window.removeEventListener('resize', cb)
}

function readStored(): number | null {
  try {
    return parseStoredWidth(localStorage.getItem(PANEL_WIDTH_KEY))
  } catch {
    return null
  }
}

/**
 * Width of the docked job panel. A width the person picked (drag or keyboard) is kept in
 * localStorage; otherwise the panel takes a share of the window. Always clamped so the
 * board keeps room.
 */
export function usePanelWidth() {
  const viewport = useSyncExternalStore(
    subscribe,
    () => window.innerWidth,
    () => 1440,
  )
  const [chosen, setChosen] = useState<number | null>(readStored)
  const width = chosen == null ? defaultPanelWidth(viewport) : clampPanelWidth(chosen, viewport)

  /** Set while dragging; pass `save` to remember it. */
  const setWidth = useCallback(
    (next: number, save = false) => {
      const clamped = clampPanelWidth(next, viewport)
      setChosen(clamped)
      if (save) {
        try {
          localStorage.setItem(PANEL_WIDTH_KEY, String(clamped))
        } catch {
          /* private mode: keep it for this visit */
        }
      }
    },
    [viewport],
  )

  const reset = useCallback(() => {
    setChosen(null)
    try {
      localStorage.removeItem(PANEL_WIDTH_KEY)
    } catch {
      /* ignore */
    }
  }, [])

  return { width, min: PANEL_MIN, max: panelMax(viewport), setWidth, reset }
}

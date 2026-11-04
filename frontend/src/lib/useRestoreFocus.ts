import { useCallback, useRef } from 'react'

type FocusHandler = (event: Event) => void

/**
 * Radix Dialog returns focus to its Trigger on close. Dialogs opened through the `open` prop
 * have no trigger, so focus fell to <body>. This remembers what had focus when the dialog
 * opened and puts it back on close, but only when nothing else took focus: a trigger, or a
 * caller's own `onCloseAutoFocus` (one that calls preventDefault is left alone entirely).
 */
export function useRestoreFocus(onOpenAutoFocus?: FocusHandler, onCloseAutoFocus?: FocusHandler) {
  const previous = useRef<HTMLElement | null>(null)

  const handleOpen = useCallback(
    (event: Event) => {
      // Fires before Radix moves focus into the content, so activeElement is still the opener.
      const active = document.activeElement
      previous.current = active instanceof HTMLElement && active !== document.body ? active : null
      onOpenAutoFocus?.(event)
    },
    [onOpenAutoFocus],
  )

  const handleClose = useCallback(
    (event: Event) => {
      onCloseAutoFocus?.(event)
      const el = previous.current
      previous.current = null
      if (event.defaultPrevented || !el) return
      // Radix focuses the trigger (if any) right after this handler; check once it has.
      requestAnimationFrame(() => {
        const active = document.activeElement
        if ((active === null || active === document.body) && el.isConnected) el.focus({ preventScroll: true })
      })
    },
    [onCloseAutoFocus],
  )

  return { onOpenAutoFocus: handleOpen, onCloseAutoFocus: handleClose }
}

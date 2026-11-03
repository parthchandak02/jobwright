import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePanelWidth } from '@/components/drawer/usePanelWidth'
import {
  findJobElement,
  focusTarget,
  JOB_KEY_ATTR,
  neighborJobId,
  PANEL_KEY_STEP,
  PANEL_KEY_STEP_BIG,
  PANEL_TWO_COLUMN_MIN,
} from '@/lib/jobPanel'
import { cn } from '@/lib/utils'

type Props = {
  jobKey: string
  title: string
  subtitle?: string
  onClose: () => void
  /** Show another job in the panel (previous / next in the list). */
  onOpenJob?: (jobId: string) => void
  /** Panel body; `twoColumns` says whether it is wide enough for two columns. */
  children: (twoColumns: boolean) => ReactNode
  /** Dialogs owned by the panel (rendered outside the scroll area). */
  dialogs?: ReactNode
}

function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  return el.isContentEditable || !!el.closest('input, textarea, select, [contenteditable="true"]')
}

/** A modal, menu, popover or select is open, or a card is being dragged: leave keys to it. */
function somethingElseOwnsKeys(): boolean {
  return !!document.querySelector(
    '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"], [data-radix-popper-content-wrapper], [aria-roledescription="sortable"][aria-pressed="true"]',
  )
}

function shortcutLabel(label: string, key: string) {
  return `${label} (${key})`
}

/**
 * Desktop job panel docked to the right of the board or table. Not modal: the list stays
 * usable, clicking another job swaps the panel. Resizable (drag or arrow keys on the edge,
 * double-click or Enter resets), remembered per browser. Escape closes; j / k (or Up / Down
 * on a focused card or row) go to the next / previous job in the lane or table.
 */
export function JobSidePanel({ jobKey, title, subtitle, onClose, onOpenJob, children, dialogs }: Props) {
  const { width, min, max, setWidth, reset } = usePanelWidth()
  const panelRef = useRef<HTMLElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const [dragging, setDragging] = useState(false)
  const [prevId, setPrevId] = useState<string | null>(null)
  const [nextId, setNextId] = useState<string | null>(null)
  const scrolledFor = useRef<string | null>(null)
  const lastKey = useRef(jobKey)
  lastKey.current = jobKey

  // Focus moves into the panel when it opens and back to the job's card or row when it closes.
  useEffect(() => {
    const panel = panelRef.current
    titleRef.current?.focus({ preventScroll: true })
    return () => {
      const active = document.activeElement
      if (active && active !== document.body && !panel?.contains(active)) return
      const key = lastKey.current
      requestAnimationFrame(() => {
        const el = findJobElement(key)
        const target = el && focusTarget(el)
        target?.focus({ preventScroll: true })
      })
    }
  }, [])

  // Keep previous / next current as the list changes under the panel (refresh, search, sort,
  // drag), and bring the open job's card into view once it is on screen (deep links).
  useEffect(() => {
    const sync = () => {
      setPrevId(neighborJobId(jobKey, -1))
      setNextId(neighborJobId(jobKey, 1))
      if (scrolledFor.current === jobKey) return
      const el = findJobElement(jobKey)
      if (el) {
        scrolledFor.current = jobKey
        el.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      }
    }
    sync()
    const list = document.querySelector('main')
    if (!list) return
    const observer = new MutationObserver(sync)
    observer.observe(list, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [jobKey])

  const go = (id: string | null, focusList: boolean) => {
    if (!id || !onOpenJob) return
    onOpenJob(id)
    requestAnimationFrame(() => {
      if (focusList) {
        const el = findJobElement(id)
        const target = el && focusTarget(el)
        target?.focus({ preventScroll: true })
        el?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      } else {
        titleRef.current?.focus({ preventScroll: true })
      }
    })
  }
  const goRef = useRef(go)
  goRef.current = go
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return
      if (somethingElseOwnsKeys()) return
      const target = e.target as HTMLElement | null
      const inPanel = !!target && !!panelRef.current?.contains(target)
      if (isEditable(target)) return
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
        return
      }
      // Up / Down on a focused card or row move from that one; j / k from the open job.
      const listItem = target?.closest<HTMLElement>(`main [${JOB_KEY_ATTR}]`)
      const onListItem = !!listItem
      let step: 1 | -1 | 0 = 0
      if (e.key === 'j' || (onListItem && e.key === 'ArrowDown')) step = 1
      else if (e.key === 'k' || (onListItem && e.key === 'ArrowUp')) step = -1
      if (!step) return
      const from = (e.key.startsWith('Arrow') && listItem?.getAttribute(JOB_KEY_ATTR)) || lastKey.current
      const id = neighborJobId(from, step)
      if (!id) return
      e.preventDefault()
      goRef.current(id, !inPanel)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function startDrag(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return
    e.preventDefault()
    const handle = e.currentTarget
    handle.setPointerCapture(e.pointerId)
    const startX = e.clientX
    const startWidth = width
    let latest = width
    setDragging(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    const move = (ev: globalThis.PointerEvent) => {
      latest = startWidth + (startX - ev.clientX)
      setWidth(latest)
    }
    const end = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', end)
      handle.removeEventListener('pointercancel', end)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      setDragging(false)
      setWidth(latest, true)
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', end)
    handle.addEventListener('pointercancel', end)
  }

  function onHandleKey(e: ReactKeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? PANEL_KEY_STEP_BIG : PANEL_KEY_STEP
    let next: number | null = null
    // The panel sits on the right, so Left makes it wider.
    if (e.key === 'ArrowLeft') next = width + step
    else if (e.key === 'ArrowRight') next = width - step
    else if (e.key === 'Home') next = min
    else if (e.key === 'End') next = max
    else if (e.key === 'Enter') {
      e.preventDefault()
      reset()
      return
    }
    if (next == null) return
    e.preventDefault()
    setWidth(next, true)
  }

  const twoColumns = width >= PANEL_TWO_COLUMN_MIN
  const titleId = `job-panel-title-${jobKey}`

  return (
    <aside
      ref={panelRef}
      aria-labelledby={titleId}
      style={{ width }}
      className="relative z-20 flex h-full min-h-0 shrink-0 animate-in flex-col border-l border-border bg-background duration-(--dur-2) ease-out fade-in-0 slide-in-from-right-4"
    >
      {/* Window-splitter pattern: a focusable separator with a value (WAI-ARIA APG). */}
      {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize job panel"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={width}
        aria-valuetext={`${width} pixels wide`}
        tabIndex={0}
        title="Drag to resize. Double-click to reset."
        data-dragging={dragging ? 'true' : 'false'}
        onPointerDown={startDrag}
        onDoubleClick={reset}
        onKeyDown={onHandleKey}
        className="group absolute inset-y-0 -left-1.5 z-10 w-3 cursor-col-resize touch-none"
      >
        <span
          aria-hidden
          className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-transparent transition-colors duration-(--dur-1) ease-out group-hover:bg-border-strong group-focus-visible:bg-primary group-data-[dragging=true]:bg-primary"
        />
      </div>
      {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}

      <header className="flex shrink-0 items-start gap-2 border-b border-border px-6 py-3">
        <div className="min-w-0 flex-1 py-0.5">
          {/* Focus lands here on open so screen readers hear the job; it is not a control, so no ring. */}
          <h2
            ref={titleRef}
            id={titleId}
            tabIndex={-1}
            className="line-clamp-2 rounded-sm text-heading text-foreground focus-visible:outline-none"
          >
            {title}
          </h2>
          {subtitle ? <p className="mt-0.5 truncate text-caption text-muted-foreground">{subtitle}</p> : null}
        </div>
        {onOpenJob ? (
          <div className="flex shrink-0 items-center">
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="Previous job"
              title={shortcutLabel('Previous job', 'K')}
              aria-keyshortcuts="k"
              disabled={!prevId}
              onClick={() => go(prevId, false)}
            >
              <ChevronUp />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="Next job"
              title={shortcutLabel('Next job', 'J')}
              aria-keyshortcuts="j"
              disabled={!nextId}
              onClick={() => go(nextId, false)}
            >
              <ChevronDown />
            </Button>
          </div>
        ) : null}
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label="Close job details"
          title={shortcutLabel('Close', 'Esc')}
          aria-keyshortcuts="Escape"
          onClick={onClose}
          className={cn('shrink-0', !onOpenJob && '-mr-2')}
        >
          <X />
        </Button>
      </header>

      {children(twoColumns)}
      {dialogs}
    </aside>
  )
}

import { useSyncExternalStore } from 'react'

/**
 * Desktop job panel: from this width up a job opens in a panel docked to the right of the
 * board or table (both stay usable). Below it the job opens in the full-screen / sheet drawer.
 */
export const DOCK_QUERY = '(min-width: 1280px)'

export const PANEL_WIDTH_KEY = 'jobwright-panel-width'
/** 32rem: the narrowest panel that still fits the action row and Stage pills. */
export const PANEL_MIN = 512
/** 56rem. */
export const PANEL_MAX = 896
/** Share of the window a new panel takes. */
export const PANEL_DEFAULT_SHARE = 0.45
/** Room always left for the board or table: sidebar rail (3.5rem) + 40rem, enough for the
 * board header (title, view tabs, search, actions as icons) and two lanes. */
export const PANEL_BOARD_RESERVE = 56 + 640
/** Panel width (52rem) from which the panel shows two columns (details | description + materials). */
export const PANEL_TWO_COLUMN_MIN = 832
/** Arrow-key step on the resize handle (Shift = bigger step). */
export const PANEL_KEY_STEP = 16
export const PANEL_KEY_STEP_BIG = 64

/** Largest panel this window allows (never below the minimum). */
export function panelMax(viewport: number): number {
  return Math.max(PANEL_MIN, Math.min(PANEL_MAX, viewport - PANEL_BOARD_RESERVE))
}

export function clampPanelWidth(width: number, viewport: number): number {
  if (!Number.isFinite(width)) return defaultPanelWidth(viewport)
  return Math.round(Math.min(panelMax(viewport), Math.max(PANEL_MIN, width)))
}

export function defaultPanelWidth(viewport: number): number {
  return clampPanelWidth(viewport * PANEL_DEFAULT_SHARE, viewport)
}

/** A saved width in pixels, or null when unset or unreadable. */
export function parseStoredWidth(raw: string | null): number | null {
  if (raw == null || raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

/*
 * The job open in the panel (or drawer), so cards and table rows can show which one it is.
 * A tiny store rather than a context: App sets it from the route, and only the card whose
 * answer changes re-renders.
 */
let selectedJob: string | null = null
const selectedListeners = new Set<() => void>()

export function setSelectedJob(jobId: string | null) {
  if (jobId === selectedJob) return
  selectedJob = jobId
  for (const cb of selectedListeners) cb()
}

function subscribeSelected(cb: () => void) {
  selectedListeners.add(cb)
  return () => {
    selectedListeners.delete(cb)
  }
}

export function useSelectedJob(jobId: string | undefined | null): boolean {
  return useSyncExternalStore(
    subscribeSelected,
    () => !!jobId && selectedJob === jobId,
    () => false,
  )
}

/** Marks the element in a list that stands for a job (board card wrapper, table row, phone card). */
export const JOB_KEY_ATTR = 'data-job-key'

function visible(el: Element): boolean {
  return el.getClientRects().length > 0
}

function listRoot(): ParentNode {
  return document.querySelector('main') || document
}

/** The visible list element (card or row) for a job, if it is on screen. */
export function findJobElement(jobId: string): HTMLElement | null {
  const all = listRoot().querySelectorAll<HTMLElement>(`[${JOB_KEY_ATTR}="${CSS.escape(jobId)}"]`)
  for (const el of all) if (visible(el)) return el
  return null
}

/** The control to focus for a list element: the card itself, or the row's title button. */
export function focusTarget(el: HTMLElement): HTMLElement | null {
  if (el.tabIndex >= 0) return el
  return el.querySelector<HTMLElement>('button, [tabindex="0"]')
}

/**
 * The job before or after `jobId` in the order it is shown: the same board lane, or the
 * table's current sort. Null at either end, or when the job isn't on screen.
 */
export function neighborJobId(jobId: string, step: 1 | -1): string | null {
  const el = findJobElement(jobId)
  const group = el?.closest('section, tbody')
  if (!el || !group) return null
  const items = Array.from(group.querySelectorAll<HTMLElement>(`[${JOB_KEY_ATTR}]`)).filter(visible)
  const next = items[items.indexOf(el) + step]
  return next?.getAttribute(JOB_KEY_ATTR) ?? null
}

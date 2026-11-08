import { useEffect, useRef, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { actionBarShownNow } from '@/lib/actionBarPresence'
import { hasUnsavedWork } from '@/lib/unsavedWork'
import {
  CLIENT_BUILD,
  isUpdateAvailable,
  POLL_MS,
  shouldAutoReload,
  shouldCheckNow,
  type ReloadGuard,
  type ReloadMoment,
  type ServerVersion,
  updatesEnabled,
} from '@/lib/version'

/* ---------------------------------------------------------------------------------------------
 * Shared store: the last GET /api/version answer (Settings shows it; the notifier polls it).
 * ------------------------------------------------------------------------------------------- */

let server: ServerVersion | null = null
let lastCheckAt: number | null = null
let inflight: Promise<ServerVersion | null> | null = null
const listeners = new Set<() => void>()

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

/** Fetch /api/version (deduplicated). Network errors keep the last answer. */
export function checkVersion(): Promise<ServerVersion | null> {
  if (inflight) return inflight
  lastCheckAt = Date.now()
  inflight = fetch('/api/version', { credentials: 'include', cache: 'no-store' })
    .then((res) => (res.ok ? (res.json() as Promise<ServerVersion>) : server))
    .catch(() => server)
    .then((next) => {
      if (next && next !== server) {
        server = next
        for (const cb of listeners) cb()
      }
      return server
    })
    .finally(() => {
      inflight = null
    })
  return inflight
}

/** The deployed version (null until the first answer); fetches once on first use. */
export function useServerVersion(): ServerVersion | null {
  const value = useSyncExternalStore(subscribe, () => server, () => null)
  useEffect(() => {
    if (!server) void checkVersion()
  }, [])
  return value
}

/* ---------------------------------------------------------------------------------------------
 * When is a reload safe?
 * ------------------------------------------------------------------------------------------- */

function currentGuard(pathname: string): ReloadGuard {
  const active = document.activeElement as HTMLElement | null
  const typing =
    !!active &&
    (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT' || active.isContentEditable)
  return {
    overlayOpen: !!document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]'),
    unsaved: hasUnsavedWork() || actionBarShownNow(),
    typing,
    formPage: pathname.startsWith('/welcome'),
  }
}

/** Reload once nothing is waiting to save (gives an in-flight autosave a few seconds). */
function reloadWhenSaved() {
  ;(document.activeElement as HTMLElement | null)?.blur?.()
  const started = Date.now()
  const tick = () => {
    if (!hasUnsavedWork() || Date.now() - started > 5000) window.location.reload()
    else window.setTimeout(tick, 200)
  }
  tick()
}

/** Board and an open job are one place; other pages are their own. */
function section(pathname: string): string {
  const first = pathname.split('/')[1] || ''
  return first === 'jobs' ? '' : first
}

const TOAST_ID = 'jobwright-update'

/**
 * Checks GET /api/version every 5 minutes and when the tab comes back. When a new build is deployed it
 * shows a calm toast with Refresh, and reloads by itself only at a safe moment: returning to a tab that
 * was away for a minute or more, or moving to another page, with no dialog open and nothing unsaved.
 * No service worker: works the same in the iOS home-screen app. Renders nothing.
 */
export function UpdateNotifier() {
  const { pathname } = useLocation()
  const value = useSyncExternalStore(subscribe, () => server, () => null)
  const ready = isUpdateAvailable(CLIENT_BUILD.build_id, value)
  const readyRef = useRef(ready)
  readyRef.current = ready
  const pathRef = useRef(pathname)
  const shownFor = useRef<string | null>(null)

  const tryReload = (moment: ReloadMoment) => {
    if (shouldAutoReload(readyRef.current, moment, currentGuard(window.location.pathname))) {
      window.location.reload()
      return true
    }
    return false
  }

  // Poll, and check again when the tab or window comes back.
  useEffect(() => {
    if (!updatesEnabled(CLIENT_BUILD.build_id)) return // dev server / tests
    void checkVersion()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void checkVersion()
    }, POLL_MS)
    let hiddenAt: number | null = document.visibilityState === 'hidden' ? Date.now() : null
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAt = Date.now()
        return
      }
      const hiddenMs = hiddenAt == null ? 0 : Date.now() - hiddenAt
      hiddenAt = null
      if (tryReload({ kind: 'visible', hiddenMs })) return
      if (shouldCheckNow(lastCheckAt, Date.now())) {
        void checkVersion().then(() => {
          // Learned about the update just now: still a fine moment to swap if they were away.
          tryReload({ kind: 'visible', hiddenMs })
        })
      }
    }
    const onFocus = () => {
      if (shouldCheckNow(lastCheckAt, Date.now())) void checkVersion()
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('focus', onFocus)
    }
  }, [])

  // Moving to another page is a natural moment to load the new version.
  useEffect(() => {
    const before = pathRef.current
    pathRef.current = pathname
    if (before !== pathname && section(before) !== section(pathname)) tryReload({ kind: 'navigate' })
  }, [pathname])

  // Tell the person once per new build.
  useEffect(() => {
    const id = value?.build_id
    if (!ready || !id || shownFor.current === id) return
    shownFor.current = id
    toast('A new version of jobwright is ready', {
      id: TOAST_ID,
      description: 'Refresh to get the latest. Nothing you saved is lost.',
      duration: Infinity,
      closeButton: true,
      action: { label: 'Refresh', onClick: reloadWhenSaved },
    })
  }, [ready, value?.build_id])

  return null
}

/*
 * Which build is running, which one the server has, and when it is safe to swap.
 * Pure helpers (tested in __tests__/version.test.ts); the hook lives in components/UpdateNotifier.
 */

/** GET /api/version */
export type ServerVersion = {
  /** Build id of the web bundle a refresh would load (null: dev server / not built). */
  build_id: string | null
  /** Short git sha of the deployed build. */
  version: string | null
  built_at: string | null
  deployed_at: string | null
  package_version?: string
  subject?: string | null
  /** Recent user-facing commit subjects ("What's new"). */
  changes?: string[]
}

export type ClientBuild = { build_id: string; sha: string; built_at: string }

/** The build this tab is running (set by vite.config.ts). */
export const CLIENT_BUILD: ClientBuild = __APP_BUILD__

/** Builds that never offer a refresh (dev server, tests). */
const NEVER_UPDATE = new Set(['dev', 'test', ''])

/** Poll every 5 minutes; focus / visibility checks at most once a minute. */
export const POLL_MS = 5 * 60_000
export const FOCUS_CHECK_MIN_MS = 60_000
/** Reload on return only after the tab was hidden this long (the person stepped away). */
export const HIDDEN_RELOAD_MS = 60_000

/** Does this build check for updates at all? (Not the dev server or tests.) */
export function updatesEnabled(clientBuildId: string): boolean {
  return !NEVER_UPDATE.has(clientBuildId)
}

/** Is a different build deployed than the one this tab runs? */
export function isUpdateAvailable(clientBuildId: string, server: Pick<ServerVersion, 'build_id'> | null | undefined): boolean {
  if (!updatesEnabled(clientBuildId)) return false
  const serverId = server?.build_id
  if (!serverId) return false
  return serverId !== clientBuildId
}

/** Focus / visibility events: check again only when the last check is old enough. */
export function shouldCheckNow(lastCheckAt: number | null, now: number, minGapMs = FOCUS_CHECK_MIN_MS): boolean {
  return lastCheckAt == null || now - lastCheckAt >= minGapMs
}

/** What could be lost by reloading right now. */
export type ReloadGuard = {
  /** A dialog, sheet or menu is open. */
  overlayOpen: boolean
  /** Typed but not saved (autosave waiting or failed, sticky "unsaved changes" bar). */
  unsaved: boolean
  /** Focus is in a text field. */
  typing: boolean
  /** A page whose answers live only in memory (onboarding). */
  formPage: boolean
}

export function safeToReload(g: ReloadGuard): boolean {
  return !g.overlayOpen && !g.unsaved && !g.typing && !g.formPage
}

export type ReloadMoment =
  /** The tab became visible again. */
  | { kind: 'visible'; hiddenMs: number }
  /** The person moved to another page inside the app. */
  | { kind: 'navigate' }

/**
 * Reload by itself only when nothing can be lost and the person won't be interrupted mid-task:
 * coming back to a tab that was away for a while, or moving to another page.
 */
export function shouldAutoReload(updateReady: boolean, moment: ReloadMoment, guard: ReloadGuard): boolean {
  if (!updateReady || !safeToReload(guard)) return false
  if (moment.kind === 'visible') return moment.hiddenMs >= HIDDEN_RELOAD_MS
  return true
}

/** "Nov 8, 3:12 PM" (local time), or "" for a missing / bad date. */
export function formatUpdatedAt(iso: string | null | undefined, locale?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(locale, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** "Version abc1234 · updated Nov 8, 3:12 PM" */
export function versionLine(sha: string | null | undefined, updatedAt: string | null | undefined, locale?: string): string {
  const v = sha ? `Version ${sha.slice(0, 7)}` : 'Version unknown'
  const when = formatUpdatedAt(updatedAt, locale)
  return when ? `${v} · updated ${when}` : v
}

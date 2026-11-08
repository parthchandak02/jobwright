import { describe, expect, it } from 'vitest'
import {
  HIDDEN_RELOAD_MS,
  formatUpdatedAt,
  isUpdateAvailable,
  safeToReload,
  shouldAutoReload,
  shouldCheckNow,
  updatesEnabled,
  versionLine,
  type ReloadGuard,
} from '@/lib/version'

const CALM: ReloadGuard = { overlayOpen: false, unsaved: false, typing: false, formPage: false }

describe('isUpdateAvailable', () => {
  it('is true only when the server has a different build', () => {
    expect(isUpdateAvailable('abc1234-x', { build_id: 'def5678-y' })).toBe(true)
    expect(isUpdateAvailable('abc1234-x', { build_id: 'abc1234-x' })).toBe(false)
  })
  it('ignores a missing answer or a server without a built frontend', () => {
    expect(isUpdateAvailable('abc1234-x', null)).toBe(false)
    expect(isUpdateAvailable('abc1234-x', { build_id: null })).toBe(false)
  })
  it('never offers a refresh on the dev server or in tests', () => {
    expect(isUpdateAvailable('dev', { build_id: 'abc' })).toBe(false)
    expect(isUpdateAvailable('test', { build_id: 'abc' })).toBe(false)
    expect(updatesEnabled('dev')).toBe(false)
    expect(updatesEnabled('abc1234-x')).toBe(true)
  })
})

describe('shouldCheckNow', () => {
  it('checks at once the first time, then at most once a minute', () => {
    expect(shouldCheckNow(null, 1000)).toBe(true)
    expect(shouldCheckNow(1000, 1000 + 30_000)).toBe(false)
    expect(shouldCheckNow(1000, 1000 + 60_000)).toBe(true)
  })
})

describe('shouldAutoReload', () => {
  const away = { kind: 'visible' as const, hiddenMs: HIDDEN_RELOAD_MS }

  it('reloads when the person comes back after a while and nothing can be lost', () => {
    expect(shouldAutoReload(true, away, CALM)).toBe(true)
  })
  it('does not reload after a quick tab switch', () => {
    expect(shouldAutoReload(true, { kind: 'visible', hiddenMs: 5_000 }, CALM)).toBe(false)
  })
  it('reloads on moving to another page', () => {
    expect(shouldAutoReload(true, { kind: 'navigate' }, CALM)).toBe(true)
  })
  it('does nothing without an update', () => {
    expect(shouldAutoReload(false, away, CALM)).toBe(false)
    expect(shouldAutoReload(false, { kind: 'navigate' }, CALM)).toBe(false)
  })
  it.each([
    ['a dialog or drawer is open', { overlayOpen: true }],
    ['edits are not saved', { unsaved: true }],
    ['focus is in a text field', { typing: true }],
    ['the page keeps answers in memory', { formPage: true }],
  ])('never reloads while %s', (_why, patch) => {
    const guard = { ...CALM, ...patch }
    expect(safeToReload(guard)).toBe(false)
    expect(shouldAutoReload(true, away, guard)).toBe(false)
    expect(shouldAutoReload(true, { kind: 'navigate' }, guard)).toBe(false)
  })
})

describe('versionLine', () => {
  it('shows the short sha and when it was updated', () => {
    const iso = '2026-11-08T15:12:00'
    expect(versionLine('abc1234def', iso, 'en-US')).toBe(`Version abc1234 · updated ${formatUpdatedAt(iso, 'en-US')}`)
    expect(formatUpdatedAt(iso, 'en-US')).toMatch(/^Nov 8, 3:12\sPM$/)
  })
  it('copes with missing parts', () => {
    expect(versionLine(null, null)).toBe('Version unknown')
    expect(versionLine('abc1234', 'not a date')).toBe('Version abc1234')
  })
})

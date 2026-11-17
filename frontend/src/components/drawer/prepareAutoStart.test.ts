import { describe, expect, it } from 'vitest'

import { isUtcToday, shouldAutoStartPrepare } from './prepareAutoStart'

const now = new Date('2026-11-17T15:00:00.000Z')

describe('isUtcToday', () => {
  it('matches the UTC calendar day', () => {
    expect(isUtcToday('2026-11-17T01:00:00+00:00', now)).toBe(true)
    expect(isUtcToday('2026-11-16T23:00:00+00:00', now)).toBe(false)
    expect(isUtcToday(null, now)).toBe(false)
  })
})

describe('shouldAutoStartPrepare', () => {
  const base = {
    jobId: 'abc123abc123',
    jobKey: 'abc123abc123',
    materialsReady: true,
    funnelStage: 'backlog' as string | null,
    hasResume: false,
    hasCover: false,
    whatsappNotifiedAt: '2026-11-17T12:00:00+00:00',
    prepareAutoStartedAt: null as string | null,
    now,
  }

  it('starts for a today daily-list pick with no materials', () => {
    expect(shouldAutoStartPrepare(base)).toBe(true)
    expect(shouldAutoStartPrepare({ ...base, funnelStage: 'prepare' })).toBe(true)
  })

  it('skips when the loaded job does not match the open key', () => {
    expect(shouldAutoStartPrepare({ ...base, jobId: 'otherjob0001' })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, jobId: null })).toBe(false)
  })

  it('skips until materials have settled', () => {
    expect(shouldAutoStartPrepare({ ...base, materialsReady: false })).toBe(false)
  })

  it('skips when a resume or cover already exists', () => {
    expect(shouldAutoStartPrepare({ ...base, hasResume: true })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, hasCover: true })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, hasResumeMd: true })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, hasCoverMd: true })).toBe(false)
  })

  it('skips jobs that are not on today\'s daily list', () => {
    expect(shouldAutoStartPrepare({ ...base, whatsappNotifiedAt: null })).toBe(false)
    expect(
      shouldAutoStartPrepare({ ...base, whatsappNotifiedAt: '2026-11-16T12:00:00+00:00' }),
    ).toBe(false)
  })

  it('skips when auto-Prepare already claimed today', () => {
    expect(
      shouldAutoStartPrepare({
        ...base,
        prepareAutoStartedAt: '2026-11-17T13:00:00+00:00',
      }),
    ).toBe(false)
  })

  it('skips later funnel stages and missing stage', () => {
    expect(shouldAutoStartPrepare({ ...base, funnelStage: 'applied' })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, funnelStage: 'closed' })).toBe(false)
    expect(shouldAutoStartPrepare({ ...base, funnelStage: null })).toBe(false)
  })
})

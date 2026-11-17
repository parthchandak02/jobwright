import { describe, expect, it } from 'vitest'

import { shouldAutoStartPrepare } from './prepareAutoStart'

describe('shouldAutoStartPrepare', () => {
  it('starts for backlog or prepare when there are no materials', () => {
    expect(
      shouldAutoStartPrepare({ funnelStage: 'backlog', hasResume: false, hasCover: false }),
    ).toBe(true)
    expect(
      shouldAutoStartPrepare({ funnelStage: 'prepare', hasResume: false, hasCover: false }),
    ).toBe(true)
  })

  it('skips when a resume or cover already exists', () => {
    expect(
      shouldAutoStartPrepare({ funnelStage: 'backlog', hasResume: true, hasCover: false }),
    ).toBe(false)
    expect(
      shouldAutoStartPrepare({ funnelStage: 'prepare', hasResume: false, hasCover: true }),
    ).toBe(false)
    expect(
      shouldAutoStartPrepare({
        funnelStage: 'backlog',
        hasResume: false,
        hasCover: false,
        hasResumeMd: true,
      }),
    ).toBe(false)
    expect(
      shouldAutoStartPrepare({
        funnelStage: 'prepare',
        hasResume: false,
        hasCover: false,
        hasCoverMd: true,
      }),
    ).toBe(false)
  })

  it('skips later funnel stages and missing stage', () => {
    expect(
      shouldAutoStartPrepare({ funnelStage: 'applied', hasResume: false, hasCover: false }),
    ).toBe(false)
    expect(
      shouldAutoStartPrepare({ funnelStage: 'closed', hasResume: false, hasCover: false }),
    ).toBe(false)
    expect(
      shouldAutoStartPrepare({ funnelStage: null, hasResume: false, hasCover: false }),
    ).toBe(false)
  })
})

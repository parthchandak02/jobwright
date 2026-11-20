import { describe, expect, it } from 'vitest'

import { MIN_AWAY_MS, shouldAskApplied, type PostingVisit } from './appliedPrompt'

describe('shouldAskApplied', () => {
  const visit: PostingVisit = { jobId: 'abc123abc123', leftAt: 1_000_000, asked: false }
  const base = { visit, jobId: 'abc123abc123', funnelStage: 'prepare', now: visit.leftAt + MIN_AWAY_MS }

  it('asks after 30 seconds away from a Backlog or Prepare job', () => {
    expect(shouldAskApplied(base)).toBe(true)
    expect(shouldAskApplied({ ...base, funnelStage: 'backlog', now: base.now + 600_000 })).toBe(true)
  })

  it('waits when she was away under the limit', () => {
    expect(shouldAskApplied({ ...base, now: visit.leftAt + MIN_AWAY_MS - 1 })).toBe(false)
    expect(shouldAskApplied({ ...base, now: visit.leftAt + 5_000 })).toBe(false)
  })

  it('never asks for jobs already applied or closed', () => {
    for (const stage of ['applied', 'in_progress', 'offer', 'closed', null]) {
      expect(shouldAskApplied({ ...base, funnelStage: stage })).toBe(false)
    }
  })

  it('never asks when another job is open or no posting was opened', () => {
    expect(shouldAskApplied({ ...base, jobId: 'other0other0' })).toBe(false)
    expect(shouldAskApplied({ ...base, jobId: null })).toBe(false)
    expect(shouldAskApplied({ ...base, visit: null })).toBe(false)
  })

  it('asks once per visit (Not yet keeps it hidden until the next Open posting)', () => {
    expect(shouldAskApplied({ ...base, visit: { ...visit, asked: true } })).toBe(false)
  })
})

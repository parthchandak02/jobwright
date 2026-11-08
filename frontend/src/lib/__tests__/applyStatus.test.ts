import { describe, expect, it } from 'vitest'
import { pickSummary } from '@/lib/applyStatus'
import type { ApplyPick } from '@/lib/api'

const base: ApplyPick = {
  id: 1, number: 1, job_url: 'https://example.com/j/1', job_id: 'abc', title: 'Analyst', company: 'Example Co',
  score: 9, picked_at: '2026-11-08T14:00:00Z', apply_after: '2026-11-08T17:00:00Z', status: 'planned',
  vetoed_by: null, outcome: null, submission_id: null,
}

describe('pickSummary', () => {
  it('names the apply time while the veto window is open', () => {
    expect(pickSummary(base, new Date('2026-11-08T15:00:00Z'))).toMatch(/^jobwright will apply to this job at /)
  })
  it('says it is about to apply once the time has passed', () => {
    expect(pickSummary(base, new Date('2026-11-08T18:00:00Z'))).toBe('jobwright is about to apply to this job.')
  })
  it('describes vetoed and applied picks', () => {
    expect(pickSummary({ ...base, status: 'vetoed' })).toMatch(/skipped/)
    expect(pickSummary({ ...base, status: 'applied' })).toMatch(/confirmation/)
  })
})

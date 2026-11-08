import { describe, expect, it } from 'vitest'
import {
  addMinutes,
  clockTime,
  currentStep,
  durationWords,
  guideSteps,
  THINGS_TO_ASK,
} from '@/lib/claudeGuide'
import type { ConnectedClaude } from '@/lib/api'

const client: ConnectedClaude = {
  id: 'g1',
  client_name: 'Claude',
  email: 'user1@example.com',
  scopes: ['jobs:read'],
  created_at: 1,
  last_used_at: null,
  active: true,
}
const none = { chrome: false, daily: false }

describe('guideSteps', () => {
  it('starts at connect when nothing is done', () => {
    const steps = guideSteps({ clients: [], missing_answers: 4, apply_via: 'connector' }, none)
    expect(steps.map((s) => s.done)).toEqual([false, false, false, false])
    expect(currentStep(steps)).toBe('connect')
  })

  it('moves to answers once a Claude is connected', () => {
    const steps = guideSteps({ clients: [client], missing_answers: 2, apply_via: 'connector' }, none)
    expect(currentStep(steps)).toBe('answers')
  })

  it('uses the ticked flags for the steps it cannot see', () => {
    const steps = guideSteps({ clients: [client], missing_answers: 0, apply_via: 'connector' }, { chrome: true, daily: false })
    expect(currentStep(steps)).toBe('daily')
    expect(currentStep(guideSteps({ clients: [client], missing_answers: 0, apply_via: 'connector' }, { chrome: true, daily: true }))).toBeNull()
  })

  it('lets a later step be done before an earlier one', () => {
    const steps = guideSteps({ clients: [], missing_answers: 0, apply_via: 'connector' }, { chrome: true, daily: false })
    expect(steps.map((s) => s.done)).toEqual([false, true, true, false])
    expect(currentStep(steps)).toBe('connect')
  })

  it('needs no daily task when jobwright’s server applies', () => {
    const steps = guideSteps({ clients: [client], missing_answers: 0, apply_via: 'server' }, { chrome: true, daily: false })
    expect(currentStep(steps)).toBeNull()
  })
})

describe('times', () => {
  it('formats a clock time and adds the buffer', () => {
    const at = new Date(2026, 10, 9, 10, 30).toISOString()
    expect(clockTime(at)).toBe('10:30 AM')
    expect(clockTime(addMinutes(at, 15))).toBe('10:45 AM')
    expect(clockTime(null)).toBeNull()
    expect(clockTime('nope')).toBeNull()
    expect(addMinutes(null, 5)).toBeNull()
  })

  it('says durations in words', () => {
    expect(durationWords(180)).toBe('3 hours')
    expect(durationWords(60)).toBe('1 hour')
    expect(durationWords(90)).toBe('90 minutes')
  })
})

describe('THINGS_TO_ASK', () => {
  it('stays short and plain', () => {
    expect(THINGS_TO_ASK.length).toBeGreaterThanOrEqual(5)
    for (const p of THINGS_TO_ASK) {
      expect(p.length).toBeLessThan(110)
      expect(p).not.toMatch(/MCP|OAuth|scope|_id/i)
    }
  })
})

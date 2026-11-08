import { describe, expect, it } from 'vitest'
import { describeClient, relativeDay } from '@/lib/connector'

const NOW = new Date(2026, 10, 8, 15, 0, 0)
const at = (y: number, m: number, d: number, h = 9) => new Date(y, m, d, h).getTime() / 1000

describe('relativeDay', () => {
  it('reads like a person would say it', () => {
    expect(relativeDay(null, NOW)).toBe('never')
    expect(relativeDay(at(2026, 10, 8), NOW)).toBe('today')
    expect(relativeDay(at(2026, 10, 7, 23), NOW)).toBe('yesterday')
    expect(relativeDay(at(2026, 10, 4), NOW)).toBe('4 days ago')
    expect(relativeDay(at(2026, 9, 1), NOW)).toMatch(/2026/)
  })
})

describe('describeClient', () => {
  it('names the widest permission first', () => {
    const base = { id: 'g', client_name: 'Claude', email: 'user1@example.com', active: true }
    expect(
      describeClient({ ...base, scopes: ['jobs:read', 'jobs:write', 'apply'], created_at: at(2026, 10, 8), last_used_at: null }, NOW),
    ).toBe('can apply for you · connected today · last used never')
    expect(
      describeClient({ ...base, scopes: ['jobs:read'], created_at: at(2026, 10, 6), last_used_at: at(2026, 10, 7) }, NOW),
    ).toBe('can read your board · connected 2 days ago · last used yesterday')
  })
})

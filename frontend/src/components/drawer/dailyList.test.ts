import { describe, expect, it } from 'vitest'

import { dailyListFor, isRecentList, latestRecentList, listDayLabel } from './dailyList'

const MON = '2026-11-16T15:00:00.000000+00:00'
const SUN = '2026-11-22T15:00:00.000000+00:00'

function job(id: string, sentAt: string | null, fit: number, stage = 'backlog') {
  return { job_id: id, whatsapp_notified_at: sentAt, fit_score: fit, funnel_stage: stage, title: `Role ${id}` }
}

describe('dailyListFor', () => {
  const board = [
    job('c', SUN, 7),
    job('a', SUN, 9),
    job('x', MON, 8),
    job('b', SUN, 8),
    job('z', null, 9),
  ]

  it('returns null for a job that was not on any list', () => {
    expect(dailyListFor(board, 'z')).toBeNull()
    expect(dailyListFor(board, 'missing')).toBeNull()
    expect(dailyListFor(board, null)).toBeNull()
  })

  it('orders the list best match first and gives the position and next job', () => {
    const list = dailyListFor(board, 'a')
    expect(list).toMatchObject({ sentAt: SUN, position: 1, total: 3, done: false })
    expect(list?.next?.job_id).toBe('b')
  })

  it('never mixes two different sends', () => {
    const list = dailyListFor(board, 'x')
    expect(list).toMatchObject({ sentAt: MON, position: 1, total: 1, next: null, done: false })
    expect(dailyListFor(board, 'b')?.total).toBe(3)
  })

  it('from the last job wraps to an earlier one still open', () => {
    const list = dailyListFor(board, 'c')
    expect(list).toMatchObject({ position: 3, total: 3 })
    expect(list?.next?.job_id).toBe('a')
  })

  it('skips jobs already applied or closed', () => {
    const jobs = [job('a', SUN, 9), job('b', SUN, 8, 'applied'), job('c', SUN, 7, 'closed'), job('d', SUN, 6, 'prepare')]
    expect(dailyListFor(jobs, 'a')?.next?.job_id).toBe('d')
  })

  it('says the list is done when every job is applied or closed', () => {
    const jobs = [job('a', SUN, 9, 'applied'), job('b', SUN, 8, 'closed'), job('c', SUN, 7, 'in_progress')]
    expect(dailyListFor(jobs, 'a')).toMatchObject({ prev: null, next: null, done: true })
  })

  it('gives prev in list order, null at first of list, and skips applied or closed jobs', () => {
    expect(dailyListFor(board, 'a')?.prev).toBeNull()
    expect(dailyListFor(board, 'b')?.prev?.job_id).toBe('a')
    expect(dailyListFor(board, 'c')?.prev?.job_id).toBe('b')

    const withApplied = [job('a', SUN, 9), job('b', SUN, 8, 'applied'), job('c', SUN, 7, 'closed'), job('d', SUN, 6, 'prepare')]
    expect(dailyListFor(withApplied, 'd')?.prev?.job_id).toBe('a')

    const earlierApplied = [job('a', SUN, 9, 'applied'), job('b', SUN, 8, 'backlog'), job('c', SUN, 7, 'prepare')]
    expect(dailyListFor(earlierApplied, 'b')?.prev).toBeNull()
  })
})

describe('isRecentList / listDayLabel', () => {
  const now = new Date('2026-11-22T20:00:00Z')

  it('keeps lists from the last 7 days only', () => {
    expect(isRecentList(SUN, now)).toBe(true)
    expect(isRecentList(MON, now)).toBe(true)
    expect(isRecentList('2026-11-14T15:00:00+00:00', now)).toBe(false)
    expect(isRecentList('not a date', now)).toBe(false)
  })

  it("names today's list, else the send's day", () => {
    const local = new Date(2026, 10, 22, 20, 0)
    expect(listDayLabel(new Date(2026, 10, 22, 8, 0).toISOString(), local)).toBe("today's list")
    expect(listDayLabel(new Date(2026, 10, 21, 23, 0).toISOString(), local)).toBe("yesterday's list")
    expect(listDayLabel(new Date(2026, 10, 19, 9, 0).toISOString(), local)).toBe(`${new Date(2026, 10, 19).toLocaleDateString(undefined, { weekday: 'short' })}'s list`)
  })
})

describe('latestRecentList (Today\'s list filter)', () => {
  const now = new Date('2026-11-23T09:00:00Z')

  it('picks the newest send and the filter keeps only its jobs', () => {
    const board = [job('a', MON, 9), job('b', SUN, 8), job('c', null, 9), job('d', SUN, 6, 'applied')]
    const latest = latestRecentList(board, now)
    expect(latest).toBe(SUN)
    expect(board.filter((j) => j.whatsapp_notified_at === latest).map((j) => j.job_id)).toEqual(['b', 'd'])
  })

  it('compares times, not strings', () => {
    const later = '2026-11-22T16:00:00Z'
    expect(latestRecentList([job('a', later, 9), job('b', SUN, 8)], now)).toBe(later)
  })

  it('is null when the newest send is older than a week or nothing was sent', () => {
    expect(latestRecentList([job('a', MON, 9)], new Date('2026-11-30T09:00:00Z'))).toBeNull()
    expect(latestRecentList([job('a', null, 9), job('b', 'not a date', 8)], now)).toBeNull()
    expect(latestRecentList([], now)).toBeNull()
  })
})

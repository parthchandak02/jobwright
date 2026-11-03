import { describe, expect, it } from 'vitest'

import type { BoardResponse, JobCard } from '@/lib/api'
import {
  buildQueue,
  clearSkips,
  keyAction,
  mergeQueue,
  reviewCount,
  reviewPosition,
  sessionCounts,
  swipeAnswer,
  upcoming,
  type ReviewAnswer,
} from '@/lib/reviewQueue'

import { job } from './fixtures'

function board(backlog: JobCard[], prepare: JobCard[] = []): BoardResponse {
  return { stages: ['backlog', 'prepare'], columns: { backlog, prepare }, total: backlog.length + prepare.length }
}

const byId = (jobs: JobCard[]) => Object.fromEntries(jobs.map((j) => [j.job_id, j]))

describe('buildQueue', () => {
  it('keeps unrated Backlog jobs, best score first, unscored last', () => {
    const low = job({ job_id: 'low', fit_score: 4 })
    const none = job({ job_id: 'none', fit_score: null })
    const high = job({ job_id: 'high', fit_score: 9 })
    const rated = job({ job_id: 'rated', fit_score: 10, user_fit_score: 8 })
    const prep = job({ job_id: 'prep', fit_score: 10, funnel_stage: 'prepare' })
    const q = buildQueue(board([low, none, high, rated], [prep]))
    expect(q.map((j) => j.job_id)).toEqual(['high', 'low', 'none'])
    expect(reviewCount(board([low, none, high, rated], [prep]))).toBe(3)
  })

  it('breaks score ties by confidence, then newest', () => {
    const a = job({ job_id: 'a', fit_score: 8, score_confidence: 0.6, discovered_at: '2026-10-02' })
    const b = job({ job_id: 'b', fit_score: 8, score_confidence: 0.9, discovered_at: '2026-10-01' })
    const c = job({ job_id: 'c', fit_score: 8, score_confidence: 0.6, discovered_at: '2026-10-03' })
    expect(buildQueue(board([a, b, c])).map((j) => j.job_id)).toEqual(['b', 'c', 'a'])
  })

  it('is empty without a board', () => {
    expect(buildQueue(null)).toEqual([])
    expect(reviewCount(null)).toBe(0)
  })
})

describe('mergeQueue', () => {
  it('keeps the session order and appends new jobs', () => {
    const fresh = [job({ job_id: 'x' }), job({ job_id: 'b' }), job({ job_id: 'y' })]
    expect(mergeQueue(['a', 'b'], fresh)).toEqual(['a', 'b', 'x', 'y'])
  })
})

describe('reviewPosition', () => {
  const jobs = [
    job({ job_id: 'a', fit_score: 9 }),
    job({ job_id: 'b', fit_score: 7 }),
    job({ job_id: 'c', fit_score: 5 }),
    job({ job_id: 'd', fit_score: null }),
  ]
  const ids = jobs.map((j) => j.job_id)

  it('counts answered jobs and finds the next one', () => {
    const answers: Record<string, ReviewAnswer> = { a: 'interested' }
    expect(reviewPosition(ids, byId(jobs), answers, 'all')).toEqual({ current: 'b', number: 2, answered: 1, total: 4 })
  })

  it('limits to strong matches with the Strong filter', () => {
    expect(reviewPosition(ids, byId(jobs), {}, 'strong')).toEqual({ current: 'a', number: 1, answered: 0, total: 2 })
    const done = reviewPosition(ids, byId(jobs), { a: 'skip', b: 'not_for_me' }, 'strong')
    expect(done).toEqual({ current: null, number: 2, answered: 2, total: 2 })
  })

  it('skips ids whose job is gone from the board', () => {
    expect(reviewPosition(['gone', ...ids], byId(jobs), {}, 'all').current).toBe('a')
  })

  it('lists the next jobs to prefetch', () => {
    expect(upcoming(ids, byId(jobs), { a: 'skip' }, 'all', 2)).toEqual(['c', 'd'])
    expect(upcoming(ids, byId(jobs), {}, 'strong', 2)).toEqual(['b'])
  })
})

describe('session counts and skips', () => {
  it('tallies answers and clears skips only', () => {
    const answers: Record<string, ReviewAnswer> = { a: 'interested', b: 'skip', c: 'not_for_me', d: 'skip' }
    expect(sessionCounts(answers)).toEqual({ interested: 1, not_for_me: 1, skip: 2 })
    expect(clearSkips(answers)).toEqual({ a: 'interested', c: 'not_for_me' })
  })
})

describe('keyAction', () => {
  const k = (key: string, mods: Partial<KeyboardEvent> = {}) =>
    keyAction({ key, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mods })

  it('maps arrows and letters', () => {
    expect(k('ArrowRight')).toBe('interested')
    expect(k('i')).toBe('interested')
    expect(k('ArrowLeft')).toBe('not_for_me')
    expect(k('N')).toBe('not_for_me')
    expect(k('ArrowDown')).toBe('skip')
    expect(k('s')).toBe('skip')
    expect(k('u')).toBe('undo')
    expect(k('o')).toBe('posting')
    expect(k('f')).toBe('open')
    expect(k('3')).toEqual({ reason: 2 })
  })

  it('treats Cmd/Ctrl+Z as undo and ignores other modified keys', () => {
    expect(k('z', { metaKey: true })).toBe('undo')
    expect(k('z', { ctrlKey: true })).toBe('undo')
    expect(k('z', { metaKey: true, shiftKey: true })).toBeNull()
    expect(k('i', { metaKey: true })).toBeNull()
    expect(k('0')).toBeNull()
    expect(k('x')).toBeNull()
  })
})

describe('swipeAnswer', () => {
  it('commits past the threshold in either direction', () => {
    expect(swipeAnswer(120, 100)).toBe('interested')
    expect(swipeAnswer(-100, 100)).toBe('not_for_me')
    expect(swipeAnswer(60, 100)).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { undoRequests } from '@/components/jobs-table/useBulkActions'
import { toggleSelected } from '@/components/jobs-table/useSelection'
import type { BulkResponse, JobCard } from '@/lib/api'

const job = (id: string, stage = 'backlog', outcome: string | null = null) =>
  ({ job_id: id, url: `https://example.com/${id}`, funnel_stage: stage, outcome }) as unknown as JobCard

const shown = ['a', 'b', 'c', 'd', 'e'].map((id) => job(id))
const url = (id: string) => `https://example.com/${id}`

describe('toggleSelected', () => {
  it('toggles one job', () => {
    const on = toggleSelected(new Set(), shown, url('b'), null)
    expect([...on]).toEqual([url('b')])
    expect(toggleSelected(on, shown, url('b'), null).size).toBe(0)
  })

  it('selects a range from the anchor in either direction', () => {
    const start = new Set([url('b')])
    expect([...toggleSelected(start, shown, url('d'), url('b'))].sort()).toEqual([url('b'), url('c'), url('d')])
    expect([...toggleSelected(new Set([url('d')]), shown, url('a'), url('d'))].sort()).toEqual(
      [url('a'), url('b'), url('c'), url('d')],
    )
  })

  it('a range on a selected row clears the range', () => {
    const all = new Set(shown.map((j) => j.url))
    expect([...toggleSelected(all, shown, url('c'), url('a'))].sort()).toEqual([url('d'), url('e')])
  })

  it('falls back to a single toggle when the anchor is hidden', () => {
    expect([...toggleSelected(new Set(), shown, url('c'), url('zzz'))]).toEqual([url('c')])
  })
})

describe('undoRequests', () => {
  const res = (results: BulkResponse['results']): BulkResponse => ({
    action: 'close',
    to_stage: 'closed',
    updated: results.length,
    results,
    jobs: [],
  })

  it('groups jobs by the lane they came from and clears dismiss labels after a close', () => {
    const before = new Map([job('a'), job('b', 'prepare'), job('c'), job('d', 'closed', 'rejected')].map((j) => [j.job_id, j]))
    const reqs = undoRequests(
      res([
        { job_id: 'a', ok: true, from_stage: 'backlog' },
        { job_id: 'b', ok: true, from_stage: 'prepare' },
        { job_id: 'c', ok: true, from_stage: 'backlog' },
        { job_id: 'd', ok: true, from_stage: 'closed' },
        { job_id: 'x', ok: false, error: 'not_found' },
      ]),
      before,
      true,
    )
    expect(reqs).toEqual([
      { job_ids: ['a', 'c'], action: 'move', stage: 'backlog', clear_dismiss_labels: true },
      { job_ids: ['b'], action: 'move', stage: 'prepare', clear_dismiss_labels: true },
      { job_ids: ['d'], action: 'close', outcome: 'rejected' },
    ])
  })

  it('a plain move undo leaves labels alone', () => {
    const reqs = undoRequests(res([{ job_id: 'a', ok: true, from_stage: 'applied' }]), new Map(), false)
    expect(reqs).toEqual([{ job_ids: ['a'], action: 'move', stage: 'applied', clear_dismiss_labels: false }])
  })
})

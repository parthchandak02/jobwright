import { describe, expect, it } from 'vitest'

import type { BoardResponse } from '@/lib/api'
import { findJobStage, moveJobAcrossColumns, reorderWithinColumn } from '@/lib/boardDnD'

import { job } from './fixtures'

function board(): BoardResponse {
  const a = job({ url: 'a', funnel_stage: 'backlog' })
  const b = job({ url: 'b', funnel_stage: 'backlog' })
  const c = job({ url: 'c', funnel_stage: 'backlog' })
  const d = job({ url: 'd', funnel_stage: 'prepare' })
  return {
    stages: ['backlog', 'prepare', 'applied'],
    columns: { backlog: [a, b, c], prepare: [d], applied: [] },
    total: 4,
  }
}

const urls = (b: BoardResponse | null, stage: string) => b?.columns[stage].map((j) => j.url)

describe('findJobStage', () => {
  it('resolves a stage id to itself and a card to its column', () => {
    const b = board()
    expect(findJobStage('prepare', b.stages, b.columns)).toBe('prepare')
    expect(findJobStage('c', b.stages, b.columns)).toBe('backlog')
    expect(findJobStage('missing', b.stages, b.columns)).toBeUndefined()
  })
})

describe('moveJobAcrossColumns', () => {
  it('moves a card before the card it is dropped on and updates its stage', () => {
    const next = moveJobAcrossColumns(board(), 'b', 'd')
    expect(urls(next, 'backlog')).toEqual(['a', 'c'])
    expect(urls(next, 'prepare')).toEqual(['b', 'd'])
    expect(next?.columns.prepare[0].funnel_stage).toBe('prepare')
  })

  it('appends when dropped on an empty column', () => {
    const next = moveJobAcrossColumns(board(), 'a', 'applied')
    expect(urls(next, 'applied')).toEqual(['a'])
  })

  it('returns null within the same column or for unknown ids', () => {
    expect(moveJobAcrossColumns(board(), 'a', 'c')).toBeNull()
    expect(moveJobAcrossColumns(board(), 'zzz', 'prepare')).toBeNull()
  })

  it('does not mutate the original board', () => {
    const b = board()
    moveJobAcrossColumns(b, 'a', 'applied')
    expect(urls(b, 'backlog')).toEqual(['a', 'b', 'c'])
    expect(b.columns.backlog[0].funnel_stage).toBe('backlog')
  })
})

describe('reorderWithinColumn', () => {
  it('moves a card to the position of the card it is dropped on', () => {
    expect(urls(reorderWithinColumn(board(), 'a', 'c'), 'backlog')).toEqual(['b', 'c', 'a'])
    expect(urls(reorderWithinColumn(board(), 'c', 'a'), 'backlog')).toEqual(['c', 'a', 'b'])
  })

  it('returns null across columns or when dropped on itself', () => {
    expect(reorderWithinColumn(board(), 'a', 'd')).toBeNull()
    expect(reorderWithinColumn(board(), 'a', 'a')).toBeNull()
  })
})

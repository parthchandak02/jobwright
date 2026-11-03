import { describe, expect, it } from 'vitest'

import type { BoardResponse } from '@/lib/api'
import type { ClientRect, CollisionDetection } from '@dnd-kit/core'
import {
  createKanbanCollisionDetection,
  findJobStage,
  laneTabId,
  moveJobAcrossColumns,
  reorderWithinColumn,
  stageFromLaneTab,
} from '@/lib/boardDnD'

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

describe('phone stage drop targets', () => {
  it('round-trips a stage through its drop target id', () => {
    expect(stageFromLaneTab(laneTabId('applied'))).toBe('applied')
    expect(stageFromLaneTab('applied')).toBeNull()
    expect(stageFromLaneTab('https://example.com/jobs/1')).toBeNull()
  })

  const rect = (left: number, top: number, width: number, height: number): ClientRect => ({
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
  })

  function args(pointer: { x: number; y: number }) {
    const rects = new Map([
      [laneTabId('applied'), rect(0, 0, 100, 44)],
      ['backlog', rect(0, 100, 390, 600)],
      ['a', rect(0, 100, 390, 120)],
    ])
    const containers = [...rects.keys()].map((id) => ({
      id,
      key: id,
      data: { current: undefined },
      disabled: false,
      node: { current: null },
      rect: { current: rects.get(id)! },
    }))
    return {
      active: { id: 'b', data: { current: undefined }, rect: { current: { initial: null, translated: null } } },
      collisionRect: rect(pointer.x - 20, pointer.y - 20, 40, 40),
      droppableRects: rects,
      droppableContainers: containers,
      pointerCoordinates: pointer,
    } as unknown as Parameters<CollisionDetection>[0]
  }

  it('picks the drop target under the finger', () => {
    const b = board()
    const detect = createKanbanCollisionDetection(b.stages, b.columns)
    expect(detect(args({ x: 50, y: 20 }))[0]?.id).toBe(laneTabId('applied'))
  })

  it('never falls back to a drop target the finger is not on', () => {
    const b = board()
    const detect = createKanbanCollisionDetection(b.stages, b.columns)
    const hits = detect(args({ x: 200, y: 80 })).map((c) => String(c.id))
    expect(hits.some((id) => stageFromLaneTab(id))).toBe(false)
  })
})

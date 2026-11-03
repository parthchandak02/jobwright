import {
  CollisionDetection,
  closestCorners,
  pointerWithin,
  type ClientRect,
  type KeyboardCoordinateGetter,
} from '@dnd-kit/core'
import { arrayMove } from '@dnd-kit/sortable'
import type { BoardResponse, JobCard } from '@/lib/api'

export function findJobStage(
  id: string,
  stages: string[],
  columns: Record<string, JobCard[]>,
): string | undefined {
  if (stages.includes(id)) return id
  for (const stage of stages) {
    if (columns[stage]?.some((job) => job.url === id)) return stage
  }
  return undefined
}

const LANE_TAB_PREFIX = 'lane-tab:'

/** Droppable id of a phone stage drop target (drop a card on it to move it to that stage). */
export function laneTabId(stage: string): string {
  return LANE_TAB_PREFIX + stage
}

/** The stage a stage drop target stands for, or null for cards and lanes. */
export function stageFromLaneTab(id: string): string | null {
  return id.startsWith(LANE_TAB_PREFIX) ? id.slice(LANE_TAB_PREFIX.length) : null
}

export function createKanbanCollisionDetection(
  stages: string[],
  columns: Record<string, JobCard[]>,
): CollisionDetection {
  return (args) => {
    const pointerCollisions = pointerWithin(args)
    if (pointerCollisions.length > 0) {
      // Phone stage drop targets win over anything under the finger.
      const tab = pointerCollisions.find((collision) => stageFromLaneTab(String(collision.id)))
      if (tab) return [tab]
      for (const collision of pointerCollisions) {
        const id = String(collision.id)
        if (!stages.includes(id)) continue

        const items = columns[id] || []
        if (items.length > 0) {
          const itemCollisions = closestCorners({
            ...args,
            droppableContainers: args.droppableContainers.filter((container) =>
              items.some((job) => job.url === container.id),
            ),
          })
          if (itemCollisions.length > 0) return itemCollisions
        }
        return [{ id }]
      }
      return pointerCollisions
    }
    // Stage drop targets only count when the finger is on them.
    return closestCorners({
      ...args,
      droppableContainers: args.droppableContainers.filter((container) => !stageFromLaneTab(String(container.id))),
    })
  }
}

/** Move a card into another column while dragging (optimistic, live preview). */
export function moveJobAcrossColumns(
  board: BoardResponse,
  activeId: string,
  overId: string,
): BoardResponse | null {
  const activeStage = findJobStage(activeId, board.stages, board.columns)
  const overStage = findJobStage(overId, board.stages, board.columns)
  if (!activeStage || !overStage || activeStage === overStage) return null

  const activeItems = [...board.columns[activeStage]]
  const overItems = [...board.columns[overStage]]
  const activeIndex = activeItems.findIndex((job) => job.url === activeId)
  if (activeIndex === -1) return null

  let overIndex = overItems.findIndex((job) => job.url === overId)
  if (overIndex === -1) overIndex = overItems.length

  const [moved] = activeItems.splice(activeIndex, 1)
  const updated: JobCard = { ...moved, funnel_stage: overStage }
  overItems.splice(overIndex, 0, updated)

  return {
    ...board,
    columns: {
      ...board.columns,
      [activeStage]: activeItems,
      [overStage]: overItems,
    },
  }
}

/** Reorder within a single column on drop. */
export function reorderWithinColumn(
  board: BoardResponse,
  activeId: string,
  overId: string,
): BoardResponse | null {
  const stage = findJobStage(activeId, board.stages, board.columns)
  if (!stage || stage !== findJobStage(overId, board.stages, board.columns)) return null
  if (activeId === overId) return null

  const items = [...board.columns[stage]]
  const oldIndex = items.findIndex((job) => job.url === activeId)
  const newIndex = items.findIndex((job) => job.url === overId)
  if (oldIndex === -1 || newIndex === -1) return null

  return {
    ...board,
    columns: {
      ...board.columns,
      [stage]: arrayMove(items, oldIndex, newIndex),
    },
  }
}

/**
 * Arrow keys for a keyboard drag on the board: Up/Down step through the
 * current lane, Left/Right jump to the neighbouring visible lane (to the card
 * at about the same height, or the empty lane). The default sortable getter
 * picks the geometrically closest droppable, which on this board can be the
 * next card in the same lane for Left/Right (the lifted card is tilted).
 */
export function createBoardKeyboardCoordinates(getBoard: () => BoardResponse | null): KeyboardCoordinateGetter {
  return (event, { context }) => {
    const { active, over, collisionRect, droppableRects } = context
    const code = event.code
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(code)) return undefined
    event.preventDefault()
    const board = getBoard()
    if (!board || !active || !collisionRect) return undefined

    const overId = String(over?.id ?? active.id)
    const stage = findJobStage(overId, board.stages, board.columns)
    if (!stage) return undefined
    const lane = (board.columns[stage] || []).filter((job) => droppableRects.has(job.url))
    let target: { left: number; top: number } | undefined

    if (code === 'ArrowUp' || code === 'ArrowDown') {
      const idx = lane.findIndex((job) => job.url === overId)
      if (idx === -1) return undefined
      const next = lane[code === 'ArrowDown' ? idx + 1 : idx - 1]
      target = next ? droppableRects.get(next.url) : undefined
    } else {
      const shown = board.stages.filter((s) => droppableRects.has(s))
      const nextStage = shown[shown.indexOf(stage) + (code === 'ArrowRight' ? 1 : -1)]
      if (!nextStage) return undefined
      let best: ClientRect | undefined
      for (const job of board.columns[nextStage] || []) {
        if (job.url === active.id) continue
        const rect = droppableRects.get(job.url)
        if (rect && (!best || Math.abs(rect.top - collisionRect.top) < Math.abs(best.top - collisionRect.top))) best = rect
      }
      target = best || droppableRects.get(nextStage)
    }
    return target ? { x: target.left, y: target.top } : undefined
  }
}

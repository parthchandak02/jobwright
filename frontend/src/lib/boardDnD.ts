import {
  CollisionDetection,
  closestCorners,
  pointerWithin,
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

export function createKanbanCollisionDetection(
  stages: string[],
  columns: Record<string, JobCard[]>,
): CollisionDetection {
  return (args) => {
    const pointerCollisions = pointerWithin(args)
    if (pointerCollisions.length > 0) {
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
    return closestCorners(args)
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

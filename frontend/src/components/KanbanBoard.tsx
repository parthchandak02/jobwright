import { useMemo, useRef, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  type ScreenReaderInstructions,
  type UniqueIdentifier,
} from '@dnd-kit/core'
import { BoardResponse, JobCard, STAGE_LABELS } from '@/lib/api'
import {
  createBoardKeyboardCoordinates,
  createKanbanCollisionDetection,
  findJobStage,
  moveJobAcrossColumns,
  reorderWithinColumn,
} from '@/lib/boardDnD'
import { JobCardView } from '@/components/JobCardView'
import { KanbanColumn } from '@/components/KanbanColumn'
import { Skeleton } from '@/components/ui/skeleton'

type Props = {
  board: BoardResponse
  setBoard: (board: BoardResponse) => void
  /** Lanes to show (all, or the one picked in the sidebar). */
  stages: string[]
  /** Cards to show per lane (after search). Drag logic always uses the full `board`. */
  columns: Record<string, JobCard[]>
  searching: boolean
  onOpen: (job: JobCard) => void
  onScoreSaved: (job: JobCard) => void
  /** A card was dropped in another lane at `position`; `revert` is the board before the drag. */
  onMove: (job: JobCard, toStage: string, position: number, revert: BoardResponse | null) => void
  /** A lane's order changed by hand; `next` is the board as shown, `revert` the board before the drag. */
  onReorder: (stage: string, next: BoardResponse, revert: BoardResponse | null) => void
}

const screenReaderInstructions: ScreenReaderInstructions = {
  draggable:
    'Press Enter to open this job. To move it, press Space to pick it up, use the arrow keys to move it ' +
    'up and down or to another stage, press Space again to drop it, or Escape to cancel.',
}

function laneName(stage: string | undefined) {
  return stage ? STAGE_LABELS[stage] || stage : 'no stage'
}

function sameOrder(a: JobCard[] = [], b: JobCard[] = []) {
  return a.length === b.length && a.every((job, i) => job.url === b[i]?.url)
}

/** The drag-and-drop board: lanes, sortable cards, mouse/touch/keyboard sensors and announcements. */
export function KanbanBoard({ board, setBoard, stages, columns, searching, onOpen, onScoreSaved, onMove, onReorder }: Props) {
  const [activeCard, setActiveCard] = useState<JobCard | null>(null)
  const [dropTargetStage, setDropTargetStage] = useState<string | null>(null)
  const dragOriginStage = useRef<string | null>(null)
  const boardSnapshot = useRef<BoardResponse | null>(null)
  // The keyboard sensor keeps its options for the whole drag; read the live board through a ref.
  const boardRef = useRef(board)
  boardRef.current = board
  const keyboardCoordinates = useMemo(() => createBoardKeyboardCoordinates(() => boardRef.current), [])

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    // Long-press to drag on touch screens, so a normal swipe still scrolls.
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
    // Space picks up and drops; Enter is left for opening the job.
    useSensor(KeyboardSensor, {
      coordinateGetter: keyboardCoordinates,
      keyboardCodes: { start: ['Space'], cancel: ['Escape'], end: ['Space', 'Enter'] },
    }),
  )

  const collisionDetection = useMemo(() => createKanbanCollisionDetection(board.stages, board.columns), [board])

  const allJobs = useMemo(() => board.stages.flatMap((s) => board.columns[s] || []), [board])

  const announcements = useMemo<Announcements>(() => {
    const title = (id: UniqueIdentifier) => {
      const job = allJobs.find((j) => j.url === String(id))
      return job ? `${job.title || 'Job'} at ${job.company || 'unknown company'}` : 'Job'
    }
    const place = (id: UniqueIdentifier) => {
      const stage = findJobStage(String(id), board.stages, board.columns)
      const cards = stage ? board.columns[stage] || [] : []
      const idx = cards.findIndex((j) => j.url === String(id))
      return idx >= 0 ? `${laneName(stage)}, position ${idx + 1} of ${cards.length}` : laneName(stage)
    }
    return {
      onDragStart: ({ active }) => `Picked up ${title(active.id)}. It is in ${place(active.id)}.`,
      onDragOver: ({ active, over }) =>
        over ? `${title(active.id)} is now in ${place(over.id)}.` : `${title(active.id)} is not over a stage.`,
      onDragEnd: ({ active, over }) =>
        over ? `Dropped ${title(active.id)} in ${place(over.id)}.` : `Dropped ${title(active.id)}.`,
      onDragCancel: ({ active }) =>
        `Cancelled. ${title(active.id)} went back to ${laneName(dragOriginStage.current || undefined)}.`,
    }
  }, [allJobs, board])

  function reset() {
    setActiveCard(null)
    setDropTargetStage(null)
    dragOriginStage.current = null
    boardSnapshot.current = null
  }

  function onDragStart(event: DragStartEvent) {
    const url = String(event.active.id)
    setActiveCard(allJobs.find((j) => j.url === url) || null)
    boardSnapshot.current = board
    dragOriginStage.current = findJobStage(url, board.stages, board.columns) || null
  }

  function onDragOver(event: DragOverEvent) {
    const { active, over } = event
    if (!over) return
    setDropTargetStage(findJobStage(String(over.id), board.stages, board.columns) || null)
    const next = moveJobAcrossColumns(board, String(active.id), String(over.id))
    if (next) setBoard(next)
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event
    const snapshot = boardSnapshot.current
    const originStage = dragOriginStage.current
    reset()
    const url = String(active.id)
    let working = board
    if (over) {
      const reordered = reorderWithinColumn(board, url, String(over.id))
      if (reordered) {
        working = reordered
        setBoard(reordered)
      }
    }
    const stage = findJobStage(url, working.stages, working.columns)
    if (!stage || !originStage) return
    if (stage === originStage) {
      if (!sameOrder(snapshot?.columns[stage], working.columns[stage])) onReorder(stage, working, snapshot)
      return
    }
    const cards = working.columns[stage] || []
    const job = cards.find((j) => j.url === url)
    if (job) onMove(job, stage, Math.max(0, cards.indexOf(job)), snapshot)
  }

  function onDragCancel() {
    const snapshot = boardSnapshot.current
    reset()
    if (snapshot) setBoard(snapshot)
  }

  const dropAnimation = useMemo(
    () => ({ sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }) }),
    [],
  )

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisionDetection}
      accessibility={{ announcements, screenReaderInstructions }}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
    >
      <div className="-mx-3 flex h-full min-h-[70vh] gap-3 overflow-x-auto px-3 pb-2 md:mx-0 md:px-0">
        {stages.map((stage) => (
          <KanbanColumn
            key={stage}
            stage={stage}
            label={STAGE_LABELS[stage] || stage}
            jobs={columns[stage] || []}
            total={stage === 'closed' ? board.closed_total : undefined}
            isDropTarget={dropTargetStage === stage}
            isDragging={!!activeCard}
            searching={searching}
            onOpen={onOpen}
            onScoreSaved={onScoreSaved}
          />
        ))}
      </div>
      <DragOverlay dropAnimation={dropAnimation}>
        {activeCard ? <JobCardView job={activeCard} stage={dropTargetStage || activeCard.funnel_stage} dragging /> : null}
      </DragOverlay>
    </DndContext>
  )
}

/** Loading placeholder shaped like the lanes. */
export function BoardSkeleton() {
  return (
    <div aria-label="Loading your jobs" role="status" className="flex gap-3 overflow-hidden">
      {[0, 1, 2, 3, 4].map((col) => (
        <div key={col} className="w-full shrink-0 space-y-2 md:w-auto md:max-w-[26rem] md:min-w-[17.5rem] md:flex-1">
          <Skeleton className="mx-1.5 my-2 h-4 w-24" />
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      ))}
    </div>
  )
}

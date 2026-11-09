import { useMemo, useRef, useState, type ReactNode, type TouchEvent } from 'react'
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
  stageFromLaneTab,
} from '@/lib/boardDnD'
import { findJobElement, focusTarget } from '@/lib/jobPanel'
import { JobCardView } from '@/components/JobCardView'
import { KanbanColumn } from '@/components/KanbanColumn'
import { StageDropGrid } from '@/components/StageDropGrid'
import { StageTabs } from '@/components/StageTabs'
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
  /**
   * Phone: one lane at a time under a sticky stage strip (`stages` should be `[lane]`). Swipe
   * sideways to change lanes; long-press a card and drop it on a stage (`StageDropGrid`) to move it.
   */
  phone?: PhoneLane
}

export type PhoneLane = {
  lane: string
  onLaneChange: (stage: string) => void
  counts: Record<string, number>
  /** Shown before the strip (the Board / Table toggle). */
  leading?: ReactNode
}

const NO_JOBS: JobCard[] = []
const MOUSE_OPTIONS = { activationConstraint: { distance: 8 } }
// Long-press to drag on touch screens, so a normal swipe still scrolls.
const TOUCH_OPTIONS = { activationConstraint: { delay: 250, tolerance: 8 } }
// Space picks up and drops; Enter is left for opening the job.
const KEYBOARD_CODES = { start: ['Space'], cancel: ['Escape'], end: ['Space', 'Enter'] }

/** A horizontal swipe: far enough, mostly sideways and quick (so it never fights vertical scroll). */
const SWIPE_MIN_PX = 56
const SWIPE_MAX_MS = 600
const PHONE_AUTO_SCROLL = { threshold: { x: 0, y: 0.2 } }

const screenReaderInstructions: ScreenReaderInstructions = {
  draggable:
    'Press Enter to open this job. To move it, press Space to pick it up, use the arrow keys to move it ' +
    'up and down or to another stage, press Space again to drop it, or Escape to cancel.',
}

function laneName(stage: string | undefined) {
  return stage ? STAGE_LABELS[stage] || stage : 'no stage'
}

/**
 * A card that crosses lanes mid-drag is a new element, so a keyboard drag loses focus. Put it
 * back on the card (wherever it ended up) once the board has settled.
 */
function refocusCard(jobId: string) {
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const el = findJobElement(jobId)
      const target = el && focusTarget(el)
      if (target && document.activeElement !== target) target.focus({ preventScroll: false })
    }),
  )
}

function sameOrder(a: JobCard[] = [], b: JobCard[] = []) {
  return a.length === b.length && a.every((job, i) => job.url === b[i]?.url)
}

/** The drag-and-drop board: lanes, sortable cards, mouse/touch/keyboard sensors and announcements. */
export function KanbanBoard({
  board,
  setBoard,
  stages,
  columns,
  searching,
  onOpen,
  onScoreSaved,
  onMove,
  onReorder,
  phone,
}: Props) {
  const [activeCard, setActiveCard] = useState<JobCard | null>(null)
  const [dropTargetStage, setDropTargetStage] = useState<string | null>(null)
  const dragOriginStage = useRef<string | null>(null)
  const keyboardDrag = useRef(false)
  const boardSnapshot = useRef<BoardResponse | null>(null)
  // The keyboard sensor keeps its options for the whole drag; read the live board through a ref.
  const boardRef = useRef(board)
  boardRef.current = board
  const keyboardCoordinates = useMemo(() => createBoardKeyboardCoordinates(() => boardRef.current), [])

  // Sensor options must keep their identity: new ones change every card's drag listeners,
  // which re-renders all (memoized) cards.
  const keyboardOptions = useMemo(
    () => ({ coordinateGetter: keyboardCoordinates, keyboardCodes: KEYBOARD_CODES }),
    [keyboardCoordinates],
  )
  const sensors = useSensors(
    useSensor(MouseSensor, MOUSE_OPTIONS),
    useSensor(TouchSensor, TOUCH_OPTIONS),
    useSensor(KeyboardSensor, keyboardOptions),
  )

  const collisionDetection = useMemo(() => createKanbanCollisionDetection(board.stages, board.columns), [board])

  const allJobs = useMemo(() => board.stages.flatMap((s) => board.columns[s] || []), [board])

  const announcements = useMemo<Announcements>(() => {
    const title = (id: UniqueIdentifier) => {
      const job = allJobs.find((j) => j.url === String(id))
      return job ? `${job.title || 'Job'} at ${job.company || 'unknown company'}` : 'Job'
    }
    const place = (id: UniqueIdentifier) => {
      const tabStage = stageFromLaneTab(String(id))
      if (tabStage) return `${laneName(tabStage)}; drop to move it there`
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

  // Phone swipe between lanes. A drag that started from a long-press never counts as a swipe.
  const swipeStart = useRef<{ x: number; y: number; t: number } | null>(null)
  const dragged = useRef(false)

  function onTouchStart(e: TouchEvent) {
    dragged.current = false
    const t = e.touches[0]
    swipeStart.current = e.touches.length === 1 && t ? { x: t.clientX, y: t.clientY, t: Date.now() } : null
  }

  function onTouchEnd(e: TouchEvent) {
    const start = swipeStart.current
    swipeStart.current = null
    const t = e.changedTouches[0]
    if (!phone || !start || !t || dragged.current || activeCard) return
    const dx = t.clientX - start.x
    const dy = t.clientY - start.y
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * 2 || Date.now() - start.t > SWIPE_MAX_MS) return
    const i = board.stages.indexOf(phone.lane)
    const next = board.stages[i + (dx < 0 ? 1 : -1)]
    if (i >= 0 && next) phone.onLaneChange(next)
  }

  function onDragStart(event: DragStartEvent) {
    dragged.current = true
    const url = String(event.active.id)
    keyboardDrag.current = event.activatorEvent instanceof KeyboardEvent
    setActiveCard(allJobs.find((j) => j.url === url) || null)
    boardSnapshot.current = board
    dragOriginStage.current = findJobStage(url, board.stages, board.columns) || null
  }

  function onDragOver(event: DragOverEvent) {
    const { active, over } = event
    if (!over) {
      // Phone: leaving a stage target clears its highlight.
      if (phone) setDropTargetStage(null)
      return
    }
    const tabStage = stageFromLaneTab(String(over.id))
    if (tabStage) {
      // Over a phone stage target: highlight it; the card moves on drop.
      setDropTargetStage(tabStage)
      return
    }
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
    if (keyboardDrag.current) {
      const id = allJobs.find((j) => j.url === url)?.job_id
      if (id) refocusCard(id)
    }
    const tabStage = over ? stageFromLaneTab(String(over.id)) : null
    if (tabStage) {
      // Dropped on a phone stage target: move to the top of that lane.
      const job = board.columns[originStage || '']?.find((j) => j.url === url)
      if (job && originStage && tabStage !== originStage) onMove(job, tabStage, 0, snapshot)
      return
    }
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

  function onDragCancel(event: { active: { id: UniqueIdentifier } }) {
    const snapshot = boardSnapshot.current
    reset()
    if (keyboardDrag.current) {
      const id = allJobs.find((j) => j.url === String(event.active.id))?.job_id
      if (id) refocusCard(id)
    }
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
      // Phone: one lane, so only scroll it up and down while dragging.
      autoScroll={phone ? PHONE_AUTO_SCROLL : undefined}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
    >
      {phone ? (
        <div className="sticky -top-3 z-10 -mx-3 -mt-3 mb-1 flex items-center gap-2 bg-background px-3 py-2">
          {phone.leading}
          <StageTabs
            className="flex-1"
            stages={board.stages}
            counts={phone.counts}
            value={phone.lane}
            onChange={phone.onLaneChange}
          />
        </div>
      ) : null}
      {phone && activeCard ? <StageDropGrid stages={board.stages} current={phone.lane} over={dropTargetStage} /> : null}
      <div
        className={
          phone
            ? 'flex min-h-[70vh] flex-col pb-2'
            : '-mx-3 flex h-full min-h-[70vh] gap-3 overflow-x-auto px-3 pb-2 md:mx-0 md:w-max md:min-w-full md:overflow-visible md:px-0'
        }
        onTouchStart={phone ? onTouchStart : undefined}
        onTouchEnd={phone ? onTouchEnd : undefined}
      >
        {stages.map((stage, i) => (
          <KanbanColumn
            key={stage}
            nextStage={stages[i + 1]}
            nextLabel={stages[i + 1] ? STAGE_LABELS[stages[i + 1]] || stages[i + 1] : undefined}
            fill={!!phone}
            stage={stage}
            label={STAGE_LABELS[stage] || stage}
            jobs={columns[stage] || NO_JOBS}
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

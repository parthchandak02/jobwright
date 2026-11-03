import type { CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useDroppable } from '@dnd-kit/core'
import { STAGE_LABELS, laneTone } from '@/lib/api'
import { laneTabId } from '@/lib/boardDnD'
import { cn } from '@/lib/utils'

function DropTarget({ stage, current, over }: { stage: string; current: boolean; over: boolean }) {
  const { setNodeRef } = useDroppable({ id: laneTabId(stage), disabled: current })
  const lane = laneTone(stage)
  return (
    <div
      ref={setNodeRef}
      style={{ '--lane': lane, '--tone': lane } as CSSProperties}
      className={cn(
        'flex h-11 min-w-0 items-center justify-center gap-1.5 rounded-md border px-2 text-label transition-colors duration-(--dur-1) ease-out',
        current
          ? 'border-transparent bg-surface-muted text-muted-foreground'
          : over
            ? 'tone-tint border-(--lane)'
            : 'border-dashed border-border-strong bg-surface text-foreground',
      )}
    >
      <span aria-hidden className="size-2 shrink-0 rounded-full bg-(--lane)" />
      <span className="truncate">{STAGE_LABELS[stage] || stage}</span>
    </div>
  )
}

/**
 * Phone board, while a card is dragged (long-press): every stage as a drop target pinned over the
 * top of the screen, so a card can move to a lane that isn't shown. Must sit inside the DndContext.
 */
export function StageDropGrid({ stages, current, over }: { stages: string[]; current: string; over: string | null }) {
  return createPortal(
    <div
      aria-hidden
      className="fixed inset-x-0 top-0 z-40 animate-in border-b border-border bg-background px-3 pt-2 pb-3 shadow-e1 duration-(--dur-2) fade-in-0 md:hidden"
    >
      <p className="mb-2 text-caption text-muted-foreground">Drop on a stage to move it there</p>
      <div className="grid grid-cols-3 gap-2">
        {stages.map((stage) => (
          <DropTarget key={stage} stage={stage} current={stage === current} over={over === stage && stage !== current} />
        ))}
      </div>
    </div>,
    document.body,
  )
}

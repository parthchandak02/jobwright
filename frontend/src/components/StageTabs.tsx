import type { CSSProperties } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { STAGE_LABELS, laneTone } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  stages: string[]
  /** Jobs per stage, shown after the label. */
  counts: Record<string, number>
  /** Current stage, or 'all' (only with `allCount`). */
  value: string
  onChange: (stage: string) => void
  /** Adds an "All" tab first (the table filter); omit on the one-lane board. */
  allCount?: number
  className?: string
}

const TRIGGER = 'touch-target gap-2 px-3 tabular-nums group-data-[variant=pill]/tabs-list:flex-none'

function TabLabel({ label, count, stage }: { label: string; count: number; stage?: string }) {
  return (
    <>
      {stage ? <span aria-hidden className="size-2 shrink-0 rounded-full bg-(--lane)" /> : null}
      <span>{label}</span>
      <span className="text-micro font-medium text-muted-foreground">
        {count}
        <span className="sr-only"> {count === 1 ? 'job' : 'jobs'}</span>
      </span>
    </>
  )
}

/**
 * Phone stage strip: a sideways-scrolling segmented control with a lane dot and count per stage.
 * On the board it picks the one lane shown; in the table it filters (with "All").
 */
// The strip filters the one list below it rather than switching tab panels, so triggers drop
// Radix's aria-controls (it would point at panels that don't exist).
export function StageTabs({ stages, counts, value, onChange, allCount, className }: Props) {
  return (
    <Tabs value={value} onValueChange={onChange} className={cn('min-w-0 gap-0', className)}>
      <TabsList scrollable aria-label="Stages">
        {allCount != null ? (
          <TabsTrigger value="all" aria-controls={undefined} className={TRIGGER}>
            <TabLabel label="All" count={allCount} />
          </TabsTrigger>
        ) : null}
        {stages.map((stage) => (
          <TabsTrigger
            key={stage}
            value={stage}
            aria-controls={undefined}
            style={{ '--lane': laneTone(stage) } as CSSProperties}
            className={TRIGGER}
          >
            <TabLabel label={STAGE_LABELS[stage] || stage} count={counts[stage] ?? 0} stage={stage} />
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

import type { CSSProperties } from 'react'
import { ArrowRightLeft, ChevronDown, Loader2, ThumbsDown, X } from 'lucide-react'
import { ActionBar } from '@/components/ActionBar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { FUNNEL_STAGES, laneTone, STAGE_LABELS, type JobCard } from '@/lib/api'

type Props = {
  jobs: JobCard[]
  busy: boolean
  onClear: () => void
  onMove: (stage: string) => void
  /** Opens the close dialog ("Not for me" before applying, "Close" otherwise). */
  onClose: () => void
}

/** Before applying, closing means "Not for me"; once any job is applied it's a plain Close. */
export function allBeforeApplying(jobs: JobCard[]) {
  return jobs.every((j) => j.funnel_stage === 'backlog' || j.funnel_stage === 'prepare')
}

/**
 * Sticky bar for the table selection: count + clear, "Move to…" lane menu and
 * "Not for me". Floats at the bottom of the table on desktop; full width above
 * the safe area on phones.
 */
export function BulkBar({ jobs, busy, onClear, onMove, onClose }: Props) {
  const count = jobs.length
  if (count === 0) return null
  const notForMe = allBeforeApplying(jobs)
  const stages = FUNNEL_STAGES.filter((s) => s !== 'closed')
  const allIn = (stage: string) => jobs.every((j) => j.funnel_stage === stage)

  return (
    <ActionBar
      label="Selected jobs"
      className="mt-3 max-md:-mx-3 max-md:-bottom-3 max-md:-mb-3"
      message={
        <span className="flex items-center gap-1.5">
          <Button type="button" variant="ghost" size="icon-sm" onClick={onClear} aria-label="Clear selection" className="-ml-1.5">
            <X />
          </Button>
          <span className="text-label text-foreground tabular-nums">{count} selected</span>
        </span>
      }
    >
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" size="sm" variant="secondary" disabled={busy}>
            <ArrowRightLeft className="max-md:hidden" />
            <span className="md:hidden">Move</span>
            <span className="max-md:hidden">Move to…</span>
            <ChevronDown className="text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="top" className="min-w-44">
          <DropdownMenuLabel className="text-caption text-muted-foreground">Move {count === 1 ? 'job' : `${count} jobs`} to</DropdownMenuLabel>
          {stages.map((stage) => (
            <DropdownMenuItem key={stage} disabled={allIn(stage)} onSelect={() => onMove(stage)}>
              <span
                aria-hidden
                className="size-2 shrink-0 rounded-full bg-(--lane)"
                style={{ '--lane': laneTone(stage) } as CSSProperties}
              />
              {STAGE_LABELS[stage]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onClose}>
        {busy ? <Loader2 className="animate-spin" /> : <ThumbsDown className="max-md:hidden" />}
        {notForMe ? 'Not for me' : 'Close'}
      </Button>
    </ActionBar>
  )
}

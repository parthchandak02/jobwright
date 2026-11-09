import type { CSSProperties } from 'react'
import { ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { FUNNEL_STAGES, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  disabled?: boolean
  onMove: (toStage: string) => void
  className?: string
}

function Dot({ stage }: { stage: string }) {
  return (
    <span
      aria-hidden
      style={{ '--lane': laneTone(stage) } as CSSProperties}
      className="size-2 shrink-0 rounded-full bg-(--lane)"
    />
  )
}

/** The job's stage as one compact menu: the current stage with its lane dot; the others one tap away. */
export function StagePicker({ stage, disabled, onMove, className }: Props) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={disabled}
          className={cn('gap-2 pr-2', className)}
          aria-label={`Stage: ${STAGE_LABELS[stage] || stage}. Change stage`}
        >
          <Dot stage={stage} />
          {STAGE_LABELS[stage] || stage}
          <ChevronDown className="text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuRadioGroup value={stage} onValueChange={(s) => s !== stage && onMove(s)}>
          {FUNNEL_STAGES.map((s) => (
            <DropdownMenuRadioItem key={s} value={s} className="gap-2">
              <Dot stage={s} />
              {STAGE_LABELS[s] || s}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

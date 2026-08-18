import { Inbox } from 'lucide-react'
import { STAGE_LABELS, STAGE_TONE } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  fitScore?: number | null
  workModel?: string | null
  outcome?: string | null
  className?: string
}

export function DrawerMetaLine({ stage, fitScore, workModel, outcome, className }: Props) {
  const toneVar = STAGE_TONE[stage] || STAGE_TONE.backlog
  const Icon = NAV_ICONS[stage] || Inbox
  const parts = [
    STAGE_LABELS[stage] || stage,
    workModel?.trim() || null,
    fitScore != null ? `${fitScore}/10` : null,
    outcome?.trim() || null,
  ].filter(Boolean)

  return (
    <p className={cn('flex items-center gap-2 text-xs text-muted-foreground', className)}>
      <Icon
        className="size-3.5 shrink-0"
        style={{ color: `var(${toneVar})` }}
        aria-hidden
      />
      <span className="truncate">{parts.join(' · ')}</span>
    </p>
  )
}

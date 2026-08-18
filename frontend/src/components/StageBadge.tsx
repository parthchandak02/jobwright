import { Inbox } from 'lucide-react'
import { Chip } from '@/components/Chip'
import { STAGE_LABELS, STAGE_TONE } from '@/lib/api'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'

type Props = {
  stage: string
  className?: string
}

/** Lane-colored stage chip shared by board, table, and drawer. */
export function StageBadge({ stage, className }: Props) {
  const toneVar = STAGE_TONE[stage] || STAGE_TONE.backlog
  const label = STAGE_LABELS[stage] || stage
  const Icon = NAV_ICONS[stage] || Inbox

  return (
    <Chip icon={Icon} tone={toneVar} className={cn(className)}>
      {label}
    </Chip>
  )
}

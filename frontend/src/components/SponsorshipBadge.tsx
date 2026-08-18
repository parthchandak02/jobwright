import { HelpCircle, OctagonAlert, TriangleAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Chip } from '@/components/Chip'
import { cn } from '@/lib/utils'

export type SponsorshipStatus = 'required' | 'not_required' | 'not_found'

type Props = {
  status?: SponsorshipStatus | string | null
  className?: string
}

const CONFIG: Record<
  SponsorshipStatus,
  { icon: LucideIcon; title: string; iconClassName?: string; muted?: boolean }
> = {
  // Employer would need to sponsor / offers sponsorship: amber heads-up.
  required: {
    icon: TriangleAlert,
    title: 'Sponsorship: employer would need to sponsor',
    iconClassName: 'text-amber-500',
  },
  // No sponsorship, or US citizen / green card required: candidate ineligible.
  not_required: {
    icon: OctagonAlert,
    title: 'Not eligible: no sponsorship (US citizen / green card required)',
    iconClassName: 'text-destructive',
  },
  // Sponsorship not mentioned in the posting.
  not_found: {
    icon: HelpCircle,
    title: 'Sponsorship not mentioned',
    muted: true,
  },
}

export function SponsorshipBadge({ status, className }: Props) {
  const key = (status?.toLowerCase().trim() || 'not_found') as SponsorshipStatus
  const config = CONFIG[key] ?? CONFIG.not_found
  const Icon = config.icon

  return (
    <Chip
      icon={Icon}
      iconClassName={config.iconClassName}
      muted={config.muted}
      title={config.title}
      className={cn(className)}
    >
      Sponsorship
    </Chip>
  )
}

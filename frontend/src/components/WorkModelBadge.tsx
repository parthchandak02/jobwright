import { Building2, HelpCircle, Home, MapPin, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Chip } from '@/components/Chip'

type Props = {
  workModel?: string | null
  className?: string
}

const CONFIG: Record<string, { icon: LucideIcon; label: string }> = {
  remote: { icon: Home, label: 'Remote' },
  hybrid: { icon: Building2, label: 'Hybrid' },
  onsite: { icon: MapPin, label: 'Onsite' },
}

export function WorkModelBadge({ workModel, className }: Props) {
  const key = workModel?.toLowerCase().trim()
  const config = key ? CONFIG[key] : undefined

  if (!config) {
    return (
      <Chip icon={HelpCircle} muted className={className}>
        Work model: NA
      </Chip>
    )
  }

  const Icon = config.icon
  return (
    <Chip icon={Icon} className={className}>
      {config.label}
    </Chip>
  )
}

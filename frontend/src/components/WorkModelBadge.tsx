import { Building2, Home, MapPin, type LucideIcon } from 'lucide-react'
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

export function workModelLabel(workModel?: string | null): string | null {
  const key = workModel?.toLowerCase().trim()
  return key && CONFIG[key] ? CONFIG[key].label : null
}

export function WorkModelBadge({ workModel, className }: Props) {
  const config = CONFIG[workModel?.toLowerCase().trim() || '']
  if (!config) return <span className="text-caption text-muted-foreground">Not stated</span>
  return (
    <Chip icon={config.icon} className={className}>
      {config.label}
    </Chip>
  )
}

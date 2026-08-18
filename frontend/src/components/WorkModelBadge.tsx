import { Building2, Home, MapPin, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  workModel?: string | null
  className?: string
}

const CONFIG: Record<string, { icon: LucideIcon; dot: string; label: string }> = {
  remote: { icon: Home, dot: 'bg-emerald-500', label: 'Remote' },
  hybrid: { icon: Building2, dot: 'bg-sky-500', label: 'Hybrid' },
  onsite: { icon: MapPin, dot: 'bg-muted-foreground', label: 'Onsite' },
}

export function WorkModelBadge({ workModel, className }: Props) {
  const key = workModel?.toLowerCase().trim()
  const config = key ? CONFIG[key] : undefined

  const base =
    'inline-flex w-fit items-center gap-1.5 rounded-full border border-border/70 bg-background/50 px-2 py-0.5 text-[11px] font-medium'

  if (!config) {
    return (
      <span className={cn(base, 'text-muted-foreground', className)}>
        <span className="size-1.5 rounded-full bg-muted-foreground/50" aria-hidden />
        Work model: NA
      </span>
    )
  }

  const Icon = config.icon
  return (
    <span className={cn(base, 'text-foreground', className)}>
      <span className={cn('size-1.5 rounded-full', config.dot)} aria-hidden />
      <Icon className="size-3 text-muted-foreground" />
      {config.label}
    </span>
  )
}

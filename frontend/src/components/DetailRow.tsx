import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Props = {
  label: string
  value?: string | null
  className?: string
}

export function DetailRow({ label, value, className }: Props) {
  const display = value?.trim() || '—'
  return (
    <div className={cn('grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1 text-sm', className)}>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-foreground">{display}</dd>
    </div>
  )
}

export function DetailGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn('space-y-1.5', className)}>{children}</dl>
}

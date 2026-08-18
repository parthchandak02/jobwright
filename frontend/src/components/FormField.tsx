import type { ReactNode } from 'react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

type Props = {
  label: string
  htmlFor?: string
  children: ReactNode
  className?: string
}

export function FormField({ label, htmlFor, children, className }: Props) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

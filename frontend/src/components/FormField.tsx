import type { ReactNode } from 'react'
import { FieldHint } from '@/components/FieldHint'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

type Props = {
  label: string
  htmlFor?: string
  children: ReactNode
  className?: string
  hint?: string
}

export function FormField({ label, htmlFor, children, className, hint }: Props) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center gap-1">
        <Label htmlFor={htmlFor}>{label}</Label>
        {hint ? <FieldHint text={hint} /> : null}
      </div>
      {children}
    </div>
  )
}

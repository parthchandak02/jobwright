import type { ReactNode } from 'react'
import { FieldHint } from '@/components/FieldHint'
import { cn } from '@/lib/utils'

export function SectionLabel({
  children,
  className,
  hint,
}: {
  children: ReactNode
  className?: string
  hint?: string
}) {
  return (
    <div className="flex items-center gap-1">
      <h3
        className={cn(
          'text-xs font-semibold uppercase tracking-wide text-muted-foreground',
          className,
        )}
      >
        {children}
      </h3>
      {hint ? <FieldHint text={hint} /> : null}
    </div>
  )
}

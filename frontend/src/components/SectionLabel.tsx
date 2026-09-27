import type { ReactNode } from 'react'
import { FieldHint } from '@/components/FieldHint'
import { cn } from '@/lib/utils'

export { SectionHeader } from '@/components/SectionHeader'

/** Legacy compact section title (no margins). New screens use `SectionHeader`. */
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
    <div className="flex items-center gap-1.5">
      <h3 className={cn('text-subheading text-foreground', className)}>{children}</h3>
      {hint ? <FieldHint text={hint} /> : null}
    </div>
  )
}

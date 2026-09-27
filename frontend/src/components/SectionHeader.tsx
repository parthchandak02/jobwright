import type { ReactNode } from 'react'
import { FieldHint } from '@/components/FieldHint'
import { cn } from '@/lib/utils'

type Props = {
  title: ReactNode
  /** One visible sentence under the title. */
  description?: ReactNode
  /** Right slot: a SaveStatus or at most one action. */
  actions?: ReactNode
  /** Longer explanation behind a "?" popover. Prefer `description`. */
  help?: ReactNode
  as?: 'h2' | 'h3'
  id?: string
  className?: string
}

/** Section title (17/600) with optional visible description. Adds 40px (32px phone) above unless first, 16px below. */
export function SectionHeader({ title, description, actions, help, as: Heading = 'h2', id, className }: Props) {
  return (
    <div
      data-slot="section-header"
      className={cn('mb-4 flex flex-wrap items-start gap-x-4 gap-y-2 not-first:mt-section', className)}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <Heading id={id} className="text-heading text-foreground">
            {title}
          </Heading>
          {help ? <FieldHint text={help} /> : null}
        </div>
        {description ? <p className="mt-1 text-caption text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  )
}

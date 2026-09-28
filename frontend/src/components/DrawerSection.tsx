import type { ReactNode } from 'react'
import { SectionHeader } from '@/components/SectionHeader'
import { cn } from '@/lib/utils'

type Props = {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  first?: boolean
}

export function DrawerSection({ title, description, actions, children, className, first }: Props) {
  return (
    <section className={cn('py-6', !first && 'border-t border-border', className)}>
      {title ? <SectionHeader as="h3" title={title} description={description} actions={actions} /> : null}
      {children}
    </section>
  )
}

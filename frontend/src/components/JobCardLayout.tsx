import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type SlotProps = {
  children: ReactNode
  className?: string
}

export function JobCardBody({ children, className }: SlotProps) {
  return <div className={cn('job-card-stack', className)}>{children}</div>
}

export function JobCardHeader({ children, className }: SlotProps) {
  return <div className={cn('job-card-header', className)}>{children}</div>
}

export function JobCardTitle({ children }: { children: ReactNode }) {
  return <h3 className="job-card-title">{children}</h3>
}

export function JobCardSubtitle({ children, className }: SlotProps) {
  return <p className={cn('job-card-subtitle', className)}>{children}</p>
}

export function JobCardMeta({ children, className }: SlotProps) {
  return <div className={cn('job-card-meta', className)}>{children}</div>
}

export function JobCardFooter({ children, className }: SlotProps) {
  return <div className={cn('job-card-footer', className)}>{children}</div>
}

export function JobCardChips({ children, className }: SlotProps) {
  return <div className={cn('job-card-chips', className)}>{children}</div>
}

export function JobCardScoreAnchor({ children, className }: SlotProps) {
  return <div className={cn('job-card-score-anchor', className)}>{children}</div>
}

export function JobCardLinkAnchor({ children, className }: SlotProps) {
  return <div className={cn('job-card-link-anchor', className)}>{children}</div>
}

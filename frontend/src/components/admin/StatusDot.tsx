import { STATUS_LABEL, type PersonStatus } from '@/components/admin/adminFormat'
import { cn } from '@/lib/utils'

const DOT: Record<PersonStatus, string> = {
  ok: 'bg-success',
  warn: 'bg-warning',
  fail: 'bg-destructive',
  none: 'border-[1.5px] border-muted-foreground',
  pending: 'border-[1.5px] border-dashed border-muted-foreground',
}

export const STATUS_TEXT: Record<PersonStatus, string> = {
  ok: 'text-muted-foreground',
  warn: 'text-foreground',
  fail: 'text-destructive',
  none: 'text-muted-foreground',
  pending: 'text-muted-foreground',
}

/** Filled = known (green ok, amber attention, red problem); hollow = unknown; dashed = setup pending. */
export function StatusDot({ status, label, className }: { status: PersonStatus; label?: string; className?: string }) {
  return (
    <span
      className={cn('inline-block size-2.5 shrink-0 rounded-full', DOT[status], className)}
      role="img"
      aria-label={label ?? STATUS_LABEL[status]}
      title={label ?? STATUS_LABEL[status]}
    />
  )
}

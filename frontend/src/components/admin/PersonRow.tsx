import { ChevronDown } from 'lucide-react'
import { PersonSettings, type PersonActions, type SaveState } from '@/components/admin/PersonSettings'
import { STATUS_LABEL, chatName, STATUS_TONE, fmtCost, fmtTime, fmtTopN, personStatus, type PersonStatus } from '@/components/admin/adminFormat'
import type { AdminOverviewUser } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = PersonActions & {
  user: AdminOverviewUser
  expanded: boolean
  onToggle: () => void
  saveState: SaveState
}

export function StatusDot({ status }: { status: PersonStatus }) {
  const tone = STATUS_TONE[status]
  return (
    <span
      className={cn(
        'inline-block size-2.5 shrink-0 rounded-full border-2',
        status === 'pending' ? 'border-muted-foreground/60 bg-transparent' : !tone && 'border-transparent bg-muted-foreground/40',
      )}
      style={tone ? { backgroundColor: `var(${tone})`, borderColor: `var(${tone})` } : undefined}
      title={STATUS_LABEL[status]}
      aria-hidden
    />
  )
}

export function PersonRow({ user: u, expanded, onToggle, saveState, ...actions }: Props) {
  const status = personStatus(u)
  const panelId = `person-${u.user_id}`
  const chat = chatName(u.whatsapp?.name) || (u.whatsapp?.target ? 'Chat set' : null)
  const pending = !u.setup_complete

  return (
    <li className={cn('min-w-0', expanded && 'bg-accent/20')}>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-left transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-ring/50 lg:h-11 lg:flex-nowrap lg:py-0"
      >
        <StatusDot status={status} />
        <span className="flex min-w-0 flex-1 items-baseline gap-2 lg:w-44 lg:flex-none">
          <span className="truncate text-sm font-medium">{u.name}</span>
          <span className={cn('shrink-0 text-xs text-muted-foreground', status === 'ok' ? 'sr-only' : 'lg:sr-only')}>
            {STATUS_LABEL[status]}
          </span>
        </span>
        <ChevronDown
          className={cn(
            'size-4 shrink-0 text-muted-foreground transition-transform duration-200 lg:order-last',
            expanded && 'rotate-180',
          )}
          aria-hidden
        />
        <span className="order-last flex min-w-0 basis-full flex-wrap gap-x-3 gap-y-0.5 pl-5.5 text-xs text-muted-foreground tabular-nums lg:order-none lg:grid lg:flex-1 lg:basis-auto lg:grid-cols-[minmax(0,1fr)_4.5rem_2rem_3.5rem_7.5rem_4rem] lg:items-center lg:pl-0">
          <span className={cn('min-w-0 truncate', chat && 'text-foreground/80')}>{chat || 'No chat'}</span>
          {pending ? (
            <span className="lg:col-span-4">Setup pending</span>
          ) : (
            <>
              <span>{fmtTime(u.hour, u.minute)}</span>
              <span>{u.notify_threshold != null ? `${u.notify_threshold}+` : '—'}</span>
              <span>{fmtTopN(u.brief_top_n)}</span>
              <span>{`${u.counts?.new_7d ?? 0} new this week`}</span>
            </>
          )}
          <span className="lg:text-right" title="AI usage, last 30 days">
            {fmtCost(u.cost_30d)}
          </span>
        </span>
      </button>
      {expanded ? <PersonSettings id={panelId} user={u} saveState={saveState} {...actions} /> : null}
    </li>
  )
}

export function PersonRowSkeleton() {
  return (
    <li className="flex h-11 items-center gap-3 px-3" aria-hidden>
      <span className="size-2.5 animate-pulse rounded-full bg-muted" />
      <span className="h-3 w-32 animate-pulse rounded bg-muted" />
      <span className="ml-auto h-3 w-40 animate-pulse rounded bg-muted" />
    </li>
  )
}

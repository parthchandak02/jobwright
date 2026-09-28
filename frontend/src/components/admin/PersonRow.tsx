import { ChevronDown, ChevronRight } from 'lucide-react'
import { SaveStatus } from '@/components/SaveStatus'
import {
  PersonActionBar,
  PersonHealth,
  PersonSettings,
  type PersonActions,
  type SaveState,
} from '@/components/admin/PersonSettings'
import { STATUS_TEXT, StatusDot } from '@/components/admin/StatusDot'
import {
  STATUS_LABEL,
  chatDisplay,
  fmtTime,
  fmtTopN,
  fmtUsage,
  personStatus,
  usageTitle,
} from '@/components/admin/adminFormat'
import { Skeleton } from '@/components/ui/skeleton'
import type { AdminOverviewUser } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = PersonActions & {
  user: AdminOverviewUser
  expanded: boolean
  onToggle: () => void
  saveState: SaveState
  savedAt?: number | null
  /** `table` = desktop grid row with inline panel; `card` = two-line phone row that opens a sheet. */
  variant: 'table' | 'card'
}

export const PEOPLE_GRID =
  'grid grid-cols-[minmax(0,1.25fr)_minmax(0,1.2fr)_5.25rem_3.75rem_4.25rem_4.5rem_6.5rem_1rem] items-center gap-x-4'

export function PeopleHeader() {
  return (
    <div
      className={cn(PEOPLE_GRID, 'border-b px-5 py-2.5 text-caption text-muted-foreground')}
      aria-hidden
    >
      <span>Person</span>
      <span>WhatsApp chat</span>
      <span>Sends at</span>
      <span>Cutoff</span>
      <span>List</span>
      <span className="text-right">New (7d)</span>
      <span className="text-right">AI use (30d)</span>
      <span />
    </div>
  )
}

function ChatText({ u }: { u: AdminOverviewUser }) {
  const chat = chatDisplay(u.whatsapp?.name, u.whatsapp?.target, u.whatsapp?.type)
  return (
    <span className={cn('min-w-0 truncate', (!chat || chat.unnamed) && 'text-muted-foreground')}>
      {chat?.label ?? 'No chat yet'}
    </span>
  )
}

function secondLine(u: AdminOverviewUser): { text: string; className: string } {
  const status = personStatus(u)
  if (status !== 'ok' && status !== 'none') return { text: STATUS_LABEL[status], className: STATUS_TEXT[status] }
  return { text: u.emails[0] ?? 'No login email', className: 'text-muted-foreground' }
}

function rowLabel(u: AdminOverviewUser): string {
  const status = STATUS_LABEL[personStatus(u)]
  const chat = chatDisplay(u.whatsapp?.name, u.whatsapp?.target, u.whatsapp?.type)?.label ?? 'no chat yet'
  const parts = [u.name, status, `chat ${chat}`]
  if (u.setup_complete) {
    parts.push(
      `sends at ${fmtTime(u.hour, u.minute)}`,
      `cutoff ${u.notify_threshold ?? 'not set'}+`,
      `list ${fmtTopN(u.brief_top_n)}`,
      `${u.counts?.new_7d ?? 0} new this week`,
    )
  }
  parts.push(`AI use ${fmtUsage(u.cost_30d)}`)
  return parts.join(', ')
}

export function PersonRow(props: Props) {
  return props.variant === 'table' ? <TableRow {...props} /> : <CardRow {...props} />
}

function TableRow({ user: u, expanded, onToggle, saveState, savedAt, onPatch, ...actions }: Props) {
  const status = personStatus(u)
  const panelId = `person-${u.user_id}`
  const pending = !u.setup_complete
  const line2 = secondLine(u)

  return (
    <li className="min-w-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        aria-label={rowLabel(u)}
        onClick={onToggle}
        className={cn(
          PEOPLE_GRID,
          'w-full min-w-0 px-5 py-2.5 text-left text-body tabular-nums transition-colors duration-(--dur-1) hover:bg-surface-muted',
          expanded && 'bg-surface-muted',
        )}
      >
        <span className="flex min-w-0 items-center gap-3">
          <StatusDot status={status} />
          <span className="min-w-0">
            <span className="block truncate text-label">{u.name}</span>
            <span className={cn('block truncate text-caption', line2.className)}>{line2.text}</span>
          </span>
        </span>
        <ChatText u={u} />
        {pending ? (
          <span className="col-span-4 text-muted-foreground">Waiting for setup</span>
        ) : (
          <>
            <span>{fmtTime(u.hour, u.minute)}</span>
            <span>{u.notify_threshold != null ? `${u.notify_threshold}+` : '—'}</span>
            <span>{fmtTopN(u.brief_top_n)}</span>
            <span className="text-right">{u.counts?.new_7d ?? 0}</span>
          </>
        )}
        <span className="truncate text-right text-muted-foreground" title={usageTitle(u.cost_30d)}>
          {fmtUsage(u.cost_30d)}
        </span>
        <ChevronDown
          className={cn(
            'size-4 justify-self-end text-muted-foreground transition-transform duration-(--dur-2)',
            expanded && 'rotate-180',
          )}
          aria-hidden
        />
      </button>
      {expanded ? (
        <div id={panelId} className="border-t px-5 pt-5 pb-4">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
            <div className="min-w-0 flex-1">
              <PersonHealth user={u} />
            </div>
            <SaveStatus state={saveState ?? 'idle'} savedAt={savedAt} />
          </div>
          <PersonSettings id={panelId} user={u} onPatch={onPatch} onOpen={actions.onOpen} />
          <PersonActionBar user={u} {...actions} className="mt-8 border-t pt-4" />
        </div>
      ) : null}
    </li>
  )
}

function CardRow({ user: u, onToggle }: Props) {
  const status = personStatus(u)
  const pending = !u.setup_complete
  const statusText = status === 'ok' ? null : STATUS_LABEL[status]
  const chat = chatDisplay(u.whatsapp?.name, u.whatsapp?.target, u.whatsapp?.type)
  const meta = pending
    ? [chat?.label ?? 'No chat yet']
    : [chat?.label ?? 'No chat yet', fmtTime(u.hour, u.minute), fmtTopN(u.brief_top_n)]

  return (
    <li className="min-w-0">
      <button
        type="button"
        aria-haspopup="dialog"
        aria-label={rowLabel(u)}
        onClick={onToggle}
        className="flex min-h-16 w-full min-w-0 items-center gap-3 px-4 py-3 text-left transition-colors duration-(--dur-1) active:bg-surface-muted"
      >
        <StatusDot status={status} className="self-start mt-[0.4375rem]" />
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-baseline gap-2">
            <span className="truncate text-label">{u.name}</span>
            {statusText ? (
              <span className={cn('shrink-0 text-caption', STATUS_TEXT[status])}>{statusText}</span>
            ) : null}
          </span>
          <span className="mt-0.5 block truncate text-caption text-muted-foreground tabular-nums">
            {meta.join(' · ')}
          </span>
        </span>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </button>
    </li>
  )
}

export function PersonRowSkeleton() {
  return (
    <li className="flex min-h-16 items-center gap-3 px-4 lg:min-h-14 lg:px-5" aria-hidden>
      <Skeleton className="size-2.5 rounded-full" />
      <div className="space-y-1.5">
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3 w-44" />
      </div>
      <Skeleton className="ml-auto hidden h-3 w-72 lg:block" />
    </li>
  )
}

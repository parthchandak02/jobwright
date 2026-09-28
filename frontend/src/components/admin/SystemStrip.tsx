import { useId, useState, type ReactNode } from 'react'
import { ChevronDown, Loader2, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { SectionHeader } from '@/components/SectionHeader'
import { StatusDot } from '@/components/admin/StatusDot'
import type { PersonStatus } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { applyHermesChannels, syncAccess, type AdminOverview } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  overview: AdminOverview | null
  onChanged: () => void
  onPickAlerts: () => void
}

type Item = {
  key: string
  label: string
  status: PersonStatus
  state: string
  action?: ReactNode
  details?: ReactNode
}

function StatusRow({ item }: { item: Item }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <li className="px-4 py-3 md:px-5">
      <div className="flex min-h-9 items-center gap-3">
        <StatusDot status={item.status} label={item.state} />
        <div className="flex min-w-0 flex-1 flex-col gap-x-4 sm:flex-row sm:items-baseline">
          <span className="shrink-0 text-label sm:w-44">{item.label}</span>
          <span
            className={cn(
              'min-w-0 text-caption text-muted-foreground sm:truncate',
              item.status === 'fail' && 'text-destructive',
            )}
          >
            {item.state}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {item.action}
          {item.details ? (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-expanded={open}
              aria-controls={id}
              aria-label={`${open ? 'Hide' : 'Show'} details: ${item.label}`}
              onClick={() => setOpen((v) => !v)}
            >
              <ChevronDown
                className={cn('text-muted-foreground transition-transform duration-(--dur-2)', open && 'rotate-180')}
              />
            </Button>
          ) : null}
        </div>
      </div>
      {item.details && open ? (
        <div
          id={id}
          className="mt-2 space-y-2 rounded-md bg-surface-muted px-3 py-2.5 text-caption text-muted-foreground sm:ml-[1.375rem]"
        >
          {item.details}
        </div>
      ) : null}
    </li>
  )
}

function EmailList({ label, emails }: { label: string; emails: string[] }) {
  if (!emails.length) return null
  return (
    <div className="space-y-0.5">
      <p className="font-medium text-foreground">{label}</p>
      <ul>
        {emails.map((e) => (
          <li key={e} className="[overflow-wrap:anywhere]">
            {e}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function SystemStrip({ overview, onChanged, onPickAlerts }: Props) {
  const [syncing, setSyncing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [restartHint, setRestartHint] = useState(false)
  const [expanded, setExpanded] = useState<boolean | null>(null)
  const listId = useId()

  if (!overview) {
    return (
      <section aria-busy>
        <SectionHeader title="System" />
        <div className="surface space-y-3 rounded-lg px-5 py-4" aria-hidden>
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
      </section>
    )
  }

  const { bridge, access, hermes, settings, users } = overview
  const accessPending = (access.add?.length ?? 0) + (access.remove?.length ?? 0)
  const hermesPending = users.filter((u) => u.hermes_status === 'add' || u.hermes_status === 'update')
  const hermesCount = hermes.pending || hermesPending.length

  async function runSync() {
    setSyncing(true)
    try {
      const res = await syncAccess()
      if (res.error) toast.error(`Login access: ${res.error}`)
      else toast.success(res.applied ? 'Login access updated' : 'Login access already up to date')
      onChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSyncing(false)
    }
  }

  async function runApply() {
    setApplying(true)
    try {
      const r = await applyHermesChannels()
      if (r.dry_run) toast.info('Dry run: nothing written')
      else if (r.written) {
        toast.success('Saved. Restart Hermes to apply: hermes gateway restart')
        setRestartHint(true)
      } else toast.info('Already up to date')
      onChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setApplying(false)
    }
  }

  const bridgeOk = bridge === 'connected'

  const items: Item[] = [
    {
      key: 'bridge',
      label: 'WhatsApp bridge',
      status: bridgeOk ? 'ok' : 'fail',
      state: bridgeOk ? 'Connected' : `Not connected${bridge && bridge !== 'down' ? ` (${bridge})` : ''}`,
      details: bridgeOk ? undefined : (
        <p>Daily lists and test messages can't be sent until the bridge reconnects. Check Hermes on the host.</p>
      ),
    },
    {
      key: 'access',
      label: 'Login access',
      status: !access.configured ? 'none' : access.error ? 'fail' : access.in_sync ? 'ok' : 'warn',
      state: !access.configured
        ? 'Not connected to Cloudflare'
        : access.error
          ? "Couldn't check Cloudflare"
          : access.in_sync
            ? 'Everyone can log in'
            : `${accessPending} change${accessPending === 1 ? '' : 's'} to sync`,
      action:
        access.configured && (!access.in_sync || access.error) ? (
          <Button size="sm" variant="secondary" onClick={() => void runSync()} disabled={syncing}>
            {syncing ? <Loader2 className="animate-spin" /> : <RefreshCw />} Sync
          </Button>
        ) : null,
      details: !access.configured ? (
        <p>
          Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in .env to sync logins automatically. Until then, add
          emails in Zero Trust → Access → Applications → jobwright.
        </p>
      ) : (
        <>
          <p>
            The “jobwright users” allow policy is kept equal to every login email plus admins. Other policies are never
            changed.
          </p>
          {access.error ? <p className="text-destructive [overflow-wrap:anywhere]">{access.error}</p> : null}
          <EmailList label="Will be allowed" emails={access.add ?? []} />
          <EmailList label="Will be removed" emails={access.remove ?? []} />
        </>
      ),
    },
    {
      key: 'hermes',
      label: 'Group instructions',
      status: hermes.error ? 'fail' : hermes.changed ? 'warn' : 'ok',
      state: hermes.error
        ? "Couldn't read the Hermes config"
        : hermes.changed
          ? `${hermesCount || 'Some'} ${hermesCount === 1 ? 'needs' : 'need'} an update`
          : restartHint
            ? 'Saved. Restart Hermes to apply'
            : 'Up to date',
      action: hermes.changed ? (
        <Button size="sm" variant="secondary" onClick={() => void runApply()} disabled={applying}>
          {applying ? <Loader2 className="animate-spin" /> : null} Apply
        </Button>
      ) : null,
      details: (
        <>
          <p>
            Each person’s WhatsApp group gets its own Hermes instructions (only that person’s data). After applying,
            restart Hermes: <code className="text-foreground">hermes gateway restart</code>
          </p>
          {hermes.error ? <p className="text-destructive [overflow-wrap:anywhere]">{hermes.error}</p> : null}
          {hermesPending.length ? (
            <ul className="space-y-0.5">
              {hermesPending.map((u) => (
                <li key={u.user_id}>
                  <span className="text-foreground">{u.name}</span> ·{' '}
                  {u.hermes_status === 'add' ? 'not set up' : 'needs update'}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ),
    },
    {
      key: 'alerts',
      label: 'Alerts chat',
      status: settings.ops_target ? 'ok' : 'warn',
      state: settings.ops_target ? `Alerts go to ${settings.ops_target_name || 'a chat'}` : 'Not set. Problems go nowhere',
      action: settings.ops_target ? null : (
        <Button size="sm" variant="secondary" onClick={onPickAlerts}>
          Pick
        </Button>
      ),
    },
  ]

  const problems = items.filter((i) => i.status === 'warn' || i.status === 'fail').length
  const open = expanded ?? problems > 0
  const summary = problems ? `${problems} need${problems === 1 ? 's' : ''} attention` : 'All systems working'

  return (
    <section>
      <SectionHeader title="System" />
      <div className="surface overflow-hidden rounded-lg">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setExpanded(!open)}
          className="flex min-h-12 w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-(--dur-1) hover:bg-surface-muted md:px-5"
        >
          <StatusDot status={problems ? (items.some((i) => i.status === 'fail') ? 'fail' : 'warn') : 'ok'} label={summary} />
          <span className="min-w-0 flex-1 text-label">{summary}</span>
          <span className="text-caption text-muted-foreground">{open ? 'Hide' : 'Details'}</span>
          <ChevronDown
            className={cn(
              'size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-2)',
              open && 'rotate-180',
            )}
            aria-hidden
          />
        </button>
        {open ? (
          <ul id={listId} className="divide-y border-t" aria-label="System status">
            {items.map((item) => (
              <StatusRow key={item.key} item={item} />
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  )
}

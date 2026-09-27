import { useState, type ReactNode } from 'react'
import { Bell, CloudCog, Loader2, MessageSquare, RefreshCw, Smartphone } from 'lucide-react'
import { toast } from 'sonner'
import { Chip } from '@/components/Chip'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { applyHermesChannels, syncAccess, type AdminOverview } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  overview: AdminOverview | null
  onChanged: () => void
}

function StatusItem({
  chip,
  details,
  action,
}: {
  chip: ReactNode
  details?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      {details ? (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="min-w-0 rounded-full focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              {chip}
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="space-y-2 text-xs">
            {details}
          </PopoverContent>
        </Popover>
      ) : (
        chip
      )}
      {action}
    </div>
  )
}

function EmailList({ label, emails }: { label: string; emails: string[] }) {
  if (!emails.length) return null
  return (
    <div className="space-y-1">
      <p className="font-medium">{label}</p>
      <ul className="space-y-0.5 text-muted-foreground">
        {emails.map((e) => (
          <li key={e} className="truncate">
            {e}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function SystemStrip({ overview, onChanged }: Props) {
  const [syncing, setSyncing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [restartHint, setRestartHint] = useState(false)

  if (!overview) {
    return (
      <div className="flex flex-wrap gap-2" aria-hidden>
        {[28, 32, 36, 24].map((w) => (
          <span key={w} className="h-6 animate-pulse rounded-full bg-muted" style={{ width: `${w * 0.25}rem` }} />
        ))}
      </div>
    )
  }

  const { bridge, access, hermes, settings, users } = overview
  const accessPending = (access.add?.length ?? 0) + (access.remove?.length ?? 0)
  const hermesPending = users.filter((u) => u.hermes_status === 'add' || u.hermes_status === 'update')

  async function runSync() {
    setSyncing(true)
    try {
      const res = await syncAccess()
      if (res.error) toast.error(`Cloudflare Access: ${res.error}`)
      else toast.success(res.applied ? 'Cloudflare Access updated' : 'Cloudflare Access already in sync')
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

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2" role="group" aria-label="System status">
      <StatusItem
        chip={
          <Chip icon={Smartphone} tone={bridgeOk ? '--stage-offer' : '--destructive'}>
            {bridgeOk ? 'WhatsApp connected' : `WhatsApp ${bridge || 'down'}`}
          </Chip>
        }
      />

      <StatusItem
        chip={
          !access.configured ? (
            <Chip icon={CloudCog} muted>
              Access not configured
            </Chip>
          ) : access.error ? (
            <Chip icon={CloudCog} tone="--destructive">
              Access error
            </Chip>
          ) : access.in_sync ? (
            <Chip icon={CloudCog} tone="--stage-offer">
              Access in sync
            </Chip>
          ) : (
            <Chip icon={CloudCog} tone="--stage-in-progress">
              {`Access: ${accessPending} pending`}
            </Chip>
          )
        }
        details={
          !access.configured ? (
            <p className="text-muted-foreground">
              Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in .env to sync logins automatically. Until then, add
              emails in Zero Trust → Access → Applications → jobwright.
            </p>
          ) : (
            <>
              <p className="text-muted-foreground">
                The “jobwright users” allow policy is kept equal to every login email plus admins. Other policies are
                never changed.
              </p>
              {access.error ? <p className="text-destructive [overflow-wrap:anywhere]">{access.error}</p> : null}
              <EmailList label="Will be allowed" emails={access.add ?? []} />
              <EmailList label="Will be removed" emails={access.remove ?? []} />
            </>
          )
        }
        action={
          access.configured && (!access.in_sync || access.error) ? (
            <Button size="xs" variant="outline" onClick={() => void runSync()} disabled={syncing}>
              {syncing ? <Loader2 className="animate-spin" /> : <RefreshCw />} Sync
            </Button>
          ) : null
        }
      />

      <StatusItem
        chip={
          hermes.error ? (
            <Chip icon={MessageSquare} tone="--destructive">
              Group instructions error
            </Chip>
          ) : hermes.changed ? (
            <Chip icon={MessageSquare} tone="--stage-in-progress">
              {`Group instructions: ${hermes.pending || hermesPending.length} need update`}
            </Chip>
          ) : (
            <Chip icon={MessageSquare} tone="--stage-offer">
              Group instructions up to date
            </Chip>
          )
        }
        details={
          <>
            <p className="text-muted-foreground">
              Each person’s WhatsApp group gets its own Hermes instructions (only that person’s data). After applying,
              restart Hermes: <code>hermes gateway restart</code>
            </p>
            {hermes.error ? <p className="text-destructive [overflow-wrap:anywhere]">{hermes.error}</p> : null}
            {hermesPending.length ? (
              <ul className="space-y-0.5">
                {hermesPending.map((u) => (
                  <li key={u.user_id}>
                    {u.name} · <span className="text-muted-foreground">{u.hermes_status === 'add' ? 'not set up' : 'needs update'}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        }
        action={
          hermes.changed ? (
            <>
              <Button size="xs" variant="outline" onClick={() => void runApply()} disabled={applying}>
                {applying ? <Loader2 className="animate-spin" /> : null} Apply
              </Button>
              <span className="hidden text-xs text-muted-foreground sm:inline">then restart Hermes</span>
            </>
          ) : restartHint ? (
            <span className="text-xs text-muted-foreground">Restart Hermes to apply</span>
          ) : null
        }
      />

      <StatusItem
        chip={
          settings.ops_target ? (
            <Chip icon={Bell} title={settings.ops_target}>
              {`Alerts → ${settings.ops_target_name || 'set'}`}
            </Chip>
          ) : (
            <Chip icon={Bell} tone="--stage-in-progress">
              No alert chat
            </Chip>
          )
        }
      />
    </div>
  )
}

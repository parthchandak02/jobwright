import { useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { ConfirmAction } from '@/components/profile/ConfirmAction'
import { SectionHeader } from '@/components/SectionHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getConnector,
  putApplyVia,
  revokeConnectedClaude,
  type ApplyVia,
  type ConnectedClaude,
  type ConnectorStatus,
} from '@/lib/api'
import { APPLY_VIA_OPTIONS, describeClient } from '@/lib/connector'
import { errorMessage } from '@/lib/utils'

const PROMPTS = [
  'What is new in jobwright today?',
  'Apply to today’s jobwright picks with Claude in Chrome. Ask me before anything you are unsure of.',
  'Tailor my resume for the best job in jobwright and save it.',
  'Which jobwright questions am I missing answers for? Ask me them one by one.',
]

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="secondary"
      size="sm"
      aria-label={label}
      onClick={() => {
        void navigator.clipboard?.writeText(text)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? <Check /> : <Copy />}
      {copied ? 'Copied' : 'Copy'}
    </Button>
  )
}

/** Settings → Claude: connect the person's own Claude, see and disconnect connected apps, choose who applies. */
export function ClaudeTab() {
  const [data, setData] = useState<ConnectorStatus | null>(null)
  const [revoking, setRevoking] = useState<ConnectedClaude | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getConnector()
      .then(setData)
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  if (!data) {
    return (
      <div className="space-y-field" aria-busy aria-label="Loading Claude settings">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  async function chooseVia(next: ApplyVia) {
    if (!data || next === data.apply_via) return
    setSaving(true)
    try {
      setData(await putApplyVia(next))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const options = APPLY_VIA_OPTIONS.filter((o) => o.value !== 'server' || data.can_choose_server || data.apply_via === 'server')
  const via = APPLY_VIA_OPTIONS.find((o) => o.value === data.apply_via)

  return (
    <div>
      <SectionHeader
        title="Connect your Claude"
        description="Use jobwright from your own Claude (claude.ai, the desktop app or your phone). It can read your jobs, tailor your resume and apply for you in your own browser."
      />
      {!data.enabled ? (
        <p className="mb-4 text-body text-muted-foreground">
          <Badge variant="warning">Off</Badge> The connector is not running on this server yet. Ask the operator.
        </p>
      ) : null}
      <ol className="list-decimal space-y-2 pl-5 text-body text-muted-foreground">
        <li>In Claude, open Settings, then Connectors, then Add custom connector.</li>
        <li>
          Name it jobwright and paste this address:
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="min-w-0 rounded-md border border-border bg-surface-muted px-3 py-2 text-label break-all text-foreground">
              {data.url}
            </code>
            <CopyButton text={data.url} label="Copy the connector address" />
          </div>
        </li>
        <li>Claude opens a jobwright page: sign in as you do here, check what it may do, and press Allow.</li>
        <li>For applying, turn on Claude in Chrome so Claude can fill forms in your own browser.</li>
      </ol>

      <SectionHeader title="Try asking" description="Copy one, then paste it into a new chat." />
      <ul className="space-y-2">
        {PROMPTS.map((p) => (
          <li key={p} className="flex items-start gap-3 rounded-lg border border-border px-4 py-3">
            <span className="min-w-0 flex-1 text-body text-foreground">{p}</span>
            <CopyButton text={p} label={`Copy: ${p}`} />
          </li>
        ))}
      </ul>

      <SectionHeader
        title="Connected Claude apps"
        description="Each one can act only on this profile. Disconnecting ends its access right away."
      />
      {data.clients.length ? (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {data.clients.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-label text-foreground">
                  {c.client_name} <span className="text-muted-foreground">({c.email})</span>
                </p>
                <p className="mt-0.5 text-body text-muted-foreground">{describeClient(c)}</p>
              </div>
              <Button variant="destructive-ghost" size="sm" onClick={() => setRevoking(c)}>
                Disconnect
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-muted-foreground">No Claude is connected yet.</p>
      )}

      <SectionHeader
        title="Who sends applications"
        description={via?.hint ?? ''}
      />
      <Segmented
        aria-label="Who sends applications"
        value={data.apply_via}
        disabled={saving}
        onValueChange={(v) => void chooseVia(v)}
        options={options.map((o) => ({
          value: o.value,
          label: o.label,
          disabled: o.value === 'server' && !data.can_choose_server,
        }))}
      />
      {data.apply_via === 'connector' ? (
        <p className="mt-3 text-body text-muted-foreground">
          {data.apply_enabled
            ? 'Claude may press Submit on jobs that meet your minimum score. Everything else it fills, then you submit.'
            : 'Claude fills each form and stops on the review page; you check it and press Submit yourself.'}{' '}
          Your daily limit, saved answers and the “skip” replies to your picks still apply.
        </p>
      ) : null}

      <ConfirmAction
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title="Disconnect this Claude?"
        description={`${revoking?.client_name ?? 'Claude'} will lose access to jobwright right away. You can connect it again later.`}
        confirmLabel="Disconnect"
        destructive
        onConfirm={async () => {
          if (!revoking) return
          try {
            setData(await revokeConnectedClaude(revoking.id))
            toast.success('Disconnected')
          } catch (e) {
            toast.error(errorMessage(e))
            throw e
          }
        }}
      />
    </div>
  )
}

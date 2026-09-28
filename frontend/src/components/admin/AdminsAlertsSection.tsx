import { useState } from 'react'
import { Bell, CalendarClock } from 'lucide-react'
import { toast } from 'sonner'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { SaveStatus, type SaveState } from '@/components/SaveStatus'
import { ChatField } from '@/components/admin/ChatField'
import { CollapsibleSection } from '@/components/admin/CollapsibleSection'
import { ConfirmDialog } from '@/components/admin/ConfirmDialog'
import { reportAccessSync } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ensureWatchdog, putAdminSettings, sendOpsTest, type AdminOverview } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Settings = AdminOverview['settings']

type Props = {
  settings: Settings | null
  onSaved: (settings: Settings, refreshAccess: boolean) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  id?: string
}

export function AdminsAlertsSection({ settings, onSaved, open, onOpenChange, id }: Props) {
  const [save, setSave] = useState<{ state: SaveState; at: number | null }>({ state: 'idle', at: null })
  const [confirmTest, setConfirmTest] = useState(false)

  async function persist(patch: Partial<Pick<Settings, 'admins' | 'ops_target'>>) {
    if (!settings) return
    setSave((s) => ({ ...s, state: 'saving' }))
    try {
      const res = await putAdminSettings(patch)
      onSaved(
        {
          admins: res.admins,
          ops_target: res.ops_target,
          ops_target_name: patch.ops_target !== undefined ? null : settings.ops_target_name,
        },
        !!patch.admins || patch.ops_target !== undefined,
      )
      setSave({ state: 'saved', at: Date.now() })
      reportAccessSync(res.access_sync)
    } catch (e) {
      setSave((s) => ({ ...s, state: 'error' }))
      toast.error(errorMessage(e))
    }
  }

  const alertsTo = settings?.ops_target_name || (settings?.ops_target ? 'a chat' : 'nobody')

  return (
    <CollapsibleSection
      id={id}
      title="Admins and alerts"
      open={open}
      onOpenChange={onOpenChange}
      summary={
        settings
          ? `${settings.admins.length} admin${settings.admins.length === 1 ? '' : 's'} · alerts go to ${alertsTo}`
          : undefined
      }
    >
      {!settings ? (
        <div className="space-y-3" aria-hidden>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <div className="space-y-field">
          {save.state !== 'idle' ? (
            <div className="-mt-2 flex justify-end">
              <SaveStatus state={save.state} savedAt={save.at} />
            </div>
          ) : null}
          <div className="grid gap-x-10 gap-y-field lg:grid-cols-2">
            <FormField label="Admin emails" hint="Admins can open and manage every profile.">
              <ChipInput
                values={settings.admins}
                onChange={(admins) => void persist({ admins })}
                placeholder="Add an admin email"
                addLabel="Add admin"
              />
            </FormField>
            <FormField
              label="Operator alerts go to"
              htmlFor="ops-target"
              hint="Failed searches, empty lists, WhatsApp delivery failures and missed runs."
            >
              <ChatField
                id="ops-target"
                value={settings.ops_target}
                name={settings.ops_target_name}
                emptyLabel="Not set"
                onCommit={(ops_target) => {
                  if (ops_target !== settings.ops_target) void persist({ ops_target })
                }}
              />
            </FormField>
          </div>
          <div className="flex flex-wrap gap-2 border-t pt-4">
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                void ensureWatchdog()
                  .then((r) =>
                    r.ok ? toast.success('Daily health check scheduled (8:30 AM)') : toast.error(r.error || 'Failed'),
                  )
                  .catch((e) => toast.error(errorMessage(e)))
              }
            >
              <CalendarClock /> Schedule daily health check
            </Button>
            <Button size="sm" variant="secondary" disabled={!settings.ops_target} onClick={() => setConfirmTest(true)}>
              <Bell /> Send test alert
            </Button>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={confirmTest}
        onOpenChange={setConfirmTest}
        title="Send a test alert?"
        description={`This posts a test alert in ${alertsTo}. Anyone in that chat will see it.`}
        confirmLabel="Send test alert"
        icon={<Bell />}
        onConfirm={() =>
          sendOpsTest()
            .then((r) => toast.info(r.result))
            .catch((e) => {
              toast.error(errorMessage(e))
              throw e
            })
        }
      />
    </CollapsibleSection>
  )
}

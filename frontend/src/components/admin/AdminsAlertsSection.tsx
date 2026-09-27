import { Bell, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { ChatField } from '@/components/admin/ChatField'
import { CollapsibleSection } from '@/components/admin/CollapsibleSection'
import { reportAccessSync } from '@/components/admin/adminFormat'
import { Button } from '@/components/ui/button'
import { ensureWatchdog, putAdminSettings, sendOpsTest, type AdminOverview } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Settings = AdminOverview['settings']

type Props = {
  settings: Settings | null
  onSaved: (settings: Settings, refreshAccess: boolean) => void
}

export function AdminsAlertsSection({ settings, onSaved }: Props) {
  async function save(patch: Partial<Pick<Settings, 'admins' | 'ops_target'>>) {
    if (!settings) return
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
      toast.success('Saved')
      reportAccessSync(res.access_sync)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <CollapsibleSection
      title="Admins and alerts"
      summary={
        settings
          ? `${settings.admins.length} admin${settings.admins.length === 1 ? '' : 's'} · alerts to ${settings.ops_target_name || (settings.ops_target ? 'a chat' : 'nobody')}`
          : undefined
      }
    >
      {!settings ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <FormField label="Admin emails" hint="Admins can open and manage every profile.">
            <ChipInput
              values={settings.admins}
              onChange={(admins) => void save({ admins })}
              placeholder="admin@example.com"
              addLabel="Add admin"
            />
          </FormField>
          <div className="space-y-3">
            <FormField
              label="Operator alerts go to"
              hint="Where problems go: failed searches, empty lists, WhatsApp delivery failures, missed runs."
            >
              <ChatField
                value={settings.ops_target}
                name={settings.ops_target_name}
                emptyLabel="Not set"
                onCommit={(ops_target) => {
                  if (ops_target !== settings.ops_target) void save({ ops_target })
                }}
              />
            </FormField>
            <div className="flex flex-wrap gap-1.5">
              <Button
                size="xs"
                variant="outline"
                onClick={() =>
                  void ensureWatchdog()
                    .then((r) =>
                      r.ok ? toast.success('Daily health check scheduled (8:30 AM)') : toast.error(r.error || 'Failed'),
                    )
                    .catch((e) => toast.error(errorMessage(e)))
                }
              >
                <Plus /> Schedule daily health check
              </Button>
              <Button
                size="xs"
                variant="outline"
                disabled={!settings.ops_target}
                onClick={() =>
                  void sendOpsTest()
                    .then((r) => toast.info(r.result))
                    .catch((e) => toast.error(errorMessage(e)))
                }
              >
                <Bell /> Send test alert
              </Button>
            </div>
          </div>
        </div>
      )}
    </CollapsibleSection>
  )
}

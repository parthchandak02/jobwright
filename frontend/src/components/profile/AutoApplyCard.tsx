import { useState } from 'react'
import { PauseCircle } from 'lucide-react'
import { toast } from 'sonner'
import { ConfirmAction } from '@/components/profile/ConfirmAction'
import { Switch } from '@/components/ui/switch'
import { putConnectorSettings, type ConnectorStatus } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

/**
 * The one place to turn auto-apply on or off, and to let Claude press Submit itself.
 * Each person decides both (Parth, 2026-11-09). Limits (score, daily cap, saved answers only) stay.
 */
export function AutoApplyCard({ data, onChange }: { data: ConnectorStatus; onChange: (d: ConnectorStatus) => void }) {
  const [saving, setSaving] = useState(false)
  const [confirmSend, setConfirmSend] = useState(false)
  const on = data.apply_via !== 'off'
  const viaServer = data.apply_via === 'server'

  async function save(body: Parameters<typeof putConnectorSettings>[0], done: string) {
    setSaving(true)
    try {
      onChange(await putConnectorSettings(body))
      toast.success(done)
    } catch (e) {
      toast.error(errorMessage(e))
      throw e
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-labelledby="auto-apply-title" className="mb-section">
      <ul className="surface divide-y divide-border rounded-lg border">
        <li className="flex items-center gap-4 px-4 py-3.5">
          <label htmlFor="auto-apply" className="min-w-0 flex-1 cursor-pointer">
            <span id="auto-apply-title" className="block text-label text-foreground">
              Auto-apply
            </span>
            <span className="mt-0.5 block text-caption text-muted-foreground">
              {!on
                ? 'Off. Your Claude won’t apply to anything.'
                : viaServer
                  ? 'On, run by jobwright (set by an admin).'
                  : !data.clients.length
                    ? 'On once you connect your Claude (step 1 below).'
                    : `Your Claude applies to your picks: ${data.apply_min_score}+ only, up to ${data.apply_daily_cap} a day.`}
            </span>
          </label>
          <Switch
            id="auto-apply"
            checked={on}
            disabled={saving}
            onCheckedChange={(v) =>
              void save({ apply_via: v ? 'connector' : 'off' }, v ? 'Auto-apply is on' : 'Auto-apply is off').catch(
                () => {},
              )
            }
          />
        </li>
        {on ? (
          <li className="flex items-center gap-4 px-4 py-3.5">
            <label htmlFor="auto-send" className="min-w-0 flex-1 cursor-pointer">
              <span className="block text-label text-foreground">Send without asking me</span>
              <span className="mt-0.5 block text-caption text-muted-foreground">
                {data.apply_enabled
                  ? `Claude presses Submit itself on ${data.apply_min_score}+ jobs.`
                  : 'Claude fills each form and stops before Submit. You send it.'}
              </span>
            </label>
            <Switch
              id="auto-send"
              checked={data.apply_enabled}
              disabled={saving}
              onCheckedChange={(v) =>
                v
                  ? setConfirmSend(true)
                  : void save({ apply_enabled: false }, 'Claude will stop before Submit').catch(() => {})
              }
            />
          </li>
        ) : null}
        {on && data.apply_paused ? (
          <li className="flex items-center gap-2 px-4 py-3 text-caption text-warning">
            <PauseCircle className="size-4 shrink-0" aria-hidden />
            Paused for now (two failed tries in a row, or stopped by an admin).
          </li>
        ) : null}
      </ul>
      <ConfirmAction
        open={confirmSend}
        onOpenChange={setConfirmSend}
        title="Let Claude send applications?"
        description={`Claude will press Submit on jobs scoring ${data.apply_min_score}+, up to ${data.apply_daily_cap} a day, using only your saved answers and your resume. Each one shows on your board as Applied, with the confirmation. You can turn this off any time.`}
        confirmLabel="Yes, send for me"
        onConfirm={() => save({ apply_enabled: true }, 'Claude will send applications for you')}
      />
    </section>
  )
}

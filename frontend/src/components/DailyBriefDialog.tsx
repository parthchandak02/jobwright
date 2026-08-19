import { useEffect, useState } from 'react'
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { toast } from 'sonner'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { notifyWhatsApp, updateProfile, type Profile } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  profile: Profile | null
  pendingCount: number
  onSaved: () => void
}

function cronToTimeValue(cron: string | undefined): string {
  const parts = (cron || '0 6 * * *').trim().split(/\s+/)
  if (parts.length !== 5 || !/^\d+$/.test(parts[0]) || !/^\d+$/.test(parts[1])) {
    return '06:00'
  }
  return `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`
}

function applyTimeToCron(cron: string | undefined, time: string): string {
  const [hourRaw, minuteRaw] = time.split(':')
  const hour = Number(hourRaw)
  const minute = Number(minuteRaw)
  const parts = (cron || '0 6 * * *').trim().split(/\s+/)
  if (parts.length !== 5) {
    return `${minute} ${hour} * * *`
  }
  parts[0] = String(minute)
  parts[1] = String(hour)
  return parts.join(' ')
}

export function DailyBriefDialog({ open, onClose, profile, pendingCount, onSaved }: Props) {
  const [time, setTime] = useState('06:00')
  const [target, setTarget] = useState('')
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!open) return
    setTime(cronToTimeValue(profile?.schedule))
    setTarget(profile?.whatsapp_target || '')
  }, [open, profile])

  const tz = profile?.timezone?.trim()
  const jobName = profile?.brief_cron_name || 'jobwright-brief-<user>'
  const pendingLabel =
    pendingCount === 0
      ? 'None waiting'
      : `${pendingCount} job${pendingCount === 1 ? '' : 's'} waiting`

  async function handleSave() {
    setSaving(true)
    try {
      const res = await updateProfile({
        schedule: applyTimeToCron(profile?.schedule, time),
        whatsapp_target: target,
      })
      if (res.cron_synced) {
        toast.success('Saved schedule and updated the Hermes cron')
      } else {
        toast.success('Saved to the user registry')
        if (res.cron_error) toast.info(res.cron_error)
      }
      onSaved()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleSend() {
    setSending(true)
    try {
      const res = await notifyWhatsApp()
      if (res.skipped) {
        toast.info(res.reason || res.message || 'No new jobs to notify')
      } else {
        toast.success(`Sent ${res.sent} jobs to WhatsApp`)
      }
      onSaved()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <WhatsAppIcon className="text-whatsapp" /> Daily WhatsApp
          </DialogTitle>
          <DialogDescription>
            Hermes runs Auto Search at this time, then sends one WhatsApp list of new jobs. Save
            writes the registry and edits the existing Hermes cron. Send now does not wait for the
            clock.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="brief-time">Time {tz ? `(${tz})` : ''}</Label>
            <Input
              id="brief-time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="brief-target">WhatsApp number</Label>
            <Input
              id="brief-target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="whatsapp:1203…@g.us"
              autoComplete="off"
            />
          </div>
          <DetailGrid>
            <DetailRow label="Waiting" value={pendingLabel} />
            <DetailRow label="Job" value={jobName} />
          </DetailGrid>
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={sending || saving}
            onClick={() => void handleSend()}
          >
            {sending ? 'Sending…' : 'Send now'}
          </Button>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="outline" onClick={onClose} disabled={saving}>
              Close
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={saving || sending || !time}
              onClick={() => void handleSave()}
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

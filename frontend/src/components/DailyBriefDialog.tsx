import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Send, Settings2 } from 'lucide-react'
import { toast } from 'sonner'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { notifyWhatsApp, type Profile } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  profile: Profile | null
  pendingCount: number
  onSaved: () => void
}

export function DailyBriefDialog({ open, onClose, profile, pendingCount, onSaved }: Props) {
  const navigate = useNavigate()
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    if (!open) setConfirming(false)
  }, [open])

  async function handleSend() {
    setSending(true)
    try {
      const res = await notifyWhatsApp()
      if (res.skipped) toast.info(res.reason || 'Nothing new to send')
      else toast.success(`Sent ${res.sent} jobs to WhatsApp`)
      onSaved()
      onClose()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSending(false)
    }
  }

  const configured = Boolean(profile?.whatsapp_target)
  const chat = profile?.whatsapp_chat_name?.trim() || (configured ? 'your WhatsApp chat' : null)
  const waiting = pendingCount ? `${pendingCount} job${pendingCount === 1 ? '' : 's'}` : 'Nothing new yet'

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <WhatsAppIcon className="size-5 text-whatsapp" /> Daily WhatsApp list
          </DialogTitle>
          <DialogDescription>
            Every day jobwright searches, scores new jobs and sends your best matches in one message.
          </DialogDescription>
        </DialogHeader>
        <DetailGrid className="rounded-lg bg-surface-muted p-4">
          <DetailRow label="Waiting to send" value={waiting} />
          <DetailRow label="Chat" value={chat || 'Not connected yet'} />
          <DetailRow
            label="Schedule"
            value={
              configured
                ? `${profile?.schedule_label || profile?.schedule}${profile?.timezone ? ` (${profile.timezone})` : ''}`
                : 'Not set up yet'
            }
          />
        </DetailGrid>
        {confirming ? (
          <div className="space-y-3 rounded-lg border border-border p-4" role="alert">
            <p className="text-body text-foreground">
              Send {pendingCount ? waiting : 'the list'} to {chat} now? Everyone in that chat will see it.
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" disabled={sending} onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={sending} onClick={() => void handleSend()}>
                {sending ? <Loader2 className="animate-spin" /> : <Send />} Yes, send now
              </Button>
            </div>
          </div>
        ) : (
          <DialogFooter className="sm:justify-between">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                onClose()
                navigate('/profile?tab=whatsapp')
              }}
            >
              <Settings2 /> Change chat or time
            </Button>
            <Button type="button" variant="secondary" disabled={!configured} onClick={() => setConfirming(true)}>
              <Send /> Send now
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

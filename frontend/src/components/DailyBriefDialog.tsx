import { useState } from 'react'
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

/** Today's WhatsApp list at a glance: what's waiting, when it goes, send it now. */
export function DailyBriefDialog({ open, onClose, profile, pendingCount, onSaved }: Props) {
  const navigate = useNavigate()
  const [sending, setSending] = useState(false)

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

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <WhatsAppIcon className="text-whatsapp" /> Daily WhatsApp list
          </DialogTitle>
          <DialogDescription>
            Every day jobwright searches, scores new jobs, and sends your best matches in one message.
          </DialogDescription>
        </DialogHeader>
        <DetailGrid>
          <DetailRow
            label="Waiting to send"
            value={pendingCount ? `${pendingCount} job${pendingCount === 1 ? '' : 's'}` : 'Nothing new yet'}
          />
          <DetailRow
            label="Schedule"
            value={
              configured
                ? `${profile?.schedule_label || profile?.schedule}${profile?.timezone ? ` (${profile.timezone})` : ''}`
                : 'Not set up yet'
            }
          />
        </DetailGrid>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              onClose()
              navigate('/profile?tab=whatsapp')
            }}
          >
            <Settings2 /> Change chat or time
          </Button>
          <Button type="button" size="sm" disabled={sending || !configured} onClick={() => void handleSend()}>
            {sending ? <Loader2 className="animate-spin" /> : <Send />} Send now
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

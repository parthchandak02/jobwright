import { useState } from 'react'
import { Loader2, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import { FormField } from '@/components/FormField'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { reportAccessSync } from '@/components/admin/adminFormat'
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
import { createProfile, patchAdminUser } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

export function AddPersonDialog({ open, onOpenChange, onCreated }: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [pickChat, setPickChat] = useState(false)
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)

  function reset() {
    setName('')
    setEmail('')
    setPickChat(false)
    setTarget('')
  }

  const valid = name.trim() && /^\S+@\S+\.\S+$/.test(email.trim())

  async function create() {
    if (!valid) return
    setBusy(true)
    try {
      const res = await createProfile(name.trim(), [email.trim().toLowerCase()])
      reportAccessSync(res.access_sync)
      if (target) {
        try {
          await patchAdminUser(res.user_id, { whatsapp_target: target })
        } catch (e) {
          toast.error(`Profile created, but the chat was not saved: ${errorMessage(e)}`)
        }
      }
      toast.success(`Added ${res.name}. They finish setup the first time they log in.`)
      reset()
      onOpenChange(false)
      onCreated()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (busy) return
        if (!v) reset()
        onOpenChange(v)
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add person</DialogTitle>
          <DialogDescription>They can log in with this email and finish setup at /welcome.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <FormField label="Name" htmlFor="add-person-name">
            <Input id="add-person-name" value={name} onChange={(e) => setName(e.target.value)} className="h-8" autoFocus />
          </FormField>
          <FormField label="Login email" htmlFor="add-person-email">
            <Input
              id="add-person-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              className="h-8"
            />
          </FormField>
          {pickChat ? (
            <FormField label="WhatsApp chat (optional)">
              <WhatsAppChatPicker hideTest value={target} onChange={setTarget} />
            </FormField>
          ) : (
            <button
              type="button"
              className="rounded text-xs text-muted-foreground underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              onClick={() => setPickChat(true)}
            >
              Pick their WhatsApp chat now (optional)
            </button>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !valid}>
              {busy ? <Loader2 className="animate-spin" /> : <UserPlus />} Add person
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

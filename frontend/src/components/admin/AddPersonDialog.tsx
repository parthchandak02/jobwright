import { useState } from 'react'
import { Loader2, UserPlus, Users } from 'lucide-react'
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
  const [tried, setTried] = useState(false)

  function reset() {
    setTried(false)
    setName('')
    setEmail('')
    setPickChat(false)
    setTarget('')
  }

  const nameError = tried && !name.trim() ? 'Add their name.' : undefined
  const emailError = tried && !/^\S+@\S+\.\S+$/.test(email.trim()) ? 'Enter a full email address.' : undefined

  async function create() {
    setTried(true)
    if (!name.trim() || !/^\S+@\S+\.\S+$/.test(email.trim())) return
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
      <DialogContent size={pickChat ? 'picker' : 'form'} className="sm:max-h-[90dvh] sm:overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add person</DialogTitle>
          <DialogDescription>They log in with this email and finish setup themselves (resume, searches, chat).</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-field"
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <FormField label="Name" htmlFor="add-person-name" error={nameError}>
            <Input
              id="add-person-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="First and last name"
              autoComplete="off"
              autoFocus
            />
          </FormField>
          <FormField
            label="Login email"
            htmlFor="add-person-email"
            hint="The email they use to sign in to jobwright."
            error={emailError}
          >
            <Input
              id="add-person-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Their sign-in email"
              autoComplete="off"
            />
          </FormField>
          {pickChat ? (
            <FormField label="WhatsApp chat" optional hint="Where their daily list is posted. You can pick it later.">
              <WhatsAppChatPicker hideTest value={target} onChange={setTarget} />
            </FormField>
          ) : (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Button type="button" size="sm" variant="secondary" onClick={() => setPickChat(true)}>
                <Users /> Choose their WhatsApp chat
              </Button>
              <span className="text-caption text-muted-foreground">Optional. You can do this later.</span>
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : <UserPlus />} Add person
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

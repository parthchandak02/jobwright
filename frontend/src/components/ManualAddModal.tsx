import { useState } from 'react'
import { toast } from 'sonner'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/FormField'
import { apiFetch, STAGE_LABELS } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

export function ManualAddModal({ open, onClose, onCreated }: Props) {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [location, setLocation] = useState('')
  const [notes, setNotes] = useState('')
  const [stage, setStage] = useState('applied')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await apiFetch('/jobs', {
        method: 'POST',
        body: JSON.stringify({
          url,
          title: title || null,
          company: company || null,
          location: location || null,
          notes: notes || null,
          funnel_stage: stage,
        }),
      })
      toast.success('Job added')
      setUrl('')
      setTitle('')
      setCompany('')
      setLocation('')
      setNotes('')
      onCreated()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add job manually</DialogTitle>
            <DialogDescription>
              Manual jobs stay out of digest and auto-apply.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <FormField label="URL *" htmlFor="url">
              <Input id="url" required value={url} onChange={(e) => setUrl(e.target.value)} />
            </FormField>
            <FormField label="Title" htmlFor="title">
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Company" htmlFor="company">
                <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} />
              </FormField>
              <FormField label="Location" htmlFor="location">
                <Input id="location" value={location} onChange={(e) => setLocation(e.target.value)} />
              </FormField>
            </div>
            <FormField label="Stage">
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(STAGE_LABELS).map(([k, v]) => (
                    <SelectItem key={k} value={k}>
                      {v}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
            <FormField label="Notes" htmlFor="notes">
              <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </FormField>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

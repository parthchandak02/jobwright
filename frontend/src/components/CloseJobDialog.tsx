import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { OUTCOMES } from '@/lib/api'
import { useState } from 'react'

type Props = {
  open: boolean
  jobTitle?: string | null
  onConfirm: (outcome: (typeof OUTCOMES)[number]) => void
  onCancel: () => void
}

export function CloseJobDialog({ open, jobTitle, onConfirm, onCancel }: Props) {
  const [outcome, setOutcome] = useState<(typeof OUTCOMES)[number]>('rejected')

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) onCancel()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Close job</DialogTitle>
          <DialogDescription>
            {jobTitle
              ? `Choose an outcome for “${jobTitle}”.`
              : 'Choose an outcome for this job.'}
          </DialogDescription>
        </DialogHeader>
        <Select
          value={outcome}
          onValueChange={(v) => setOutcome(v as (typeof OUTCOMES)[number])}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OUTCOMES.map((o) => (
              <SelectItem key={o} value={o} className="capitalize">
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={() => onConfirm(outcome)}>
            Close job
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

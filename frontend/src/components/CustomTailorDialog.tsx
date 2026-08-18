import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { tailorDefaults, type TailorInstructions } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  onStart: (instructions: TailorInstructions) => void
  starting: boolean
}

export function CustomTailorDialog({ open, onClose, onStart, starting }: Props) {
  const [resume, setResume] = useState('')
  const [cover, setCover] = useState('')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoaded(false)
    void tailorDefaults()
      .then((d) => {
        setResume(d.resume_instructions)
        setCover(d.cover_instructions)
        setLoaded(true)
      })
      .catch((e) => {
        toast.error(errorMessage(e))
        setLoaded(true)
      })
  }, [open])

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-4 overflow-hidden sm:max-w-2xl">
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle>Custom Tailor</DialogTitle>
          <DialogDescription>
            These are the Auto Tailor instructions. Edit them, then start. The base resume stays
            the source of truth.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-3 overflow-auto">
          <div className="space-y-1.5">
            <Label htmlFor="custom-tailor-resume">Resume instructions</Label>
            <Textarea
              id="custom-tailor-resume"
              value={resume}
              rows={10}
              disabled={!loaded || starting}
              onChange={(e) => setResume(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="custom-tailor-cover">Cover letter instructions</Label>
            <Textarea
              id="custom-tailor-cover"
              value={cover}
              rows={8}
              disabled={!loaded || starting}
              onChange={(e) => setCover(e.target.value)}
            />
          </div>
        </div>
        <div className="flex shrink-0 justify-end gap-2">
          <Button type="button" size="sm" variant="outline" onClick={onClose} disabled={starting}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ai"
            disabled={!loaded || starting || !resume.trim()}
            onClick={() =>
              onStart({
                resume_instructions: resume.trim(),
                cover_instructions: cover.trim(),
              })
            }
          >
            <Sparkles />
            Start tailor
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

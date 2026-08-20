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
import { tailorDefaults } from '@/lib/api'
import type { TailorScope } from '@/lib/useTailorMaterials'
import { errorMessage } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  onStart: (instructions: string) => void
  starting: boolean
  scope: TailorScope
}

const COPY: Record<
  TailorScope,
  { title: string; description: string; label: string; emptyError: string }
> = {
  resume: {
    title: 'Custom Tailor (Resume)',
    description:
      'These are the Auto Tailor resume instructions. Edit them, then start. The base resume stays the source of truth.',
    label: 'Resume instructions',
    emptyError: 'Resume instructions required',
  },
  cover: {
    title: 'Custom Tailor (Cover Letter)',
    description:
      'These are the Auto Tailor cover letter instructions. Edit them, then start. Your profile samples are not changed.',
    label: 'Cover letter instructions',
    emptyError: 'Cover letter instructions required',
  },
}

export function CustomTailorDialog({ open, onClose, onStart, starting, scope }: Props) {
  const [text, setText] = useState('')
  const [loaded, setLoaded] = useState(false)
  const copy = COPY[scope]

  useEffect(() => {
    if (!open) return
    setLoaded(false)
    void tailorDefaults()
      .then((d) => {
        setText(scope === 'resume' ? d.resume_instructions : d.cover_instructions)
        setLoaded(true)
      })
      .catch((e) => {
        toast.error(errorMessage(e))
        setLoaded(true)
      })
  }, [open, scope])

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-4 overflow-hidden sm:max-w-2xl">
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="space-y-1.5">
            <Label htmlFor={`custom-tailor-${scope}`}>{copy.label}</Label>
            <Textarea
              id={`custom-tailor-${scope}`}
              value={text}
              rows={scope === 'resume' ? 12 : 10}
              disabled={!loaded || starting}
              onChange={(e) => setText(e.target.value)}
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
            disabled={!loaded || starting || !text.trim()}
            onClick={() => onStart(text.trim())}
          >
            <Sparkles />
            Start tailor
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

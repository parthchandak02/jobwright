import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { FileCheck2, Hand, MessageCircle, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { getConnector } from '@/lib/api'
import { useMe } from '@/lib/me'

const SEEN = (userId: string) => `jobwright-seen-auto-apply-intro:${userId}`

const POINTS: [LucideIcon, string][] = [
  [Sparkles, 'Applies to your best daily picks'],
  [FileCheck2, 'Fills the form and attaches your resume'],
  [Hand, 'Stops before Submit, unless you say otherwise'],
  [MessageCircle, 'Messages you on WhatsApp when a job needs you'],
]

/** One-time "what's new" for a profile that hasn't turned auto-apply on (no Claude connected, or it's off). */
export function WhatsNewAutoApply() {
  const { me } = useMe()
  const userId = me?.active_user ?? null
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setOpen(false)
    if (!userId) return
    try {
      if (localStorage.getItem(SEEN(userId))) return
    } catch {
      return
    }
    let live = true
    void getConnector()
      .then((c) => live && setOpen(c.enabled && (c.clients.length === 0 || c.apply_via === 'off')))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [userId])

  function close() {
    if (userId) {
      try {
        localStorage.setItem(SEEN(userId), new Date().toISOString())
      } catch {
        /* private mode: it may show again */
      }
    }
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      <DialogContent size="form">
        <DialogHeader>
          <DialogTitle>New: your Claude can apply for you</DialogTitle>
          <DialogDescription>Turn it on or off any time in Settings → Claude.</DialogDescription>
        </DialogHeader>
        <ul className="space-y-3 py-1">
          {POINTS.map(([Icon, text]) => (
            <li key={text} className="flex items-center gap-3 text-body text-foreground">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-muted">
                <Icon className="size-4 text-primary" aria-hidden />
              </span>
              {text}
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button variant="ghost" onClick={close}>
            Not now
          </Button>
          <Button
            onClick={() => {
              close()
              navigate('/profile?tab=claude')
            }}
          >
            Set it up
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

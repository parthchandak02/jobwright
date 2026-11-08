import { useEffect, useState } from 'react'
import { MessagesSquare, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getConnector } from '@/lib/api'
import { dismissClaudeCard, isClaudeCardDismissed } from '@/lib/claudeGuide'
import { useMe } from '@/lib/me'
import { cn } from '@/lib/utils'

/** Board nudge to connect the person's own Claude: shown until one is connected or it is dismissed (per profile). */
export function ClaudeSetupBanner({ className }: { className?: string }) {
  const { me } = useMe()
  const userId = me?.active_user ?? null
  const [show, setShow] = useState(false)

  useEffect(() => {
    setShow(false)
    if (!userId || isClaudeCardDismissed(userId)) return
    let live = true
    void getConnector()
      .then((c) => live && setShow(c.enabled && c.clients.length === 0))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [userId])

  if (!show) return null

  return (
    <div role="status" className={cn('surface mb-3 flex items-center gap-3 rounded-lg border py-2.5 pr-2 pl-4', className)}>
      <MessagesSquare className="size-4 shrink-0 text-muted-foreground max-sm:hidden" aria-hidden />
      <div className="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-2">
        <p className="text-body text-foreground">Use jobwright from your own Claude</p>
        <p className="text-caption text-muted-foreground">Set up in 2 minutes</p>
      </div>
      <Button asChild size="sm" variant="secondary">
        <Link to="/profile?tab=claude">Set up</Link>
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label="Dismiss"
        onClick={() => {
          dismissClaudeCard(userId)
          setShow(false)
        }}
      >
        <X />
      </Button>
    </div>
  )
}

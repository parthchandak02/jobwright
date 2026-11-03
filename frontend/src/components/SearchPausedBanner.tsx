import { useEffect, useState } from 'react'
import { PauseCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { updateProfile, type Profile } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  profile: Profile | null
  /** Called after the search is turned back on (refresh the profile). */
  onResumed?: () => void
  className?: string
}

/** Calm board notice while "Keep looking for new jobs" is off, with a one-tap Resume. */
export function SearchPausedBanner({ profile, onResumed, className }: Props) {
  const [busy, setBusy] = useState(false)
  const [resumed, setResumed] = useState<string | null>(null)
  const paused = profile?.search_enabled === false
  // Forget a local "resumed" once the refreshed profile agrees, so a later pause shows again.
  useEffect(() => {
    if (!paused) setResumed(null)
  }, [paused])
  if (!profile || profile.search_enabled !== false || resumed === profile.user_id) return null

  const backlog = profile.stage_counts?.backlog ?? 0

  async function resume() {
    if (!profile) return
    setBusy(true)
    try {
      await updateProfile({ search_enabled: true })
      setResumed(profile.user_id)
      toast.success('Search is back on. New jobs arrive with your next daily list.')
      onResumed?.()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div role="status" className={cn('surface mb-3 flex items-center gap-3 rounded-lg border py-2.5 pr-2 pl-4', className)}>
      <PauseCircle className="size-4 shrink-0 text-muted-foreground max-sm:hidden" aria-hidden />
      <div className="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-2">
        <p className="text-body text-foreground">New job search is paused</p>
        <p className="text-caption text-muted-foreground tabular-nums">
          <span className="max-sm:hidden" aria-hidden>
            ·{' '}
          </span>
          {backlog.toLocaleString()} {backlog === 1 ? 'job' : 'jobs'} in Backlog
        </p>
      </div>
      <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void resume()}>
        Resume
      </Button>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { ThumbsUp, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getCalibration, type Calibration } from '@/lib/api'
import { dismissCalibration, isCalibrationDismissed } from '@/lib/calibration'
import { useMe } from '@/lib/me'
import { cn } from '@/lib/utils'

type Props = {
  /** Refetch when this changes (e.g. the number of rated cards on the board). */
  refreshKey?: number
  className?: string
}

/** Gentle board nudge to rate a few jobs until the profile has `target` ratings or dismisses it. */
export function CalibrationBanner({ refreshKey, className }: Props) {
  const navigate = useNavigate()
  const { me } = useMe()
  const userId = me?.active_user ?? null
  const [data, setData] = useState<Calibration | null>(null)
  const [dismissed, setDismissed] = useState(() => isCalibrationDismissed(userId))

  useEffect(() => {
    setDismissed(isCalibrationDismissed(userId))
  }, [userId])

  useEffect(() => {
    if (!userId || isCalibrationDismissed(userId)) return
    let live = true
    void getCalibration()
      .then((c) => live && setData(c))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [userId, refreshKey])

  if (dismissed || !data || data.rated_count >= data.target || data.jobs.length === 0) return null

  return (
    <div role="status" className={cn('surface mb-3 flex items-center gap-3 rounded-lg border py-2.5 pr-2 pl-4', className)}>
      <ThumbsUp className="size-4 shrink-0 text-muted-foreground max-sm:hidden" aria-hidden />
      <div className="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-2">
        <p className="text-body text-foreground">Rate {data.target} jobs to sharpen your list</p>
        <p className="text-caption text-muted-foreground tabular-nums">
          {data.rated_count}/{data.target} done
        </p>
      </div>
      <Button type="button" size="sm" variant="secondary" onClick={() => navigate('/welcome/rate', { state: { now: true } })}>
        Rate jobs
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label="Dismiss"
        onClick={() => {
          dismissCalibration(userId)
          setDismissed(true)
        }}
      >
        <X />
      </Button>
    </div>
  )
}

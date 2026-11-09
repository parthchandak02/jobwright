import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react'
import { Ban, Banknote, ExternalLink, Maximize2, MapPin, ThumbsDown, ThumbsUp } from 'lucide-react'
import { JobDescriptionPane } from '@/components/drawer/JobDescriptionPane'
import { Chip } from '@/components/Chip'
import { listingHref, placeLine } from '@/components/JobSummary'
import { MatchExplanation } from '@/components/MatchExplanation'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { JobCard } from '@/lib/api'
import { swipeAnswer, type ReviewAnswer } from '@/lib/reviewQueue'
import { compactPay } from '@/lib/pay'

type Props = {
  job: JobCard
  /** Full job (with description) once loaded; undefined while loading, null if it failed. */
  detail: JobCard | null | undefined
  onSwipe: (answer: ReviewAnswer) => void
  onOpenFull: () => void
  /** Shown under the match explanation (the optional "not for me" reasons). */
  children?: ReactNode
}

const LEAVE_MS = 200

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Swipe right / left on touch or pen (mouse keeps normal text selection). */
function useSwipe(onSwipe: (answer: ReviewAnswer) => void) {
  const ref = useRef<HTMLElement | null>(null)
  const start = useRef<{ x: number; y: number; active: boolean } | null>(null)
  const dxRef = useRef(0)
  const [dx, setDx] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [leaving, setLeaving] = useState<ReviewAnswer | null>(null)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const threshold = useCallback(() => Math.min(120, (ref.current?.offsetWidth ?? 360) * 0.28), [])

  const set = (v: number) => {
    dxRef.current = v
    setDx(v)
  }

  function reset() {
    start.current = null
    setDragging(false)
    set(0)
  }

  const handlers = {
    onPointerDown(e: PointerEvent<HTMLElement>) {
      if (e.pointerType === 'mouse' || leaving) return
      if ((e.target as HTMLElement).closest('a,button,input,textarea,select,[role="button"]')) return
      start.current = { x: e.clientX, y: e.clientY, active: false }
    },
    onPointerMove(e: PointerEvent<HTMLElement>) {
      const s = start.current
      if (!s) return
      const mx = e.clientX - s.x
      const my = e.clientY - s.y
      if (!s.active) {
        if (Math.abs(my) > 10 && Math.abs(my) > Math.abs(mx)) {
          start.current = null
          return
        }
        if (Math.abs(mx) < 10) return
        s.active = true
        setDragging(true)
        try {
          e.currentTarget.setPointerCapture(e.pointerId)
        } catch {
          // Synthetic or already-released pointers can't be captured; moves still arrive.
        }
      }
      set(mx)
    },
    onPointerUp() {
      const s = start.current
      start.current = null
      if (!s?.active) return
      setDragging(false)
      const answer = swipeAnswer(dxRef.current, threshold())
      if (!answer) return set(0)
      if (prefersReducedMotion()) {
        set(0)
        onSwipe(answer)
        return
      }
      setLeaving(answer)
      timer.current = window.setTimeout(() => onSwipe(answer), LEAVE_MS)
    },
    onPointerCancel: reset,
  }

  return { ref, dx, dragging, leaving, threshold, handlers }
}

export function ReviewCard({ job, detail, onSwipe, onOpenFull, children }: Props) {
  const { ref, dx, dragging, leaving, threshold, handlers } = useSwipe(onSwipe)
  const href = listingHref(job)
  const salary = compactPay(job.salary)
  const shown = detail ?? job
  const description = (detail?.full_description || '').trim()

  const reduced = prefersReducedMotion()
  const offset = leaving ? (leaving === 'interested' ? 1 : -1) * (window.innerWidth + 80) : dx
  const progress = Math.min(1, Math.abs(dx) / threshold())
  const heading: ReviewAnswer = leaving ?? (dx > 0 ? 'interested' : 'not_for_me')
  const style: CSSProperties = {
    transform: offset ? `translateX(${offset}px)${reduced ? '' : ` rotate(${offset / 40}deg)`}` : undefined,
    transition: dragging ? 'none' : `transform ${LEAVE_MS}ms var(--ease-out)`,
    touchAction: 'pan-y',
  }

  return (
    <article
      ref={ref}
      aria-labelledby="review-job-title"
      data-slot="review-card"
      className="surface relative animate-in rounded-lg p-4 duration-(--dur-2) fade-in-0 slide-in-from-bottom-1 select-text md:p-6"
      style={style}
      {...handlers}
    >
      {/* Drag feedback: tint + label on the side the card is heading to. */}
      {dx !== 0 || leaving ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-10 flex items-start rounded-lg border-2 px-4"
          style={
            {
              '--tone': heading === 'interested' ? 'var(--success)' : 'var(--destructive)',
              borderColor: 'var(--tone)',
              opacity: leaving ? 1 : progress,
              justifyContent: heading === 'interested' ? 'flex-start' : 'flex-end',
            } as CSSProperties
          }
        >
          <span className="tone-tint inline-flex -translate-y-1/2 items-center gap-1.5 rounded-full border px-3 py-1 text-label shadow-e1">
            {heading === 'interested' ? <ThumbsUp className="size-4" /> : <ThumbsDown className="size-4" />}
            {heading === 'interested' ? 'Interested' : 'Not for me'}
          </span>
        </div>
      ) : null}

      <header>
        <h2 id="review-job-title" className="text-title text-foreground">
          {job.title || 'Untitled'}
        </h2>
        <p className="mt-1 text-subheading text-muted-foreground">{job.company || job.site || 'Unknown company'}</p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-body text-muted-foreground">
          <p className="flex min-w-0 items-center gap-1.5">
            <MapPin className="size-4 shrink-0" aria-hidden />
            <span>{placeLine(job)}</span>
          </p>
          <p className="flex min-w-0 items-center gap-1.5">
            <Banknote className="size-4 shrink-0" aria-hidden />
            <span>{salary || 'Pay not stated'}</span>
          </p>
        </div>
        {job.is_dead ? (
          <Chip icon={Ban} tone="--destructive" className="mt-3">
            Posting closed
          </Chip>
        ) : null}
      </header>

      <section aria-label="Why this score" className="mt-5 rounded-lg bg-surface-muted p-4">
        <MatchExplanation job={shown} />
      </section>

      {children}

      <section aria-labelledby="review-jd" className="mt-6">
        <h3 id="review-jd" className="mb-2 text-subheading text-foreground">
          Job description
        </h3>
        {detail === undefined ? (
          <div className="space-y-2" aria-label="Loading description">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        ) : description ? (
          <JobDescriptionPane text={description} />
        ) : (
          <p className="text-body text-muted-foreground">No description saved for this job. Open the posting to read it.</p>
        )}
      </section>

      <div className="mt-5 flex flex-wrap gap-2 border-t pt-4">
        {href ? (
          <Button asChild size="sm" variant="secondary">
            <a href={href} target="_blank" rel="noreferrer">
              <ExternalLink /> Open posting
            </a>
          </Button>
        ) : null}
        <Button type="button" size="sm" variant="ghost" onClick={onOpenFull}>
          <Maximize2 /> Open full job
        </Button>
      </div>
    </article>
  )
}

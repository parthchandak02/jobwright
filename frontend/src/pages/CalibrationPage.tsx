import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Loader2, Search, ThumbsDown, ThumbsUp, TriangleAlert } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ReasonChips } from '@/components/ReasonChips'
import { WelcomeShell, WelcomeStep } from '@/components/welcome/WelcomeShell'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getCalibration, rateJob, type Calibration, type CalibrationJob } from '@/lib/api'
import { useMe } from '@/lib/me'
import { GOOD_FIT_REASONS, useNotAFitReasons } from '@/lib/reasons'
import { cn, errorMessage } from '@/lib/utils'

type Phase = 'loading' | 'error' | 'waiting' | 'rating' | 'done'
type Mode = null | 'up' | 'down'

const UP_SCORE = 8
const DOWN_SCORE = 2
const POLL_MS = 6000
const READY_AT = 10

function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      className="h-1 w-full overflow-hidden rounded-full bg-border"
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-(--dur-3) ease-out" style={{ width: `${pct}%` }} />
    </div>
  )
}

function place(job: CalibrationJob) {
  return [job.company, job.location].filter(Boolean).join(' · ')
}

export function CalibrationPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const now = Boolean((location.state as { now?: boolean } | null)?.now)
  const { me } = useMe()
  const notAFit = useNotAFitReasons()
  const [phase, setPhase] = useState<Phase>('loading')
  const [data, setData] = useState<Calibration | null>(null)
  const [queue, setQueue] = useState<CalibrationJob[]>([])
  const [index, setIndex] = useState(0)
  const [rated, setRated] = useState(0)
  const [mode, setMode] = useState<Mode>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const skipped = useRef(new Set<string>())

  const fresh = (c: Calibration) => c.jobs.filter((j) => !skipped.current.has(j.job_id))

  const decide = useCallback(
    (c: Calibration, startNow = false) => {
      setData(c)
      setRated(c.rated_count)
      const jobs = c.jobs.filter((j) => !skipped.current.has(j.job_id))
      if (c.rated_count >= c.target) return setPhase('done')
      const enough = c.ready || jobs.length >= c.target - c.rated_count
      if (jobs.length && (enough || startNow)) {
        setQueue(jobs)
        setIndex(0)
        setPhase('rating')
      } else if (c.ready) setPhase('done')
      else setPhase('waiting')
    },
    [],
  )

  const load = useCallback(
    (startNow = false) =>
      getCalibration()
        .then((c) => decide(c, startNow))
        .catch(() => setPhase('error')),
    [decide],
  )

  useEffect(() => {
    void load(now)
  }, [load, now])

  useEffect(() => {
    if (phase !== 'waiting') return
    const id = window.setInterval(() => {
      void getCalibration()
        .then((c) => decide(c))
        .catch(() => undefined)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [phase, decide])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [phase, index])

  function next() {
    setMode(null)
    setReasons([])
    if (index + 1 < queue.length) setIndex(index + 1)
    else {
      setPhase('loading')
      void load(true)
    }
  }

  function skip() {
    const job = queue[index]
    if (job) skipped.current.add(job.job_id)
    next()
  }

  async function save() {
    const job = queue[index]
    if (!job || !mode) return
    if (mode === 'down' && !reasons.length) {
      toast.error('Pick at least one reason so the scorer knows why.')
      return
    }
    setBusy(true)
    try {
      await rateJob(job, mode === 'up' ? UP_SCORE : DOWN_SCORE, reasons, reasons.length ? '' : 'Good fit')
      const done = rated + 1
      setRated(done)
      if (data && done >= data.target) setPhase('done')
      else next()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const toBoard = () => navigate('/')
  const target = data?.target ?? 10
  const job = phase === 'rating' ? queue[index] : undefined
  const later = (
    <Button type="button" size="sm" variant="ghost" onClick={toBoard} disabled={busy}>
      Finish later
    </Button>
  )

  let body
  if (phase === 'loading') {
    body = (
      <div className="space-y-3" aria-label="Loading">
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    )
  } else if (phase === 'error') {
    body = (
      <EmptyState
        icon={TriangleAlert}
        title="Could not load jobs to rate"
        description="Check your connection and try again."
        action={
          <Button type="button" size="sm" variant="secondary" onClick={() => void load()}>
            Try again
          </Button>
        }
      />
    )
  } else if (phase === 'waiting' && data) {
    const ready = fresh(data)
    body = (
      <EmptyState
        icon={Search}
        title="Finding your first jobs"
        description="Jobs to rate show up here once about 10 are scored. The first search takes 30 to 60 minutes, so feel free to leave and come back from your board."
      >
        <Bar value={data.scored_count} max={READY_AT} label="Jobs scored" />
        <p className="mt-2 flex items-center justify-center gap-1.5 text-caption text-muted-foreground tabular-nums">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          {Math.min(data.scored_count, READY_AT)} of {READY_AT} scored
        </p>
        {ready.length ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="mt-5"
            onClick={() => {
              setQueue(ready)
              setIndex(0)
              setPhase('rating')
            }}
          >
            Rate the {ready.length} ready now
          </Button>
        ) : null}
      </EmptyState>
    )
  } else if (phase === 'done') {
    const full = rated >= target
    body = (
      <EmptyState
        icon={CheckCircle2}
        title={full ? 'Thanks, that helps' : 'That’s all for now'}
        description={
          full
            ? 'Your ratings are saved. The next scoring run learns from them, so your daily list gets sharper.'
            : 'You can rate more any time from a job on your board. Every rating teaches the scorer.'
        }
        action={
          <Button type="button" onClick={toBoard}>
            Go to my board
          </Button>
        }
      />
    )
  } else if (job) {
    body = (
      <div>
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <p className="text-label text-foreground">
            Job {index + 1} of {queue.length}
          </p>
          <p className="text-caption text-muted-foreground tabular-nums">
            {rated} of {target} rated
          </p>
        </div>
        <Bar value={rated} max={target} label="Jobs rated" />

        <article key={job.job_id} className="mt-5 rounded-lg border bg-surface p-4 md:p-5" aria-labelledby="calibration-job-title">
          <h2 id="calibration-job-title" className="text-heading text-foreground">
            {job.title}
          </h2>
          {place(job) ? <p className="mt-1 text-caption text-muted-foreground">{place(job)}</p> : null}
          {job.reason ? <p className="mt-3 text-body text-muted-foreground">{job.reason}</p> : null}

          <div className="mt-5 flex flex-wrap gap-2">
            {(['up', 'down'] as const).map((m) => {
              const Icon = m === 'up' ? ThumbsUp : ThumbsDown
              const active = mode === m
              return (
                <Button
                  key={m}
                  type="button"
                  size="sm"
                  variant="secondary"
                  aria-pressed={active}
                  disabled={busy}
                  className={cn('max-sm:flex-1', active && 'border-primary bg-accent text-accent-foreground hover:bg-accent')}
                  onClick={() => {
                    setMode(active ? null : m)
                    setReasons([])
                  }}
                >
                  <Icon /> {m === 'up' ? 'Good fit' : 'Not for me'}
                </Button>
              )
            })}
            <Button type="button" size="sm" variant="ghost" onClick={skip} disabled={busy}>
              Skip
            </Button>
          </div>

          {mode ? (
            <div className="mt-4 space-y-3 border-t pt-4">
              <p className="text-caption text-muted-foreground">
                {mode === 'up' ? 'What makes it a good fit? Optional.' : 'Why isn’t it a fit? Pick any that apply.'}
              </p>
              <ReasonChips
                options={mode === 'up' ? GOOD_FIT_REASONS : notAFit}
                selected={reasons}
                onChange={setReasons}
                tone={mode === 'up' ? 'positive' : 'negative'}
              />
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={() => void save()} disabled={busy || (mode === 'down' && !reasons.length)}>
                  {busy ? <Loader2 className="animate-spin" /> : null}
                  Save and next
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setMode(null)} disabled={busy}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </article>
      </div>
    )
  }

  return (
    <WelcomeShell email={me?.email}>
      <WelcomeStep
        title="Rate a few jobs"
        description="Tell us which of these fit. Each rating teaches the scorer, so your first daily lists are sharper. It’s optional."
        actions={phase === 'done' ? undefined : later}
      >
        {body}
      </WelcomeStep>
    </WelcomeShell>
  )
}

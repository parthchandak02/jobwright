import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, CloudOff, Loader2, RotateCcw, SkipForward, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { listingHref } from '@/components/JobSummary'
import { PageColumn, PageHeader } from '@/components/PageHeader'
import { ReasonChips } from '@/components/ReasonChips'
import { ReviewCard } from '@/components/review/ReviewCard'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import { clearReview, getJob, moveJob, rateJob, type BoardResponse, type JobCard, type Profile } from '@/lib/api'
import { useMe } from '@/lib/me'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { useNotAFitReasons } from '@/lib/reasons'
import {
  buildQueue,
  clearSkips,
  inFilter,
  keyAction,
  mergeQueue,
  reviewPosition,
  sessionCounts,
  STRONG_MIN,
  upcoming,
  type ReviewAnswer,
  type ReviewFilter,
} from '@/lib/reviewQueue'
import { useDebouncedCallback } from '@/lib/useDebouncedCallback'
import { cn, errorMessage } from '@/lib/utils'

/** Same scores the drawer's thumbs use, so a review answer is an ordinary label. */
const UP_SCORE = 8
const DOWN_SCORE = 2
const TOAST_ID = 'quick-review'

type Slim = Pick<JobCard, 'job_id' | 'url' | 'title' | 'company' | 'fit_score'>
type Step = { id: string; answer: ReviewAnswer; job: Slim }

type Session = {
  ids: string[]
  answers: Record<string, ReviewAnswer>
  history: Step[]
  /** Answered jobs leave the Backlog; keep enough of them to count and undo. */
  seen: Record<string, Slim>
  filter: ReviewFilter
}

const EMPTY: Session = { ids: [], answers: {}, history: [], seen: {}, filter: 'all' }
const storageKey = (user: string | null | undefined) => `jobwright-review:${user || 'default'}`

function slim(j: JobCard | Slim): Slim {
  return { job_id: j.job_id, url: j.url, title: j.title, company: j.company, fit_score: j.fit_score }
}

function loadSession(key: string): Session {
  try {
    const raw = sessionStorage.getItem(key)
    if (raw) return { ...EMPTY, ...(JSON.parse(raw) as Partial<Session>) }
  } catch {
    // Private mode or bad JSON: start fresh.
  }
  return EMPTY
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`
}

/** Keys the focused element needs for itself: typing anywhere, arrows inside a toggle group. */
function ownsKey(target: EventTarget | null, key: string): boolean {
  const el = target as HTMLElement | null
  if (!el?.closest) return false
  if (el.closest('input,textarea,select,[contenteditable="true"]')) return true
  return key.startsWith('Arrow') && Boolean(el.closest('[role="radiogroup"],[data-slot="segmented"]'))
}

function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-surface px-1 font-sans text-micro text-muted-foreground',
        className,
      )}
    >
      {children}
    </kbd>
  )
}

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div
      role="progressbar"
      aria-label="Reviewed"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      className="h-1 w-full overflow-hidden rounded-full bg-border"
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-(--dur-3) ease-out" style={{ width: `${pct}%` }} />
    </div>
  )
}

type Props = {
  board: BoardResponse | null
  profile: Profile | null
  /** Board fetch finished without data (show an error, not a skeleton). */
  failed?: boolean
  /** Refresh the board shell (sidebar counts) after answers settle. */
  onChanged: () => void
}

/** Quick review: go through unrated Backlog jobs one at a time, best match first. */
export function ReviewPage({ board, profile, failed, onChanged }: Props) {
  const navigate = useNavigate()
  const { me } = useMe()
  const key = storageKey(me?.active_user ?? profile?.user_id)
  const notAFit = useNotAFitReasons()
  const phone = useMediaQuery('(max-width: 767px)')

  const [session, setSessionState] = useState<Session>(() => loadSession(key))
  const sessionRef = useRef(session)
  const [jobs, setJobs] = useState<Record<string, JobCard>>({})
  const [details, setDetails] = useState<Record<string, JobCard | null>>({})
  // Reasons belong to the job on screen; a new job starts with none.
  const [picked, setPicked] = useState<{ id: string | null; list: string[] }>({ id: null, list: [] })
  const [undoing, setUndoing] = useState(false)
  const chain = useRef<Promise<unknown>>(Promise.resolve())
  const loading = useRef(new Set<string>())

  const update = useCallback(
    (fn: (s: Session) => Session) => {
      const next = fn(sessionRef.current)
      sessionRef.current = next
      setSessionState(next)
      try {
        sessionStorage.setItem(key, JSON.stringify(next))
      } catch {
        // Storage full or blocked: the session still works in memory.
      }
    },
    [key],
  )

  // Profile switch (or first load of the login): pick up that profile's session.
  useEffect(() => {
    const s = loadSession(key)
    sessionRef.current = s
    setSessionState(s)
  }, [key])

  // Board refresh: keep the session order, add new unrated Backlog jobs, drop ones that left
  // the Backlog some other way (rated or moved elsewhere) unless this session touched them.
  useEffect(() => {
    if (!board) return
    const fresh = buildQueue(board)
    const freshIds = new Set(fresh.map((j) => j.job_id))
    setJobs((prev) => {
      const next = { ...prev }
      for (const j of fresh) next[j.job_id] = j
      return next
    })
    update((s) => {
      const touched = new Set(s.history.map((h) => h.id))
      const kept = s.ids.filter((id) => freshIds.has(id) || s.answers[id] || touched.has(id))
      return { ...s, ids: mergeQueue(kept, fresh) }
    })
  }, [board, update])

  const known = useMemo(() => {
    const out: Record<string, Slim | JobCard> = { ...session.seen }
    for (const [id, j] of Object.entries(jobs)) out[id] = j
    return out
  }, [jobs, session.seen])

  const { filter, ids, answers, history } = session
  const pos = reviewPosition(ids, known, answers, filter)
  const job = pos.current ? jobs[pos.current] : undefined
  const counts = sessionCounts(answers)
  const remaining = useMemo(() => {
    let all = 0
    let strong = 0
    for (const id of ids) {
      const j = known[id]
      if (!j || answers[id]) continue
      all += 1
      if (inFilter(j, 'strong')) strong += 1
    }
    return { all, strong }
  }, [ids, known, answers])

  // Descriptions: load the current job and prefetch the next two.
  const nextIds = upcoming(ids, known, answers, filter, 2)
  const wanted = [pos.current, ...nextIds].filter((id): id is string => Boolean(id))
  const wantedKey = wanted.join(',')
  useEffect(() => {
    for (const id of wantedKey.split(',').filter(Boolean)) {
      const j = jobs[id]
      if (!j || id in details || loading.current.has(id)) continue
      loading.current.add(id)
      getJob(j)
        .then((full) => setDetails((d) => ({ ...d, [id]: full })))
        .catch(() => setDetails((d) => ({ ...d, [id]: null })))
        .finally(() => loading.current.delete(id))
    }
  }, [wantedKey, jobs, details])

  const currentId = pos.current
  const reasons = useMemo(() => (picked.id === currentId ? picked.list : []), [picked, currentId])
  const setReasons = useCallback(
    (fn: string[] | ((cur: string[]) => string[])) =>
      setPicked((p) => {
        const cur = p.id === currentId ? p.list : []
        return { id: currentId, list: typeof fn === 'function' ? fn(cur) : fn }
      }),
    [currentId],
  )

  // One board refresh after a burst of answers (and on leaving the page).
  const refreshSoon = useDebouncedCallback(() => onChanged(), 1200)

  /** Run API calls one after another so an Undo never races the answer it undoes. */
  const enqueue = useCallback(<T,>(op: () => Promise<T>): Promise<T> => {
    const run = chain.current.then(op, op)
    chain.current = run.catch(() => undefined)
    return run
  }, [])

  const undo = useCallback(() => {
    const last = sessionRef.current.history.at(-1)
    if (!last) return
    update((s) => {
      const answersNext = { ...s.answers }
      delete answersNext[last.id]
      return { ...s, answers: answersNext, history: s.history.slice(0, -1) }
    })
    toast.dismiss(TOAST_ID)
    if (last.answer === 'skip') return
    const ref = last.job as JobCard
    setUndoing(true)
    enqueue(async () => {
      if (last.answer === 'interested') {
        await clearReview(ref)
        await moveJob(ref, 'backlog')
      } else {
        await moveJob(ref, 'backlog')
        await clearReview(ref)
      }
    })
      .then(() => {
        toast.success('Undone. The job is back in your Backlog.', { id: TOAST_ID, position: phone ? 'top-center' : undefined })
        refreshSoon(undefined)
      })
      .catch((e) => {
        // Put the answer back: the server still has it.
        update((s) => ({ ...s, answers: { ...s.answers, [last.id]: last.answer }, history: [...s.history, last] }))
        toast.error(`Couldn’t undo: ${errorMessage(e)}`, { id: TOAST_ID })
      })
      .finally(() => setUndoing(false))
  }, [enqueue, phone, refreshSoon, update])

  const answer = useCallback(
    (kind: ReviewAnswer) => {
      if (!job || undoing) return
      const picked = kind === 'not_for_me' ? reasons : []
      const step: Step = { id: job.job_id, answer: kind, job: slim(job) }
      update((s) => ({
        ...s,
        answers: { ...s.answers, [job.job_id]: kind },
        history: [...s.history, step],
        seen: { ...s.seen, [job.job_id]: slim(job) },
      }))
      if (kind === 'skip') return

      const title = job.title || 'This job'
      toast(kind === 'interested' ? 'Moved to Prepare' : 'Closed as not for me', {
        id: TOAST_ID,
        description: title,
        position: phone ? 'top-center' : undefined,
        action: { label: 'Undo', onClick: () => undo() },
      })
      enqueue(async () => {
        if (kind === 'interested') {
          await rateJob(job, UP_SCORE, [], 'Interested')
          await moveJob(job, 'prepare')
        } else {
          await rateJob(job, DOWN_SCORE, picked, picked.length ? '' : 'Not for me')
          await moveJob(job, 'closed', { outcome: 'not_interested', reasons: picked })
        }
      })
        .then(() => refreshSoon(undefined))
        .catch((e) => {
          update((s) => {
            const answersNext = { ...s.answers }
            delete answersNext[job.job_id]
            return { ...s, answers: answersNext, history: s.history.filter((h) => h !== step) }
          })
          toast.error(`Couldn’t save “${title}”: ${errorMessage(e)}`, { id: TOAST_ID })
          refreshSoon(undefined)
        })
    },
    [enqueue, job, phone, reasons, refreshSoon, undo, undoing, update],
  )

  const openPosting = useCallback(() => {
    const href = job ? listingHref(job) : null
    if (href) window.open(href, '_blank', 'noopener,noreferrer')
  }, [job])

  const openFull = useCallback(() => {
    if (job) navigate(`/jobs/${job.job_id}?from=review`)
  }, [job, navigate])

  // Keyboard: arrows or letters answer, 1-9 pick reasons, U / Cmd+Z undo.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.repeat || ownsKey(e.target, e.key)) return
      if (document.querySelector('[role="dialog"]')) return
      const action = keyAction(e)
      if (!action) return
      if (typeof action === 'object') {
        const r = notAFit[action.reason]
        if (!r || !job) return
        e.preventDefault()
        setReasons((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]))
        return
      }
      e.preventDefault()
      if (action === 'undo') undo()
      else if (action === 'posting') openPosting()
      else if (action === 'open') openFull()
      else answer(action)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [answer, job, notAFit, openFull, openPosting, setReasons, undo])

  const setFilter = (f: ReviewFilter) => update((s) => ({ ...s, filter: f }))
  const paused = profile?.search_enabled === false
  const canUndo = history.length > 0 && !undoing

  const filterControl = (
    <Segmented
      size="sm"
      value={filter}
      onValueChange={setFilter}
      aria-label="Which jobs"
      options={[
        {
          value: 'strong',
          label: (
            <>
              Strong only ({STRONG_MIN}+)<span className="ml-1.5 text-muted-foreground tabular-nums">{remaining.strong}</span>
            </>
          ),
        },
        {
          value: 'all',
          label: (
            <>
              All<span className="ml-1.5 text-muted-foreground tabular-nums">{remaining.all}</span>
            </>
          ),
        },
      ]}
    />
  )

  const undoButton = (
    <Button type="button" size={phone ? 'icon-sm' : 'sm'} variant="ghost" disabled={!canUndo} onClick={undo} aria-label="Undo last answer">
      {undoing ? <Loader2 className="animate-spin" /> : <RotateCcw />}
      {phone ? null : (
        'Undo'
      )}
    </Button>
  )

  let body: ReactNode
  if (!board) {
    body = failed ? (
      <EmptyState
        size="page"
        icon={CloudOff}
        title="Couldn’t load your jobs"
        description="Check your internet, then try again."
        action={
          <Button variant="secondary" onClick={onChanged}>
            Try again
          </Button>
        }
      />
    ) : (
      <div className="space-y-4" aria-label="Loading">
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-96 w-full rounded-lg" />
      </div>
    )
  } else if (!job) {
    const did = counts.interested + counts.not_for_me + counts.skip
    const moreInAll = filter === 'strong' && remaining.all > 0
    body = (
      <EmptyState
        size="page"
        icon={CheckCircle2}
        title={moreInAll ? 'No strong matches left' : 'You’re all caught up'}
        description={
          <>
            {did
              ? `This session: ${[
                  counts.interested ? `${plural(counts.interested, 'job')} moved to Prepare` : '',
                  counts.not_for_me ? `${plural(counts.not_for_me, 'job')} closed as not for me` : '',
                  counts.skip ? `${counts.skip.toLocaleString()} skipped` : '',
                ]
                  .filter(Boolean)
                  .join(', ')}.`
              : moreInAll
                ? 'Every job scored 7 or more has an answer.'
                : 'Nothing in your Backlog needs a look right now.'}
            {moreInAll ? ` ${plural(remaining.all, 'more job')} scored lower ${remaining.all === 1 ? 'is' : 'are'} waiting.` : ''}
          </>
        }
        action={
          <>
            {moreInAll ? (
              <Button type="button" onClick={() => setFilter('all')}>
                Review the rest
              </Button>
            ) : (
              <Button type="button" onClick={() => navigate('/')}>
                Back to the board
              </Button>
            )}
            {counts.skip ? (
              <Button type="button" variant="secondary" onClick={() => update((s) => ({ ...s, answers: clearSkips(s.answers), history: s.history.filter((h) => h.answer !== 'skip') }))}>
                Review {counts.skip === 1 ? 'the one' : `the ${counts.skip}`} you skipped
              </Button>
            ) : null}
            {moreInAll ? (
              <Button type="button" variant="ghost" onClick={() => navigate('/')}>
                Back to the board
              </Button>
            ) : null}
          </>
        }
      >
        {paused ? (
          <p className="text-caption text-muted-foreground">
            New job search is paused.{' '}
            <button
              type="button"
              className="touch-target relative font-medium text-foreground underline underline-offset-2"
              onClick={() => navigate('/profile?tab=whatsapp')}
            >
              Resume it in Settings
            </button>{' '}
            to get new jobs.
          </p>
        ) : null}
        {canUndo ? (
          <Button type="button" size="sm" variant="ghost" className="mt-2" onClick={undo}>
            <RotateCcw /> Undo last answer
          </Button>
        ) : null}
      </EmptyState>
    )
  } else {
    body = (
      <>
        <div className="mb-3 flex items-center justify-between gap-3 md:mb-2">
          <div className="md:hidden">{filterControl}</div>
          <p className="text-label text-foreground tabular-nums md:order-first" aria-live="polite">
            {pos.number.toLocaleString()} of {pos.total.toLocaleString()}
          </p>
          <p className="text-caption text-muted-foreground tabular-nums max-md:hidden">
            {counts.interested ? `${counts.interested} interested` : null}
            {counts.interested && counts.not_for_me ? ' · ' : null}
            {counts.not_for_me ? `${counts.not_for_me} not for me` : null}
          </p>
        </div>
        <Bar value={pos.answered} max={pos.total} />

        <div className="mt-4">
          <ReviewCard key={job.job_id} job={job} detail={details[job.job_id]} onSwipe={answer} onOpenFull={openFull}>
            <section aria-labelledby="review-reasons" className="mt-5">
              <p id="review-reasons" className="text-label text-foreground">
                Not for me because… <span className="font-normal text-muted-foreground">optional</span>
              </p>
              <p className="mb-3 text-caption text-muted-foreground">
                Pick any before you answer<span className="max-md:hidden"> (keys 1–9)</span>. Similar jobs score lower next time.
              </p>
              <ReasonChips options={notAFit} selected={reasons} onChange={setReasons} />
            </section>
          </ReviewCard>
        </div>
      </>
    )
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <PageHeader
          title="Quick review"
          description="One Backlog job at a time, best match first. Every answer teaches the scorer."
          actions={filterControl}
          mobileActions={undoButton}
        />
        <PageColumn className="pt-5 pb-8 md:pt-8">
          {board && !job ? <div className="mb-5 md:hidden">{filterControl}</div> : null}
          {body}
        </PageColumn>

        {job ? (
          <div className="sticky bottom-0 z-20 mt-2 md:bottom-4">
            <PageColumn>
              <div
                role="region"
                aria-label="Answer"
                className="border-t bg-surface pt-3 pb-[calc(0.75rem+var(--safe-bottom))] shadow-e1 max-md:-mx-page-x max-md:px-3 md:rounded-lg md:border md:px-3 md:py-3"
              >
                <div className="flex items-center gap-2">
                  <div className="max-md:hidden">{undoButton}</div>
                  <div className="grid flex-1 grid-cols-3 gap-2 md:ml-auto md:flex md:flex-none">
                    <Button
                      type="button"
                      variant="secondary"
                      className="h-12 max-md:flex-col max-md:gap-0.5 max-md:text-caption md:h-10"
                      onClick={() => answer('not_for_me')}
                      disabled={undoing}
                    >
                      <ThumbsDown /> Not for me
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-12 max-md:flex-col max-md:gap-0.5 max-md:text-caption md:h-10"
                      onClick={() => answer('skip')}
                      disabled={undoing}
                    >
                      <SkipForward /> Skip
                    </Button>
                    <Button
                      type="button"
                      className="h-12 max-md:flex-col max-md:gap-0.5 max-md:text-caption md:h-10"
                      onClick={() => answer('interested')}
                      disabled={undoing}
                    >
                      <ThumbsUp /> Interested
                    </Button>
                  </div>
                </div>
                <p className="mt-2 text-center text-caption text-muted-foreground max-md:hidden">
                  <Kbd>←</Kbd> or <Kbd>N</Kbd> not for me · <Kbd>↓</Kbd> or <Kbd>S</Kbd> skip · <Kbd>→</Kbd> or <Kbd>I</Kbd> interested ·{' '}
                  <Kbd>U</Kbd> undo · <Kbd>O</Kbd> posting · <Kbd>F</Kbd> full job
                </p>
                <p className="mt-2 text-center text-caption text-muted-foreground md:hidden">Swipe right if interested, left if not</p>
              </div>
            </PageColumn>
          </div>
        ) : null}
      </main>
    </div>
  )
}

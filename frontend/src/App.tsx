import { Suspense, lazy, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CloudOff, Inbox, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BoardResponse, JobCard, STAGE_LABELS } from '@/lib/api'
import { useBoard } from '@/lib/useBoard'
import { DOCK_QUERY, setSelectedJob } from '@/lib/jobPanel'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { reviewCount } from '@/lib/reviewQueue'
import { cn } from '@/lib/utils'
import { AppSidebar } from '@/components/AppSidebar'
import { AutoSearchControls } from '@/components/AutoSearchControls'
import { BoardHeader } from '@/components/BoardHeader'
import { Chip } from '@/components/Chip'
import { DailyBriefDialog } from '@/components/DailyBriefDialog'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { JobDrawer } from '@/components/JobDrawer'
import { JobsTable } from '@/components/JobsTable'
import { BoardSkeleton, KanbanBoard } from '@/components/KanbanBoard'
import { ManualAddModal } from '@/components/ManualAddModal'
import { PageSkeleton } from '@/components/PageSkeleton'
import { PhoneTabBar } from '@/components/PhoneTabBar'
import { StageTabs } from '@/components/StageTabs'
import { StatusBanner } from '@/components/StatusBanner'
import { CalibrationBanner } from '@/components/CalibrationBanner'
import { SearchPausedBanner } from '@/components/SearchPausedBanner'
import { ViewModeTabs, type ViewMode } from '@/components/ViewModeTabs'

const ProfilePage = lazy(() => import('@/components/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const QualityPage = lazy(() => import('@/pages/QualityPage').then((m) => ({ default: m.QualityPage })))
const AdminPage = lazy(() => import('@/pages/AdminPage').then((m) => ({ default: m.AdminPage })))
const ReviewPage = lazy(() => import('@/pages/ReviewPage').then((m) => ({ default: m.ReviewPage })))

const VIEW_KEY = 'jobwright-view'
/** The lane the phone board shows when no stage is picked (last one chosen). */
const PHONE_LANE_KEY = 'jobwright-phone-lane'

function jobMatchesQuery(job: JobCard, q: string): boolean {
  if (!q) return true
  const hay = [job.title, job.company, job.location, job.site].filter(Boolean).join(' ').toLowerCase()
  return hay.includes(q)
}

function isWorthALook(job: JobCard): boolean {
  const s = job.fit_score
  return job.funnel_stage === 'backlog' && s != null && s >= 5 && s <= 6 && !(job.dealbreakers || []).length
}

const NO_JOBS: JobCard[] = []

function allVisibleCount(columns: Record<string, JobCard[]>): number {
  return Object.values(columns).reduce((n, jobs) => n + jobs.length, 0)
}

function initialView(): ViewMode {
  const saved = localStorage.getItem(VIEW_KEY)
  if (saved === 'board' || saved === 'table') return saved
  return window.matchMedia('(max-width: 767px)').matches ? 'table' : 'board'
}

type Page = 'board' | 'profile' | 'quality' | 'admin' | 'review'

function pageFor(pathname: string): Page {
  if (pathname.startsWith('/profile')) return 'profile'
  if (pathname.startsWith('/quality')) return 'quality'
  if (pathname.startsWith('/admin')) return 'admin'
  if (pathname.startsWith('/review')) return 'review'
  return 'board'
}

/** A card waiting for the "Not for me / closed" dialog, with where it was dropped. */
type CloseTarget = { job: JobCard; position?: number }

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const { jobId } = useParams<{ jobId?: string }>()
  const page = pageFor(location.pathname)
  const isPhone = useMediaQuery('(max-width: 767px)')
  const { board, setBoard, profile, pendingNotify, loading, refresh, refreshCard, moveCard, applyCards, saveLaneOrder } = useBoard()
  const [view, setViewState] = useState<ViewMode>(initialView)
  const [showAdd, setShowAdd] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)
  const [closeTarget, setCloseTarget] = useState<CloseTarget | null>(null)
  const worthOnly = params.get('worth') === '1'

  // Stage filter and search live in the URL (?stage=prepare&q=design) so reload and shared links keep them.
  const stageParam = params.get('stage')
  const filterStage: string | 'all' = stageParam && STAGE_LABELS[stageParam] ? stageParam : 'all'
  useEffect(() => {
    if (filterStage !== 'all') localStorage.setItem(PHONE_LANE_KEY, filterStage)
  }, [filterStage])

  const setQueryParam = useCallback(
    (key: string, value: string | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (value) next.set(key, value)
          else next.delete(key)
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  // The search box types into local state (instant); the URL follows a moment later so fast
  // typing never loses keys. Back/forward or a pasted link updates the box.
  const urlQuery = params.get('q') || ''
  const [searchQuery, setSearchQuery] = useState(urlQuery)
  const writtenQuery = useRef(urlQuery)
  useEffect(() => {
    if (urlQuery === writtenQuery.current) return
    writtenQuery.current = urlQuery
    setSearchQuery(urlQuery)
  }, [urlQuery])
  useEffect(() => {
    if (searchQuery === writtenQuery.current) return
    const t = window.setTimeout(() => {
      writtenQuery.current = searchQuery
      setQueryParam('q', searchQuery || null)
    }, 250)
    return () => window.clearTimeout(t)
  }, [searchQuery, setQueryParam])

  function setView(next: ViewMode) {
    localStorage.setItem(VIEW_KEY, next)
    setViewState(next)
  }

  useEffect(() => {
    if (worthOnly) setViewState('table')
  }, [worthOnly])

  function selectStage(stage: string | 'all') {
    const value = stage === 'all' ? null : stage
    if (page === 'board') setQueryParam('stage', value)
    else navigate(value ? `/?stage=${encodeURIComponent(value)}` : '/')
  }

  // Filtering 300+ cards follows the typing at low priority, so keys never wait for the board.
  const search = useDeferredValue(searchQuery.trim().toLowerCase())

  const allJobs = useMemo(() => (board ? board.stages.flatMap((s) => board.columns[s] || []) : []), [board])
  const ratedOnBoard = useMemo(() => allJobs.filter((j) => j.user_fit_score != null).length, [allJobs])

  // Desktop: the job opens in a panel beside the board, so the board stays usable.
  const docked = useMediaQuery(DOCK_QUERY)
  // Mark the open job on the board / table only where both are visible side by side.
  useEffect(() => setSelectedJob(docked ? (jobId ?? null) : null), [docked, jobId])

  /** Opening another job while one is open swaps it in place (Back still returns to the board). */
  function openJobId(id: string) {
    navigate(`/jobs/${id}${location.search}`, { replace: Boolean(jobId) })
  }

  // Stable handlers for the (memoized) cards and rows: they read the latest route through a ref.
  const openJobIdRef = useRef(openJobId)
  openJobIdRef.current = openJobId
  const allJobsRef = useRef(allJobs)
  allJobsRef.current = allJobs
  const openJob = useCallback((job: JobCard) => openJobIdRef.current(job.job_id), [])
  const openJobByUrl = useCallback((url: string) => {
    const job = allJobsRef.current.find((j) => j.url === url)
    if (job) openJobIdRef.current(job.job_id)
  }, [])

  function closeDrawer() {
    navigate(params.get('from') === 'review' ? '/review' : `/${location.search}`)
  }

  // One predicate for both views: search plus "worth a look".
  const visible = useCallback(
    (j: JobCard) => jobMatchesQuery(j, search) && (!worthOnly || isWorthALook(j)),
    [search, worthOnly],
  )

  // Per lane, reuse the last filtered list while that lane and the filter are unchanged, so a
  // drag (which replaces two lanes) only re-renders those two lanes.
  const laneCache = useRef(new WeakMap<JobCard[], { visible: (j: JobCard) => boolean; jobs: JobCard[] }>())
  const filteredColumns = useMemo(() => {
    if (!board) return {}
    const cols: Record<string, JobCard[]> = {}
    for (const stage of board.stages) {
      const source = board.columns[stage] || NO_JOBS
      const hit = laneCache.current.get(source)
      if (hit && hit.visible === visible) {
        cols[stage] = hit.jobs
        continue
      }
      const jobs = source.filter(visible)
      laneCache.current.set(source, { visible, jobs })
      cols[stage] = jobs
    }
    return cols
  }, [board, visible])

  const visibleStages = useMemo(() => {
    if (!board) return []
    if (filterStage === 'all') return board.stages
    return board.stages.filter((s) => s === filterStage)
  }, [board, filterStage])

  const tableJobs = useMemo(
    () => visibleStages.flatMap((s) => filteredColumns[s] || []),
    [filteredColumns, visibleStages],
  )

  // Phone: the board shows one lane at a time. A stage filter (?stage=) picks it; with "All" it
  // falls back to the last lane chosen, then the first lane with jobs.
  const phoneBoard = isPhone && view === 'board' && !worthOnly
  const phoneLane = useMemo(() => {
    if (!board) return 'backlog'
    if (filterStage !== 'all') return filterStage
    const saved = localStorage.getItem(PHONE_LANE_KEY)
    if (saved && board.stages.includes(saved)) return saved
    return board.stages.find((s) => (filteredColumns[s] || []).length > 0) || board.stages[0]
  }, [board, filterStage, filteredColumns])

  // Strip counts match the desktop sidebar (stage totals); while searching they count matches.
  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    if (!board) return counts
    const narrowed = !!search || worthOnly
    for (const s of board.stages) {
      const shown = (filteredColumns[s] || []).length
      counts[s] = narrowed ? shown : (board.stage_counts?.[s] ?? profile?.stage_counts?.[s] ?? shown)
    }
    return counts
  }, [board, filteredColumns, profile, search, worthOnly])
  const allCount = board ? (search || worthOnly ? allVisibleCount(filteredColumns) : board.total) : 0

  function onBoardMove(job: JobCard, toStage: string, position: number, revert: BoardResponse | null) {
    if (toStage === 'closed') {
      // Ask why first; the card goes back until the dialog is confirmed.
      const before = revert?.stages.flatMap((s) => revert.columns[s] || []).find((j) => j.url === job.url)
      if (revert) setBoard(revert)
      setCloseTarget({ job: before || job, position })
      return
    }
    void moveCard(job, toStage, { position })
  }

  function onDismissConfirm(result: DismissResult) {
    const target = closeTarget
    setCloseTarget(null)
    if (!target) return
    void moveCard(target.job, 'closed', {
      outcome: result.outcome,
      reasons: result.reasons,
      close_reason: result.note || undefined,
      position: target.position,
    })
  }

  /** Score saved on a card: refetch just that card (the table doesn't say which one, so it reloads the board). */
  const onScoreSaved = useCallback(
    (job?: JobCard) => void (job ? refreshCard(job) : refresh()),
    [refresh, refreshCard],
  )

  /** Settings or Admin changed the signed-in profile: refresh the shell (banner, counts, schedule). */
  const refreshProfile = useCallback(() => void refresh({ board: false, profile: true, notify: true }), [refresh])

  function openWhatsApp() {
    setShowSchedule(true)
    void refresh({ board: false, notify: true })
  }

  const drawerOpen = Boolean(jobId)
  const showsTable = !(view === 'board' && !worthOnly)
  const openPreview = useMemo(() => (jobId ? allJobs.find((j) => j.job_id === jobId) ?? null : null), [allJobs, jobId])
  const pageTitle = filterStage === 'all' ? 'All jobs' : STAGE_LABELS[filterStage] || filterStage
  // Phone: the stage strip names the stage, so the header just says Jobs (board count = every lane).
  const headerTitle = isPhone ? 'Jobs' : pageTitle
  const headerCount = !board ? null : phoneBoard ? allVisibleCount(filteredColumns) : tableJobs.length
  const showTabBar = !drawerOpen

  return (
    <>
      <div
        className={cn(
          'relative flex h-full bg-background max-md:flex-col',
          // The tab bar owns the bottom safe area; sticky bars above it don't pad for it again.
          showTabBar && 'max-md:[--safe-bottom:0px]',
        )}
      >
        {page === 'board' ? (
          <a
            href="#jobs-main"
            className="skip-link fixed! top-2 left-2"
            onClick={(e) => {
              e.preventDefault()
              document.getElementById('jobs-main')?.focus()
            }}
          >
            Skip to jobs
          </a>
        ) : null}
        <AppSidebar
          profile={profile}
          board={board}
          filterStage={filterStage}
          onFilterStage={selectStage}
          jobOpen={drawerOpen}
        />

        <ErrorBoundary resetKey={page}>
          {page === 'profile' ? (
            <Suspense fallback={<PageSkeleton />}>
              <ProfilePage profile={profile} onBack={() => navigate('/')} onProfileChanged={refreshProfile} />
            </Suspense>
          ) : page === 'quality' ? (
            <Suspense fallback={<PageSkeleton />}>
              <QualityPage />
            </Suspense>
          ) : page === 'admin' ? (
            <Suspense fallback={<PageSkeleton />}>
              <AdminPage onActiveProfileChanged={refreshProfile} />
            </Suspense>
          ) : page === 'review' ? (
            <Suspense fallback={<PageSkeleton />}>
              <ReviewPage board={board} profile={profile} failed={!loading && !board} onChanged={() => void refresh({ profile: true })} />
            </Suspense>
          ) : (
            <div
              className={cn(
                'flex min-w-0 flex-1 flex-col max-md:min-h-0',
                drawerOpen && 'max-md:hidden',
                docked && drawerOpen && 'board-beside-panel',
              )}
            >
              <StatusBanner />
              <BoardHeader
                title={headerTitle}
                count={headerCount}
                view={view}
                onViewChange={setView}
                search={searchQuery}
                onSearchChange={setSearchQuery}
                pendingNotify={pendingNotify}
                onOpenWhatsApp={openWhatsApp}
                onAddJob={() => setShowAdd(true)}
                onRunDone={() => void refresh({ profile: true, notify: true })}
                reviewCount={reviewCount(board)}
              />

              <main
                id="jobs-main"
                // Target of "Skip to jobs" (focused by script only, so no focus ring of its own).
                tabIndex={-1}
                className={cn(
                  'min-h-0 flex-1 overflow-auto p-3 outline-none md:p-4',
                  docked && drawerOpen && showsTable && 'jobs-table-fit',
                )}
              >
                <SearchPausedBanner profile={profile} onResumed={() => void refresh({ board: false, profile: true })} />
                {board && allJobs.length > 0 ? <CalibrationBanner refreshKey={ratedOnBoard} /> : null}
                {worthOnly ? (
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <Chip>Worth a look: scored 5–6, no dealbreakers</Chip>
                    <Button size="sm" variant="ghost" onClick={() => setQueryParam('worth', null)}>
                      <X /> Show all
                    </Button>
                  </div>
                ) : null}
                {isPhone && board && allJobs.length > 0 && !(view === 'board' && !worthOnly) ? (
                  // Phone table: the stage filter that lived in the old menu (All + each stage).
                  <StageTabs
                    className="mb-3"
                    stages={board.stages}
                    counts={stageCounts}
                    allCount={allCount}
                    value={filterStage}
                    onChange={selectStage}
                  />
                ) : null}
                {!board ? (
                  loading ? (
                    <BoardSkeleton />
                  ) : (
                    <EmptyState
                      size="page"
                      icon={CloudOff}
                      title="Couldn’t load your jobs"
                      description="Check your internet, then try again."
                      action={
                        <Button variant="secondary" onClick={() => void refresh({ profile: true, notify: true })}>
                          <RefreshCw /> Try again
                        </Button>
                      }
                    />
                  )
                ) : allJobs.length === 0 ? (
                  <EmptyState
                    size="page"
                    icon={Inbox}
                    title="No jobs yet"
                    description="Your first search fills this board. Run it now, or wait for tomorrow morning’s automatic search."
                    action={
                      <>
                        <AutoSearchControls labelled onRunDone={() => void refresh({ profile: true, notify: true })} />
                        <Button size="sm" variant="ghost" onClick={() => navigate('/profile?tab=search')}>
                          Check search settings
                        </Button>
                      </>
                    }
                  />
                ) : view === 'board' && !worthOnly ? (
                  <>
                    <KanbanBoard
                      board={board}
                      setBoard={setBoard}
                      stages={phoneBoard ? [phoneLane] : visibleStages}
                      columns={filteredColumns}
                      searching={!!search}
                      onOpen={openJob}
                      onScoreSaved={onScoreSaved}
                      onMove={onBoardMove}
                      onReorder={(stage, next, revert) => void saveLaneOrder(stage, next, revert)}
                      phone={
                        phoneBoard
                          ? {
                              lane: phoneLane,
                              onLaneChange: selectStage,
                              counts: stageCounts,
                              leading: <ViewModeTabs value={view} onChange={setView} />,
                            }
                          : undefined
                      }
                    />
                  </>
                ) : (
                  <JobsTable
                    jobs={tableJobs}
                    stages={board.stages}
                    onOpen={openJobByUrl}
                    onScoreSaved={onScoreSaved}
                    onCardsChanged={applyCards}
                    searching={!!search}
                    toolbarStart={
                      <div className="md:hidden">
                        <ViewModeTabs value={view} onChange={setView} />
                      </div>
                    }
                  />
                )}
              </main>
            </div>
          )}
        </ErrorBoundary>

        <JobDrawer
          jobKey={jobId ?? null}
          onClose={closeDrawer}
          onChanged={() => void refresh()}
          onOpenJob={openJobId}
          preview={openPreview}
        />
        <DismissDialog
          open={!!closeTarget}
          jobTitle={closeTarget?.job.title}
          fromStage={closeTarget?.job.funnel_stage}
          onCancel={() => setCloseTarget(null)}
          onConfirm={onDismissConfirm}
        />
        <ManualAddModal
          open={showAdd}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false)
            void refresh({ notify: true })
          }}
        />
        <DailyBriefDialog
          open={showSchedule}
          onClose={() => setShowSchedule(false)}
          profile={profile}
          pendingCount={pendingNotify}
          onSaved={() => void refresh({ notify: true })}
        />

        {showTabBar ? <PhoneTabBar /> : null}
      </div>
    </>
  )
}

import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CloudOff, Inbox, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BoardResponse, JobCard, STAGE_LABELS } from '@/lib/api'
import { useBoard } from '@/lib/useBoard'
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
import { MobileNav, MobileNavProvider } from '@/components/MobileNav'
import { PageSkeleton } from '@/components/PageSkeleton'
import { StatusBanner } from '@/components/StatusBanner'
import { CalibrationBanner } from '@/components/CalibrationBanner'
import { SearchPausedBanner } from '@/components/SearchPausedBanner'
import { ViewModeTabs, type ViewMode } from '@/components/ViewModeTabs'

const ProfilePage = lazy(() => import('@/components/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const QualityPage = lazy(() => import('@/pages/QualityPage').then((m) => ({ default: m.QualityPage })))
const AdminPage = lazy(() => import('@/pages/AdminPage').then((m) => ({ default: m.AdminPage })))
const ReviewPage = lazy(() => import('@/pages/ReviewPage').then((m) => ({ default: m.ReviewPage })))

const VIEW_KEY = 'jobwright-view'

function jobMatchesQuery(job: JobCard, q: string): boolean {
  if (!q) return true
  const hay = [job.title, job.company, job.location, job.site].filter(Boolean).join(' ').toLowerCase()
  return hay.includes(q)
}

function isWorthALook(job: JobCard): boolean {
  const s = job.fit_score
  return job.funnel_stage === 'backlog' && s != null && s >= 5 && s <= 6 && !(job.dealbreakers || []).length
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
  const { board, setBoard, profile, pendingNotify, loading, refresh, refreshCard, moveCard, saveLaneOrder } = useBoard()
  const [view, setViewState] = useState<ViewMode>(initialView)
  const [showAdd, setShowAdd] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)
  const [closeTarget, setCloseTarget] = useState<CloseTarget | null>(null)
  const worthOnly = params.get('worth') === '1'

  // Stage filter and search live in the URL (?stage=prepare&q=design) so reload and shared links keep them.
  const stageParam = params.get('stage')
  const filterStage: string | 'all' = stageParam && STAGE_LABELS[stageParam] ? stageParam : 'all'

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

  const search = searchQuery.trim().toLowerCase()

  const allJobs = useMemo(() => (board ? board.stages.flatMap((s) => board.columns[s] || []) : []), [board])
  const ratedOnBoard = useMemo(() => allJobs.filter((j) => j.user_fit_score != null).length, [allJobs])

  function openJob(job: JobCard) {
    navigate(`/jobs/${job.job_id}${location.search}`)
  }

  function openJobByUrl(url: string) {
    const job = allJobs.find((j) => j.url === url)
    if (job) openJob(job)
  }

  function closeDrawer() {
    navigate(params.get('from') === 'review' ? '/review' : `/${location.search}`)
  }

  // One predicate for both views: search plus "worth a look".
  const visible = useCallback(
    (j: JobCard) => jobMatchesQuery(j, search) && (!worthOnly || isWorthALook(j)),
    [search, worthOnly],
  )

  const filteredColumns = useMemo(() => {
    if (!board) return {}
    const cols: Record<string, JobCard[]> = {}
    for (const stage of board.stages) cols[stage] = (board.columns[stage] || []).filter(visible)
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

  function openWhatsApp() {
    setShowSchedule(true)
    void refresh({ board: false, notify: true })
  }

  const drawerOpen = Boolean(jobId)
  const pageTitle = filterStage === 'all' ? 'All jobs' : STAGE_LABELS[filterStage] || filterStage

  return (
    <MobileNavProvider>
      <div className="relative flex h-full bg-background">
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
              <ProfilePage
                profile={profile}
                onBack={() => navigate('/')}
                onProfileChanged={() => void refresh({ board: false, profile: true, notify: true })}
              />
            </Suspense>
          ) : page === 'quality' ? (
            <Suspense fallback={<PageSkeleton />}>
              <QualityPage />
            </Suspense>
          ) : page === 'admin' ? (
            <Suspense fallback={<PageSkeleton />}>
              <AdminPage />
            </Suspense>
          ) : page === 'review' ? (
            <Suspense fallback={<PageSkeleton />}>
              <ReviewPage board={board} profile={profile} failed={!loading && !board} onChanged={() => void refresh({ profile: true })} />
            </Suspense>
          ) : (
            <div className={cn('flex min-w-0 flex-1 flex-col', drawerOpen && 'max-md:hidden')}>
              <StatusBanner />
              <BoardHeader
                title={pageTitle}
                count={board ? tableJobs.length : null}
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

              <main className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
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
                    <div className="sticky -top-3 left-0 z-10 -mx-3 -mt-3 mb-1 bg-background px-3 py-2 md:hidden">
                      <ViewModeTabs value={view} onChange={setView} />
                    </div>
                    <KanbanBoard
                      board={board}
                      setBoard={setBoard}
                      stages={visibleStages}
                      columns={filteredColumns}
                      searching={!!search}
                      onOpen={openJob}
                      onScoreSaved={onScoreSaved}
                      onMove={onBoardMove}
                      onReorder={(stage, next, revert) => void saveLaneOrder(stage, next, revert)}
                    />
                  </>
                ) : (
                  <JobsTable
                    jobs={tableJobs}
                    stages={board.stages}
                    onOpen={openJobByUrl}
                    onScoreSaved={onScoreSaved}
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

        <JobDrawer jobKey={jobId ?? null} onClose={closeDrawer} onChanged={() => void refresh()} />
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

        <MobileNav profile={profile} board={board} filterStage={filterStage} onFilterStage={selectStage} />
      </div>
    </MobileNavProvider>
  )
}

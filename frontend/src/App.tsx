import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  DndContext,
  DragCancelEvent,
  DragEndEvent,
  DragOverEvent,
  DragOverlay,
  DragStartEvent,
  MouseSensor,
  TouchSensor,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CloudOff, Gauge, Inbox, Plus, RefreshCw, Search, Shield, X } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  apiFetch,
  BoardResponse,
  JobCard,
  moveJob,
  previewNotify,
  Profile,
  STAGE_LABELS,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'
import { AppSidebar } from '@/components/AppSidebar'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { AutoSearchControls } from '@/components/AutoSearchControls'
import { Chip } from '@/components/Chip'
import { DailyBriefDialog } from '@/components/DailyBriefDialog'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { EmptyState } from '@/components/EmptyState'
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { JobCardView } from '@/components/JobCardView'
import { JobDrawer } from '@/components/JobDrawer'
import { JobsTable } from '@/components/JobsTable'
import { KanbanColumn } from '@/components/KanbanColumn'
import { ManualAddModal } from '@/components/ManualAddModal'
import { MobileNav, MobileNavProvider, MobileNavTrigger } from '@/components/MobileNav'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { StatusBanner } from '@/components/StatusBanner'
import { CalibrationBanner } from '@/components/CalibrationBanner'
import { ViewModeTabs, type ViewMode } from '@/components/ViewModeTabs'
import {
  createKanbanCollisionDetection,
  findJobStage,
  moveJobAcrossColumns,
  reorderWithinColumn,
} from '@/lib/boardDnD'

const ProfilePage = lazy(() => import('@/components/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const QualityPage = lazy(() => import('@/pages/QualityPage').then((m) => ({ default: m.QualityPage })))
const AdminPage = lazy(() => import('@/pages/AdminPage').then((m) => ({ default: m.AdminPage })))

function PageFallback() {
  return <div className="flex-1 p-6 text-sm text-muted-foreground">Loading…</div>
}

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

function BoardSearch({
  value,
  onChange,
  autoFocus,
  className,
}: {
  value: string
  onChange: (v: string) => void
  autoFocus?: boolean
  className?: string
}) {
  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input
        type="search"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onChange('')
        }}
        placeholder="Search title, company or place"
        className="pl-9 md:h-9"
        aria-label="Search jobs"
      />
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div aria-label="Loading your jobs" role="status" className="flex gap-3 overflow-hidden">
      {[0, 1, 2, 3, 4].map((col) => (
        <div key={col} className="w-full shrink-0 space-y-2 md:w-[17.5rem]">
          <Skeleton className="mx-1.5 my-2 h-4 w-24" />
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      ))}
    </div>
  )
}

type Page = 'board' | 'profile' | 'quality' | 'admin'

function pageFor(pathname: string): Page {
  if (pathname.startsWith('/profile')) return 'profile'
  if (pathname.startsWith('/quality')) return 'quality'
  if (pathname.startsWith('/admin')) return 'admin'
  return 'board'
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const { jobId } = useParams<{ jobId?: string }>()
  const { me } = useMe()
  const page = pageFor(location.pathname)
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [activeCard, setActiveCard] = useState<JobCard | null>(null)
  const [view, setViewState] = useState<ViewMode>(initialView)
  const [filterStage, setFilterStage] = useState<string | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)
  const [pendingNotify, setPendingNotify] = useState(0)
  const [loading, setLoading] = useState(true)
  const [closeTarget, setCloseTarget] = useState<JobCard | null>(null)
  const [dropTargetStage, setDropTargetStage] = useState<string | null>(null)
  const dragOriginStage = useRef<string | null>(null)
  const boardSnapshot = useRef<BoardResponse | null>(null)
  const worthOnly = params.get('worth') === '1'

  function setView(next: ViewMode) {
    localStorage.setItem(VIEW_KEY, next)
    setViewState(next)
  }

  const refresh = useCallback(async () => {
    try {
      const [b, p] = await Promise.all([apiFetch<BoardResponse>('/board'), apiFetch<Profile>('/profile')])
      setBoard(b)
      setProfile(p)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setLoading(false)
    }
    previewNotify()
      .then((r) => setPendingNotify(r.skipped ? 0 : r.jobs.length))
      .catch(() => setPendingNotify(0))
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (worthOnly) setViewState('table')
  }, [worthOnly])

  function selectStage(stage: string | 'all') {
    setFilterStage(stage)
    if (page !== 'board') navigate('/')
  }

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    // Long-press to drag on touch screens, so a normal swipe still scrolls.
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
  )

  const collisionDetection = useMemo(
    () => (board ? createKanbanCollisionDetection(board.stages, board.columns) : undefined),
    [board],
  )

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
    navigate(`/${location.search}`)
  }

  const filteredJobs = useMemo(
    () => allJobs.filter((j) => jobMatchesQuery(j, search) && (!worthOnly || isWorthALook(j))),
    [allJobs, search, worthOnly],
  )

  const filteredColumns = useMemo(() => {
    if (!board) return {}
    const cols: Record<string, JobCard[]> = {}
    for (const stage of board.stages) {
      cols[stage] = (board.columns[stage] || []).filter((j) => jobMatchesQuery(j, search))
    }
    return cols
  }, [board, search])

  const visibleStages = useMemo(() => {
    if (!board) return []
    if (filterStage === 'all') return board.stages
    return board.stages.filter((s) => s === filterStage)
  }, [board, filterStage])

  const tableJobs = useMemo(
    () => (filterStage === 'all' ? filteredJobs : filteredJobs.filter((j) => j.funnel_stage === filterStage)),
    [filteredJobs, filterStage],
  )

  async function completeMove(job: JobCard, toStage: string, opts?: { outcome?: string; reasons?: string[]; close_reason?: string }) {
    if (!board) return
    const prev = board
    const next: BoardResponse = {
      ...board,
      columns: Object.fromEntries(board.stages.map((s) => [s, [...(board.columns[s] || [])]])),
    }
    for (const stage of next.stages) {
      const idx = next.columns[stage].findIndex((j) => j.url === job.url)
      if (idx >= 0) {
        next.columns[stage].splice(idx, 1)
        break
      }
    }
    next.columns[toStage].unshift({ ...job, funnel_stage: toStage, ...(opts?.outcome ? { outcome: opts.outcome } : {}) })
    setBoard(next)
    try {
      await moveJob(job, toStage, opts)
      void refresh()
    } catch (e) {
      setBoard(prev)
      toast.error(errorMessage(e))
    }
  }

  async function moveCard(url: string, toStage: string, revertBoard?: BoardResponse | null) {
    const job = allJobs.find((j) => j.url === url)
    if (!job) return
    if (toStage === 'closed') {
      const before = revertBoard
        ? revertBoard.stages.flatMap((s) => revertBoard.columns[s] || []).find((j) => j.url === url)
        : undefined
      if (revertBoard) setBoard(revertBoard)
      setCloseTarget(before || job)
      return
    }
    await completeMove(job, toStage)
  }

  function onDragStart(event: DragStartEvent) {
    const url = String(event.active.id)
    setActiveCard(allJobs.find((j) => j.url === url) || null)
    if (board) {
      boardSnapshot.current = board
      dragOriginStage.current = findJobStage(url, board.stages, board.columns) || null
    }
  }

  function onDragOver(event: DragOverEvent) {
    const { active, over } = event
    if (!over || !board) return
    const overStage = findJobStage(String(over.id), board.stages, board.columns) || null
    setDropTargetStage(overStage)
    const next = moveJobAcrossColumns(board, String(active.id), String(over.id))
    if (next) setBoard(next)
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event
    setActiveCard(null)
    setDropTargetStage(null)
    const snapshot = boardSnapshot.current
    const originStage = dragOriginStage.current
    dragOriginStage.current = null
    boardSnapshot.current = null
    if (!board) return
    const url = String(active.id)
    let workingBoard = board
    if (over) {
      const reordered = reorderWithinColumn(board, url, String(over.id))
      if (reordered) {
        workingBoard = reordered
        setBoard(reordered)
      }
    }
    const currentStage = findJobStage(url, workingBoard.stages, workingBoard.columns)
    if (!currentStage || !originStage || currentStage === originStage) return
    void moveCard(url, currentStage, snapshot)
  }

  function onDragCancel(_event: DragCancelEvent) {
    setActiveCard(null)
    setDropTargetStage(null)
    if (boardSnapshot.current) setBoard(boardSnapshot.current)
    dragOriginStage.current = null
    boardSnapshot.current = null
  }

  const dropAnimation = useMemo(
    () => ({ sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }) }),
    [],
  )

  function onDismissConfirm(result: DismissResult) {
    const target = closeTarget
    setCloseTarget(null)
    if (!target) return
    void completeMove(target, 'closed', {
      outcome: result.outcome,
      reasons: result.reasons,
      close_reason: result.note || undefined,
    })
  }

  const drawerOpen = Boolean(jobId)
  const pageTitle = filterStage === 'all' ? 'All jobs' : STAGE_LABELS[filterStage] || filterStage

  const extraNav = (
    <>
      <SidebarActionButton
        active={page === 'quality'}
        icon={Gauge}
        label="Match quality"
        onClick={() => navigate('/quality')}
      />
      {me?.is_admin ? (
        <SidebarActionButton
          active={page === 'admin'}
          icon={Shield}
          label="Admin"
          onClick={() => navigate('/admin')}
        />
      ) : null}
    </>
  )

  return (
    <MobileNavProvider>
      <div className="relative flex h-full bg-background">
        <AppSidebar
          profile={profile}
          board={board}
          filterStage={filterStage}
          onFilterStage={selectStage}
          profileActive={page === 'profile'}
          onOpenProfile={() => navigate('/profile')}
          jobOpen={drawerOpen}
          extraActions={extraNav}
        />

        {page === 'profile' ? (
          <Suspense fallback={<PageFallback />}>
            <ProfilePage profile={profile} onBack={() => navigate('/')} onProfileChanged={() => void refresh()} />
          </Suspense>
        ) : page === 'quality' ? (
          <Suspense fallback={<PageFallback />}>
            <QualityPage />
          </Suspense>
        ) : page === 'admin' ? (
          <Suspense fallback={<PageFallback />}>
            <AdminPage />
          </Suspense>
        ) : (
          <div className={cn('flex min-w-0 flex-1 flex-col', drawerOpen && 'max-md:hidden')}>
            <StatusBanner />
            <header
              className={cn(
                'sticky top-0 z-20',
                APP_SHELL_HEADER,
                'max-md:h-14 max-md:flex-nowrap max-md:gap-1 max-md:px-2 max-md:py-0',
              )}
            >
              {searchOpen ? (
                <div className="flex min-w-0 flex-1 items-center gap-1 md:hidden">
                  <BoardSearch value={searchQuery} onChange={setSearchQuery} autoFocus className="flex-1" />
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setSearchQuery('')
                      setSearchOpen(false)
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              ) : null}
              <div className={cn('flex min-w-0 flex-1 items-center gap-1 md:gap-4', searchOpen && 'max-md:hidden')}>
                <MobileNavTrigger />
                <h1 className="min-w-0 truncate text-subheading text-foreground max-md:pl-1 md:text-heading">
                  {pageTitle}
                  {board ? (
                    <span className="ml-2 font-normal text-muted-foreground tabular-nums">{tableJobs.length}</span>
                  ) : null}
                </h1>
                <div className="max-md:hidden">
                  <ViewModeTabs value={view} onChange={setView} />
                </div>
                <BoardSearch value={searchQuery} onChange={setSearchQuery} className="w-64 max-md:hidden" />

                <div className="ml-auto flex shrink-0 items-center gap-0.5 md:gap-2">
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    className="md:hidden"
                    onClick={() => setSearchOpen(true)}
                    aria-label="Open search"
                  >
                    <Search />
                  </Button>

                  <AutoSearchControls onRunDone={() => void refresh()} />

                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    className="md:hidden"
                    onClick={() => setShowSchedule(true)}
                    aria-label={`Daily WhatsApp list${pendingNotify ? `, ${pendingNotify} waiting` : ''}`}
                  >
                    <WhatsAppIcon className="text-whatsapp" />
                    {pendingNotify > 0 ? (
                      <span className="absolute top-0 right-0 min-w-4 rounded-full bg-primary px-1 text-center text-micro leading-4 text-primary-foreground tabular-nums">
                        {pendingNotify}
                      </span>
                    ) : null}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="max-md:hidden"
                    onClick={() => setShowSchedule(true)}
                    title="Daily WhatsApp list"
                  >
                    <WhatsAppIcon className="text-whatsapp" />
                    WhatsApp
                    {pendingNotify > 0 ? <Badge variant="secondary">{pendingNotify}</Badge> : null}
                  </Button>

                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    className="md:hidden"
                    onClick={() => setShowAdd(true)}
                    aria-label="Add a job"
                  >
                    <Plus />
                  </Button>
                  <Button size="sm" variant="secondary" className="max-md:hidden" onClick={() => setShowAdd(true)}>
                    <Plus /> Add job
                  </Button>
                </div>
              </div>
            </header>

            <main className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
              {board && allJobs.length > 0 ? <CalibrationBanner refreshKey={ratedOnBoard} /> : null}
              {worthOnly ? (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Chip>Worth a look: scored 5–6, no dealbreakers</Chip>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      params.delete('worth')
                      setParams(params, { replace: true })
                    }}
                  >
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
                      <Button variant="secondary" onClick={() => void refresh()}>
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
                      <AutoSearchControls labelled onRunDone={() => void refresh()} />
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
                  <DndContext
                    sensors={sensors}
                    collisionDetection={collisionDetection}
                    onDragStart={onDragStart}
                    onDragOver={onDragOver}
                    onDragEnd={onDragEnd}
                    onDragCancel={onDragCancel}
                  >
                    <div className="-mx-3 flex h-full min-h-[70vh] gap-3 overflow-x-auto px-3 pb-2 md:mx-0 md:px-0">
                      {visibleStages.map((stage) => (
                        <KanbanColumn
                          key={stage}
                          stage={stage}
                          label={STAGE_LABELS[stage] || stage}
                          jobs={filteredColumns[stage] || []}
                          total={stage === 'closed' ? board.closed_total : undefined}
                          isDropTarget={dropTargetStage === stage}
                          isDragging={!!activeCard}
                          searching={!!search}
                          onOpen={openJob}
                          onScoreSaved={() => void refresh()}
                        />
                      ))}
                    </div>
                    <DragOverlay dropAnimation={dropAnimation}>
                      {activeCard ? (
                        <JobCardView job={activeCard} stage={dropTargetStage || activeCard.funnel_stage} dragging />
                      ) : null}
                    </DragOverlay>
                  </DndContext>
                </>
              ) : (
                <JobsTable
                  jobs={tableJobs}
                  stages={board.stages}
                  onOpen={openJobByUrl}
                  onScoreSaved={() => void refresh()}
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

        <JobDrawer jobKey={jobId ?? null} onClose={closeDrawer} onChanged={() => void refresh()} />
        <DismissDialog
          open={!!closeTarget}
          jobTitle={closeTarget?.title}
          fromStage={closeTarget?.funnel_stage}
          onCancel={() => setCloseTarget(null)}
          onConfirm={onDismissConfirm}
        />
        <ManualAddModal
          open={showAdd}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false)
            void refresh()
          }}
        />
        <DailyBriefDialog
          open={showSchedule}
          onClose={() => setShowSchedule(false)}
          profile={profile}
          pendingCount={pendingNotify}
          onSaved={() => void refresh()}
        />

        <MobileNav profile={profile} board={board} filterStage={filterStage} onFilterStage={selectStage} />
      </div>
    </MobileNavProvider>
  )
}

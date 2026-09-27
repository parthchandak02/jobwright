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
import { Gauge, Plus, Search, Shield, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import { WhatsAppIcon } from '@/components/WhatsAppIcon'
import { JobCardView } from '@/components/JobCardView'
import { JobDrawer } from '@/components/JobDrawer'
import { JobsTable } from '@/components/JobsTable'
import { KanbanColumn } from '@/components/KanbanColumn'
import { ManualAddModal } from '@/components/ManualAddModal'
import { MobileNav, MobileNavProvider, MobileNavTrigger } from '@/components/MobileNav'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { StatusBanner } from '@/components/StatusBanner'
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

/** Fresh backlog jobs just under the notify bar with no hard dealbreaker. */
function isWorthALook(job: JobCard): boolean {
  const s = job.fit_score
  return job.funnel_stage === 'backlog' && s != null && s >= 5 && s <= 6 && !(job.dealbreakers || []).length
}

function initialView(): ViewMode {
  const saved = localStorage.getItem(VIEW_KEY)
  if (saved === 'board' || saved === 'table') return saved
  return window.matchMedia('(max-width: 767px)').matches ? 'table' : 'board'
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
      if (revertBoard) setBoard(revertBoard)
      setCloseTarget(job)
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
            <header className={cn('sticky top-0 z-20', APP_SHELL_HEADER)}>
              <MobileNavTrigger />

              <ViewModeTabs value={view} onChange={setView} />

              <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2">
                <div className="relative w-full max-w-xs max-md:order-last sm:w-56">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search jobs…"
                    className="h-8 pl-8"
                    aria-label="Search jobs"
                  />
                </div>

                <AutoSearchControls onRunDone={() => void refresh()} />

                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setShowSchedule(true)}
                  title="Daily WhatsApp list"
                >
                  <WhatsAppIcon className="text-whatsapp" />
                  <span className="max-sm:sr-only">WhatsApp</span>
                  {pendingNotify > 0 ? ` (${pendingNotify})` : ''}
                </Button>

                <Button size="sm" variant="outline" onClick={() => setShowAdd(true)} aria-label="Add a job">
                  <Plus /> <span className="max-sm:sr-only">Add job</span>
                </Button>
              </div>
            </header>

            <main className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
              {worthOnly ? (
                <div className="mb-3 flex items-center gap-2">
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
                <p className="text-sm text-muted-foreground">
                  {loading ? 'Loading your jobs…' : 'Could not load your jobs. Refresh the page.'}
                </p>
              ) : allJobs.length === 0 ? (
                <div className="mx-auto mt-16 max-w-md space-y-3 text-center">
                  <h2 className="text-base font-semibold">No jobs yet</h2>
                  <p className="text-sm text-muted-foreground">
                    Your first search fills this board. Run it now, or wait for tomorrow morning’s automatic search.
                  </p>
                  <div className="flex justify-center gap-2">
                    <AutoSearchControls onRunDone={() => void refresh()} />
                    <Button size="sm" variant="outline" onClick={() => navigate('/profile?tab=search')}>
                      Check search settings
                    </Button>
                  </div>
                </div>
              ) : view === 'board' && !worthOnly ? (
                <DndContext
                  sensors={sensors}
                  collisionDetection={collisionDetection}
                  onDragStart={onDragStart}
                  onDragOver={onDragOver}
                  onDragEnd={onDragEnd}
                  onDragCancel={onDragCancel}
                >
                  <div className="flex h-full min-h-[70vh] gap-3 overflow-x-auto pb-2">
                    {visibleStages.map((stage) => (
                      <KanbanColumn
                        key={stage}
                        stage={stage}
                        label={STAGE_LABELS[stage] || stage}
                        jobs={filteredColumns[stage] || []}
                        total={stage === 'closed' ? board.closed_total : undefined}
                        isDropTarget={dropTargetStage === stage}
                        isDragging={!!activeCard}
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
              ) : (
                <JobsTable
                  jobs={tableJobs}
                  stages={board.stages}
                  onOpen={openJobByUrl}
                  onScoreSaved={() => void refresh()}
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

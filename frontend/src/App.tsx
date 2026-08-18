import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  DndContext,
  DragCancelEvent,
  DragEndEvent,
  DragOverEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import {
  CircleUser,
  Menu,
  MessageCircle,
  Plus,
  Search,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import {
  apiFetch,
  BoardResponse,
  JobCard,
  notifyWhatsApp,
  Profile,
  STAGE_LABELS,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'
import { AppSidebar } from '@/components/AppSidebar'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { AutoSearchDialog } from '@/components/AutoSearchDialog'
import { RunProgressButton } from '@/components/RunProgressButton'
import { useAutoSearch, STAGE_LABELS as AUTO_STAGE_LABELS } from '@/lib/useAutoSearch'
import { CloseJobDialog } from '@/components/CloseJobDialog'
import { JobCardView } from '@/components/JobCardView'
import { JobDrawer } from '@/components/JobDrawer'
import { JobsTable } from '@/components/JobsTable'
import { KanbanColumn } from '@/components/KanbanColumn'
import { ManualAddModal } from '@/components/ManualAddModal'
import { ProfilePage } from '@/components/ProfilePage'
import { SidebarActionButton } from '@/components/SidebarActionButton'
import { SidebarNav } from '@/components/SidebarNav'
import { ThemeToggle } from '@/components/ThemeToggle'
import { ViewModeTabs, type ViewMode } from '@/components/ViewModeTabs'
import {
  createKanbanCollisionDetection,
  findJobStage,
  moveJobAcrossColumns,
  reorderWithinColumn,
} from '@/lib/boardDnD'

function jobMatchesQuery(job: JobCard, q: string): boolean {
  if (!q) return true
  const hay = [job.title, job.company, job.location, job.site]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const { jobId } = useParams<{ jobId?: string }>()
  const profilePage = location.pathname === '/profile'
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null)
  const [activeCard, setActiveCard] = useState<JobCard | null>(null)
  const [view, setView] = useState<ViewMode>('board')
  const [filterStage, setFilterStage] = useState<string | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showAutoSearch, setShowAutoSearch] = useState(false)
  const [notifying, setNotifying] = useState(false)
  const [loading, setLoading] = useState(true)
  const resolvedJobId = useRef<string | null>(null)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [closeTarget, setCloseTarget] = useState<{ url: string; title: string | null } | null>(
    null,
  )
  const [dropTargetStage, setDropTargetStage] = useState<string | null>(null)
  const dragOriginStage = useRef<string | null>(null)
  const boardSnapshot = useRef<BoardResponse | null>(null)
  const refresh = useCallback(async () => {
    try {
      const [b, p] = await Promise.all([
        apiFetch<BoardResponse>('/board'),
        apiFetch<Profile>('/profile'),
      ])
      setBoard(b)
      setProfile(p)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const autoSearch = useAutoSearch(() => void refresh())

  function selectStage(stage: string | 'all') {
    setFilterStage(stage)
    if (profilePage) navigate('/')
  }

  function openProfile() {
    navigate('/profile')
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  const collisionDetection = useMemo(
    () => (board ? createKanbanCollisionDetection(board.stages, board.columns) : undefined),
    [board],
  )

  const search = searchQuery.trim().toLowerCase()

  const allJobs = useMemo(() => {
    if (!board) return []
    return board.stages.flatMap((s) => board.columns[s] || [])
  }, [board])

  function openJob(job: JobCard) {
    setSelectedUrl(job.url)
    if (job.job_id) {
      resolvedJobId.current = job.job_id
      navigate(`/jobs/${job.job_id}`)
    }
  }

  function openJobByUrl(url: string) {
    const job = allJobs.find((j) => j.url === url)
    if (job) openJob(job)
    else setSelectedUrl(url)
  }

  function closeDrawer() {
    setSelectedUrl(null)
    resolvedJobId.current = null
    if (jobId) navigate('/')
  }

  // Deep link: /jobs/:jobId opens the matching job drawer once the board loads.
  useEffect(() => {
    if (!jobId) {
      resolvedJobId.current = null
      return
    }
    if (resolvedJobId.current === jobId) return
    if (!board) return
    const match = allJobs.find((j) => j.job_id === jobId)
    if (match) {
      resolvedJobId.current = jobId
      setSelectedUrl(match.url)
      return
    }
    resolvedJobId.current = jobId
    apiFetch<JobCard>(`/jobs/by-id/${encodeURIComponent(jobId)}`)
      .then((j) => setSelectedUrl(j.url))
      .catch((e) => toast.error(errorMessage(e)))
  }, [jobId, board, allJobs])

  async function handleNotify() {
    setNotifying(true)
    try {
      const res = await notifyWhatsApp()
      if (res.skipped) {
        toast.info(res.message || 'No new jobs to notify')
      } else {
        toast.success(`Sent ${res.sent} jobs to WhatsApp`)
      }
      void refresh()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setNotifying(false)
    }
  }

  const filteredJobs = useMemo(
    () => allJobs.filter((j) => jobMatchesQuery(j, search)),
    [allJobs, search],
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

  const tableJobs = useMemo(() => {
    if (filterStage === 'all') return filteredJobs
    return filteredJobs.filter((j) => j.funnel_stage === filterStage)
  }, [filteredJobs, filterStage])

  async function completeMove(url: string, toStage: string, outcome?: string) {
    if (!board) return
    const prev = board
    const next: BoardResponse = {
      ...board,
      columns: Object.fromEntries(
        board.stages.map((s) => [s, [...(board.columns[s] || [])]]),
      ),
    }
    let moved: JobCard | undefined
    for (const stage of next.stages) {
      const idx = next.columns[stage].findIndex((j) => j.url === url)
      if (idx >= 0) {
        moved = {
          ...next.columns[stage][idx],
          funnel_stage: toStage,
          ...(outcome ? { outcome } : {}),
        }
        next.columns[stage].splice(idx, 1)
        break
      }
    }
    if (!moved) return

    next.columns[toStage].unshift(moved)
    setBoard(next)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(url)}/move`, {
        method: 'POST',
        body: JSON.stringify({
          to_stage: toStage,
          ...(outcome ? { outcome } : {}),
        }),
      })
      void refresh()
    } catch (e) {
      setBoard(prev)
      toast.error(errorMessage(e))
    }
  }

  async function moveCard(url: string, toStage: string, revertBoard?: BoardResponse | null) {
    if (!board) return
    let job: JobCard | undefined
    for (const stage of board.stages) {
      job = board.columns[stage]?.find((j) => j.url === url)
      if (job) break
    }
    if (!job) return

    if (toStage === 'closed' && !job.outcome) {
      if (revertBoard) setBoard(revertBoard)
      setCloseTarget({ url, title: job.title })
      return
    }

    await completeMove(url, toStage)
  }

  function onDragStart(event: DragStartEvent) {
    const url = String(event.active.id)
    const card = allJobs.find((j) => j.url === url)
    setActiveCard(card || null)
    if (board) {
      boardSnapshot.current = board
      dragOriginStage.current = findJobStage(url, board.stages, board.columns) || null
    }
  }

  function onDragOver(event: DragOverEvent) {
    const { active, over } = event
    if (!over || !board) return

    const activeId = String(active.id)
    const overId = String(over.id)
    const overStage = findJobStage(overId, board.stages, board.columns) || null
    setDropTargetStage(overStage)

    const next = moveJobAcrossColumns(board, activeId, overId)
    if (next) setBoard(next)
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event
    setActiveCard(null)
    setDropTargetStage(null)

    if (!board) {
      dragOriginStage.current = null
      boardSnapshot.current = null
      return
    }

    const url = String(active.id)
    const originStage = dragOriginStage.current
    const snapshot = boardSnapshot.current
    dragOriginStage.current = null
    boardSnapshot.current = null

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
    () => ({
      sideEffects: defaultDropAnimationSideEffects({
        styles: { active: { opacity: '0.4' } },
      }),
    }),
    [],
  )

  return (
    <div className="relative flex h-full bg-background">
      <AppSidebar
        profile={profile}
        board={board}
        filterStage={filterStage}
        onFilterStage={selectStage}
        profileActive={profilePage}
        onOpenProfile={openProfile}
        jobOpen={Boolean(selectedUrl)}
      />

      {profilePage ? (
        <ProfilePage
          profile={profile}
          onBack={() => navigate('/')}
          onProfileChanged={() => void refresh()}
        />
      ) : (
      <div className="flex min-w-0 flex-1 flex-col">
        <header className={cn('sticky top-0 z-20', APP_SHELL_HEADER)}>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            onClick={() => setMobileNavOpen(true)}
            title="Open filters"
            aria-label="Open stage filters"
            className="md:hidden"
          >
            <Menu />
          </Button>

          <ViewModeTabs value={view} onChange={setView} />

          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2">
            <div className="relative w-full max-w-xs sm:w-56">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search jobs…"
                className="h-8 pl-8"
                aria-label="Search jobs"
              />
            </div>

            <RunProgressButton
              run={autoSearch}
              idleLabel="Auto Search"
              stageLabels={AUTO_STAGE_LABELS}
              titleIdle="Run auto search"
              titleActive="Auto search in progress. Click to view logs"
              onClick={() => {
                autoSearch.start()
                setShowAutoSearch(true)
              }}
            />

            <Button
              size="sm"
              variant="outline"
              disabled={notifying}
              onClick={() => void handleNotify()}
            >
              <MessageCircle /> Notify WhatsApp
            </Button>

            <Button size="sm" variant="outline" onClick={() => setShowAdd(true)}>
              <Plus /> Add job
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
          {loading && !board ? (
            <p className="text-sm text-muted-foreground">Loading board…</p>
          ) : view === 'board' && board ? (
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
                    isDropTarget={dropTargetStage === stage}
                    isDragging={!!activeCard}
                    onOpen={(j) => openJob(j)}
                    onScoreSaved={() => void refresh()}
                  />
                ))}
              </div>
              <DragOverlay dropAnimation={dropAnimation}>
                {activeCard ? (
                  <JobCardView
                    job={activeCard}
                    stage={dropTargetStage || activeCard.funnel_stage}
                    dragging
                  />
                ) : null}
              </DragOverlay>
            </DndContext>
          ) : (
            <JobsTable
              jobs={tableJobs}
              stages={board?.stages ?? []}
              onOpen={openJobByUrl}
              onScoreSaved={() => void refresh()}
            />
          )}
        </main>
      </div>
      )}

      <JobDrawer
        jobUrl={selectedUrl}
        onClose={closeDrawer}
        onChanged={() => void refresh()}
        onRequestClose={(url, title) => setCloseTarget({ url, title })}
      />
      <CloseJobDialog
        open={!!closeTarget}
        jobTitle={closeTarget?.title}
        onCancel={() => setCloseTarget(null)}
        onConfirm={(outcome) => {
          const target = closeTarget
          setCloseTarget(null)
          if (!target) return
          void completeMove(target.url, 'closed', outcome)
        }}
      />
      <ManualAddModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onCreated={() => {
          setShowAdd(false)
          void refresh()
        }}
      />
      <AutoSearchDialog
        open={showAutoSearch}
        onClose={() => setShowAutoSearch(false)}
        run={autoSearch}
      />

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="flex w-64 flex-col gap-0 p-0">
          <SheetHeader className="border-b px-4 py-4 text-left">
            <SheetTitle className="text-sm">Stages</SheetTitle>
            <p className="text-xs font-normal text-muted-foreground">
              {profile?.name || profile?.user_id || '…'}
            </p>
          </SheetHeader>
          <SidebarNav
            className="min-h-0 flex-1 overflow-y-auto"
            profile={profile}
            board={board}
            filterStage={filterStage}
            onFilterStage={(s) => {
              selectStage(s)
              setMobileNavOpen(false)
            }}
            onNavigate={() => setMobileNavOpen(false)}
          />
          <div className="mt-auto flex flex-col gap-0.5 border-t border-border p-2">
            <SidebarActionButton
              active={profilePage}
              icon={CircleUser}
              label={profile?.name || profile?.user_id || 'Profile'}
              onClick={() => {
                openProfile()
                setMobileNavOpen(false)
              }}
            />
            <ThemeToggle />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}

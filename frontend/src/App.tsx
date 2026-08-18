import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  Columns3,
  LayoutList,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Search,
  Terminal,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  apiFetch,
  BoardResponse,
  JobCard,
  Profile,
  STAGE_LABELS,
} from '@/lib/api'
import { errorMessage } from '@/lib/utils'
import { AppSidebar } from '@/components/AppSidebar'
import { CloseJobDialog } from '@/components/CloseJobDialog'
import { JobCardView } from '@/components/JobCardView'
import { JobDrawer } from '@/components/JobDrawer'
import { JobsTable } from '@/components/JobsTable'
import { KanbanColumn } from '@/components/KanbanColumn'
import { ManualAddModal } from '@/components/ManualAddModal'
import { RunConsole } from '@/components/RunConsole'
import { SidebarNav } from '@/components/SidebarNav'
import { ThemeToggle } from '@/components/ThemeToggle'

type ViewMode = 'board' | 'table'

const SIDEBAR_KEY = 'jobwright-sidebar'
const SIDEBAR_AUTO_COLLAPSE_MQ = '(max-width: 1023px)'

function readSidebarCollapsed(): boolean {
  try {
    const v = localStorage.getItem(SIDEBAR_KEY)
    if (v === 'collapsed') return true
    if (v === 'open') return false
  } catch {
    /* ignore */
  }
  return typeof window !== 'undefined' && window.matchMedia(SIDEBAR_AUTO_COLLAPSE_MQ).matches
}

function jobMatchesQuery(job: JobCard, q: string): boolean {
  if (!q) return true
  const hay = [job.title, job.company, job.location, job.site]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

export default function App() {
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null)
  const [activeCard, setActiveCard] = useState<JobCard | null>(null)
  const [view, setView] = useState<ViewMode>('board')
  const [filterStage, setFilterStage] = useState<string | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showRun, setShowRun] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [closeTarget, setCloseTarget] = useState<{ url: string; title: string | null } | null>(
    null,
  )
  const [sidebarManual, setSidebarManual] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) !== null
    } catch {
      return false
    }
  })

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

  useEffect(() => {
    const mq = window.matchMedia(SIDEBAR_AUTO_COLLAPSE_MQ)
    const onChange = () => {
      if (sidebarManual) return
      setSidebarCollapsed(mq.matches)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [sidebarManual])

  useEffect(() => {
    if (selectedUrl) setSidebarCollapsed(true)
  }, [selectedUrl])

  function toggleSidebar() {
    setSidebarManual(true)
    setSidebarCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'open')
      } catch {
        /* ignore */
      }
      return next
    })
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  )

  const search = searchQuery.trim().toLowerCase()

  const allJobs = useMemo(() => {
    if (!board) return []
    return board.stages.flatMap((s) => board.columns[s] || [])
  }, [board])

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

  const statsLine = useMemo(() => {
    if (loading) return 'Loading…'
    const total = board?.total ?? 0
    const shown = filteredJobs.length
    const base =
      search && shown !== total
        ? `${shown} of ${total} jobs`
        : `${total} jobs`
    return `${base} · ${profile?.stats.scored ?? 0} scored · ${profile?.stats.tailored ?? 0} tailored`
  }, [loading, board?.total, filteredJobs.length, search, profile])

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

  async function moveCard(url: string, toStage: string) {
    if (!board) return
    const job = allJobs.find((j) => j.url === url)
    if (!job) return

    if (toStage === 'closed' && !job.outcome) {
      setCloseTarget({ url, title: job.title })
      return
    }

    await completeMove(url, toStage)
  }

  function onDragEnd(event: DragEndEvent) {
    setActiveCard(null)
    const { active, over } = event
    if (!over || !board) return
    const url = String(active.id)
    const overId = String(over.id)
    const toStage = board.stages.includes(overId)
      ? overId
      : allJobs.find((j) => j.url === overId)?.funnel_stage
    if (!toStage) return
    const from = allJobs.find((j) => j.url === url)?.funnel_stage
    if (from === toStage) return
    void moveCard(url, toStage)
  }

  return (
    <div className="flex h-full bg-background">
      <AppSidebar
        profile={profile}
        board={board}
        filterStage={filterStage}
        onFilterStage={setFilterStage}
        collapsed={sidebarCollapsed}
        onProfileChanged={() => void refresh()}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-border/40 bg-background/70 px-4 py-3 backdrop-blur-xl">
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
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="hidden md:inline-flex"
          >
            {sidebarCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold tracking-tight">Application board</h1>
            <p className="truncate text-xs text-muted-foreground">{statsLine}</p>
          </div>

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

          <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
            <TabsList>
              <TabsTrigger value="board" className="gap-1.5">
                <Columns3 className="size-3.5" /> Board
              </TabsTrigger>
              <TabsTrigger value="table" className="gap-1.5">
                <LayoutList className="size-3.5" /> Table
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="flex flex-wrap items-center gap-2">
            <ThemeToggle />
            <Button size="sm" variant="outline" onClick={() => setShowAdd(true)}>
              <Plus /> Add job
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowRun(true)}>
              <Terminal /> Run
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void refresh()}>
              <RefreshCw /> Refresh
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
          {loading && !board ? (
            <p className="text-sm text-muted-foreground">Loading board…</p>
          ) : view === 'board' && board ? (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCorners}
              onDragStart={(e) => {
                const card = allJobs.find((j) => j.url === String(e.active.id))
                setActiveCard(card || null)
              }}
              onDragEnd={onDragEnd}
              onDragCancel={() => setActiveCard(null)}
            >
              <div className="flex h-full min-h-[70vh] gap-3 overflow-x-auto pb-2">
                {visibleStages.map((stage) => (
                  <KanbanColumn
                    key={stage}
                    stage={stage}
                    label={STAGE_LABELS[stage] || stage}
                    jobs={filteredColumns[stage] || []}
                    onOpen={(j) => setSelectedUrl(j.url)}
                  />
                ))}
              </div>
              <DragOverlay>
                {activeCard ? <JobCardView job={activeCard} dragging /> : null}
              </DragOverlay>
            </DndContext>
          ) : (
            <JobsTable jobs={tableJobs} onOpen={setSelectedUrl} />
          )}
        </main>
      </div>

      <JobDrawer
        jobUrl={selectedUrl}
        applyEnabled={!!profile?.apply_enabled}
        onClose={() => setSelectedUrl(null)}
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
      <RunConsole
        open={showRun}
        applyEnabled={!!profile?.apply_enabled}
        onClose={() => setShowRun(false)}
        onDone={() => void refresh()}
      />

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-64 gap-0 p-0">
          <SheetHeader className="border-b px-4 py-4 text-left">
            <SheetTitle className="text-sm">Stages</SheetTitle>
            <p className="text-xs font-normal text-muted-foreground">
              {profile?.name || profile?.user_id || '…'}
            </p>
          </SheetHeader>
          <SidebarNav
            profile={profile}
            board={board}
            filterStage={filterStage}
            onFilterStage={setFilterStage}
            onNavigate={() => setMobileNavOpen(false)}
          />
        </SheetContent>
      </Sheet>
    </div>
  )
}

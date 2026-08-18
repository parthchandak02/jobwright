import { useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Building2,
  Filter,
  MapPin,
  X,
} from 'lucide-react'
import { JobCardView } from '@/components/JobCardView'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { ScoreEditor } from '@/components/ScoreEditor'
import { StageBadge } from '@/components/StageBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { FUNNEL_STAGES, JobCard, STAGE_LABELS } from '@/lib/api'
import {
  applyColumnFilters,
  countActiveFilters,
  DEFAULT_COLUMN_FILTERS,
  sortJobs,
  type ColumnFilters,
  type SortKey,
  uniqueValues,
} from '@/lib/jobListFilters'
import { cn } from '@/lib/utils'

type Props = {
  jobs: JobCard[]
  stages: string[]
  onOpen: (url: string) => void
  onScoreSaved?: () => void
}

const SORT_LABELS: Record<SortKey, string> = {
  'score-desc': 'Score (high first)',
  'score-asc': 'Score (low first)',
  'title-asc': 'Title (A-Z)',
  'title-desc': 'Title (Z-A)',
  'company-asc': 'Company (A-Z)',
  stage: 'Stage order',
}

function FilterChip({
  label,
  onClear,
}: {
  label: string
  onClear: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="inline-flex min-h-9 shrink-0 items-center gap-1 rounded-full border border-border/70 bg-muted/50 px-3 py-1 text-xs font-medium text-foreground"
    >
      {label}
      <X className="size-3 opacity-60" aria-hidden />
    </button>
  )
}

function ColumnFilterButton({
  active,
  children,
  label,
}: {
  active: boolean
  children: ReactNode
  label: string
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          className={cn('size-7 shrink-0', active && 'bg-accent text-accent-foreground')}
          aria-label={`Filter ${label}`}
        >
          <Filter className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 space-y-2 p-3">
        <p className="text-xs font-semibold text-muted-foreground">Filter {label}</p>
        {children}
      </PopoverContent>
    </Popover>
  )
}

function ColumnHead({
  label,
  sort,
  filter,
}: {
  label: string
  sort?: {
    active: boolean
    direction?: 'asc' | 'desc'
    onClick: () => void
  }
  filter?: ReactNode
}) {
  const SortIcon = sort?.active
    ? sort.direction === 'asc'
      ? ArrowUp
      : ArrowDown
    : ArrowUpDown
  return (
    <div className="jobs-table-head">
      {sort ? (
        <button type="button" className="jobs-table-sort" onClick={sort.onClick}>
          <span className="min-w-0 truncate">{label}</span>
          <SortIcon
            className={cn(
              'size-3.5 shrink-0',
              sort.active ? 'text-foreground' : 'text-muted-foreground',
            )}
            aria-hidden
          />
        </button>
      ) : (
        <span className="jobs-table-label">
          <span className="min-w-0 truncate">{label}</span>
        </span>
      )}
      {filter ? <span className="shrink-0">{filter}</span> : null}
    </div>
  )
}

function sortAria(
  active: boolean,
  direction?: 'asc' | 'desc',
): 'none' | 'ascending' | 'descending' {
  if (!active) return 'none'
  return direction === 'asc' ? 'ascending' : 'descending'
}

function FiltersPanel({
  filters,
  setFilters,
  stages,
  sources,
  workModels,
  className,
}: {
  filters: ColumnFilters
  setFilters: Dispatch<SetStateAction<ColumnFilters>>
  stages: string[]
  sources: string[]
  workModels: string[]
  className?: string
}) {
  return (
    <div className={cn('space-y-4', className)}>
      <div className="space-y-1.5">
        <Label htmlFor="filter-title">Title</Label>
        <Input
          id="filter-title"
          value={filters.title}
          onChange={(e) => setFilters((f) => ({ ...f, title: e.target.value }))}
          placeholder="Contains…"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-company">Company</Label>
        <Input
          id="filter-company"
          value={filters.company}
          onChange={(e) => setFilters((f) => ({ ...f, company: e.target.value }))}
          placeholder="Contains…"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-location">Location</Label>
        <Input
          id="filter-location"
          value={filters.location}
          onChange={(e) => setFilters((f) => ({ ...f, location: e.target.value }))}
          placeholder="Contains…"
        />
      </div>
      <div className="space-y-1.5">
        <Label>Min score</Label>
        <Select
          value={filters.scoreMin == null ? 'any' : String(filters.scoreMin)}
          onValueChange={(v) =>
            setFilters((f) => ({ ...f, scoreMin: v === 'any' ? null : Number(v) }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Any score" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any score</SelectItem>
            {[6, 7, 8, 9].map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n}+ only
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {stages.length > 1 ? (
        <div className="space-y-2">
          <Label>Stage</Label>
          <div className="flex flex-wrap gap-1.5">
            {stages.map((stage) => {
              const selected = filters.stages.includes(stage)
              return (
                <button
                  key={stage}
                  type="button"
                  onClick={() =>
                    setFilters((f) => ({
                      ...f,
                      stages: selected
                        ? f.stages.filter((s) => s !== stage)
                        : [...f.stages, stage],
                    }))
                  }
                  className={cn(selected && 'ring-2 ring-ring ring-offset-1 ring-offset-background')}
                >
                  <StageBadge stage={stage} />
                </button>
              )
            })}
          </div>
        </div>
      ) : null}
      <div className="space-y-1.5">
        <Label>Work model</Label>
        <Select
          value={filters.workModel || 'any'}
          onValueChange={(v) => setFilters((f) => ({ ...f, workModel: v === 'any' ? '' : v }))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any</SelectItem>
            {workModels.map((m) => (
              <SelectItem key={m} value={m}>
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Source</Label>
        <Select
          value={filters.source || 'any'}
          onValueChange={(v) => setFilters((f) => ({ ...f, source: v === 'any' ? '' : v }))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any</SelectItem>
            {sources.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Materials</Label>
        <Select
          value={filters.materials}
          onValueChange={(v) =>
            setFilters((f) => ({ ...f, materials: v as ColumnFilters['materials'] }))
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any</SelectItem>
            <SelectItem value="resume">Has resume</SelectItem>
            <SelectItem value="cover">Has cover letter</SelectItem>
            <SelectItem value="both">Has both</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

export function JobsTable({ jobs, stages, onOpen, onScoreSaved }: Props) {
  const [filters, setFilters] = useState<ColumnFilters>(DEFAULT_COLUMN_FILTERS)
  const [sort, setSort] = useState<SortKey>('score-desc')
  const [filtersOpen, setFiltersOpen] = useState(false)

  const sources = useMemo(() => uniqueValues(jobs, 'source'), [jobs])
  const workModels = useMemo(() => uniqueValues(jobs, 'work_model'), [jobs])
  const stageOptions = stages.length > 0 ? stages : [...FUNNEL_STAGES]

  const displayJobs = useMemo(
    () => sortJobs(applyColumnFilters(jobs, filters), sort),
    [jobs, filters, sort],
  )

  const activeFilterCount = countActiveFilters(filters)

  function toggleSort(column: 'score' | 'title' | 'company' | 'stage') {
    setSort((prev) => {
      if (column === 'score') return prev === 'score-desc' ? 'score-asc' : 'score-desc'
      if (column === 'title') return prev === 'title-asc' ? 'title-desc' : 'title-asc'
      if (column === 'company') return 'company-asc'
      return 'stage'
    })
  }

  function clearFilters() {
    setFilters(DEFAULT_COLUMN_FILTERS)
  }

  const filterChips = useMemo(() => {
    const chips: { label: string; onClear: () => void }[] = []
    if (filters.scoreMin != null) {
      chips.push({
        label: `Score ${filters.scoreMin}+`,
        onClear: () => setFilters((f) => ({ ...f, scoreMin: null })),
      })
    }
    if (filters.title.trim()) {
      chips.push({
        label: `Title: ${filters.title.trim()}`,
        onClear: () => setFilters((f) => ({ ...f, title: '' })),
      })
    }
    if (filters.company.trim()) {
      chips.push({
        label: `Company: ${filters.company.trim()}`,
        onClear: () => setFilters((f) => ({ ...f, company: '' })),
      })
    }
    if (filters.location.trim()) {
      chips.push({
        label: `Location: ${filters.location.trim()}`,
        onClear: () => setFilters((f) => ({ ...f, location: '' })),
      })
    }
    for (const stage of filters.stages) {
      chips.push({
        label: STAGE_LABELS[stage] || stage,
        onClear: () => setFilters((f) => ({ ...f, stages: f.stages.filter((s) => s !== stage) })),
      })
    }
    if (filters.workModel) {
      chips.push({
        label: filters.workModel,
        onClear: () => setFilters((f) => ({ ...f, workModel: '' })),
      })
    }
    if (filters.source) {
      chips.push({
        label: filters.source,
        onClear: () => setFilters((f) => ({ ...f, source: '' })),
      })
    }
    if (filters.materials !== 'any') {
      chips.push({
        label:
          filters.materials === 'both'
            ? 'Resume + cover'
            : filters.materials === 'resume'
              ? 'Has resume'
              : 'Has cover',
        onClear: () => setFilters((f) => ({ ...f, materials: 'any' })),
      })
    }
    return chips
  }, [filters])

  if (jobs.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-10 text-center shadow-sm">
        <p className="text-sm font-medium text-foreground">No jobs in this view</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Try another stage filter or run the pipeline to discover roles.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs text-muted-foreground">
          {displayJobs.length} of {jobs.length} jobs
        </p>
        <div className="ml-auto flex items-center gap-2">
          <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
            <SelectTrigger className="h-9 w-[11.5rem] md:hidden">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {SORT_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="md:hidden"
            onClick={() => setFiltersOpen(true)}
          >
            <Filter className="size-3.5" />
            Filters
            {activeFilterCount > 0 ? (
              <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-bold text-primary-foreground">
                {activeFilterCount}
              </span>
            ) : null}
          </Button>
          {activeFilterCount > 0 ? (
            <Button type="button" size="sm" variant="ghost" onClick={clearFilters}>
              Clear
            </Button>
          ) : null}
        </div>
      </div>

      {filterChips.length > 0 ? (
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {filterChips.map((chip) => (
            <FilterChip key={chip.label} label={chip.label} onClear={chip.onClear} />
          ))}
        </div>
      ) : null}

      {/* Mobile: card list (primary phone experience) */}
      <div className="flex flex-col gap-2.5 md:hidden">
        {displayJobs.length === 0 ? (
          <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
            No jobs match these filters.
          </div>
        ) : (
          displayJobs.map((job) => (
            <JobCardView
              key={job.url}
              job={job}
              stage={job.funnel_stage}
              onOpen={() => onOpen(job.url)}
              onScoreSaved={onScoreSaved}
            />
          ))
        )}
      </div>

      {/* Desktop: filterable table. All columns stay visible so col widths stay aligned; the wrapper scrolls. */}
      <div className="hidden overflow-hidden rounded-xl border bg-card shadow-sm md:block">
        <div className="overflow-x-auto">
          <table className="jobs-table">
            <colgroup>
              <col className="jobs-table-col-score" />
              <col className="jobs-table-col-title" />
              <col className="jobs-table-col-company" />
              <col className="jobs-table-col-location" />
              <col className="jobs-table-col-stage" />
              <col className="jobs-table-col-work" />
              <col className="jobs-table-col-source" />
              <col className="jobs-table-col-materials" />
            </colgroup>
            <thead className="sticky top-0 z-10 border-b bg-muted/80 text-muted-foreground backdrop-blur">
              <tr>
                <th
                  scope="col"
                  aria-sort={sortAria(
                    sort === 'score-desc' || sort === 'score-asc',
                    sort === 'score-asc' ? 'asc' : 'desc',
                  )}
                >
                  <ColumnHead
                    label="Score"
                    sort={{
                      active: sort === 'score-desc' || sort === 'score-asc',
                      direction: sort === 'score-asc' ? 'asc' : 'desc',
                      onClick: () => toggleSort('score'),
                    }}
                    filter={
                      <ColumnFilterButton active={filters.scoreMin != null} label="score">
                        <Select
                          value={filters.scoreMin == null ? 'any' : String(filters.scoreMin)}
                          onValueChange={(v) =>
                            setFilters((f) => ({
                              ...f,
                              scoreMin: v === 'any' ? null : Number(v),
                            }))
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            {[6, 7, 8, 9].map((n) => (
                              <SelectItem key={n} value={String(n)}>
                                {n}+
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th
                  scope="col"
                  aria-sort={sortAria(
                    sort === 'title-asc' || sort === 'title-desc',
                    sort === 'title-desc' ? 'desc' : 'asc',
                  )}
                >
                  <ColumnHead
                    label="Title"
                    sort={{
                      active: sort === 'title-asc' || sort === 'title-desc',
                      direction: sort === 'title-desc' ? 'desc' : 'asc',
                      onClick: () => toggleSort('title'),
                    }}
                    filter={
                      <ColumnFilterButton active={!!filters.title.trim()} label="title">
                        <Input
                          value={filters.title}
                          onChange={(e) => setFilters((f) => ({ ...f, title: e.target.value }))}
                          placeholder="Contains…"
                          className="h-8"
                        />
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th
                  scope="col"
                  aria-sort={sortAria(sort === 'company-asc', 'asc')}
                >
                  <ColumnHead
                    label="Company"
                    sort={{
                      active: sort === 'company-asc',
                      direction: 'asc',
                      onClick: () => toggleSort('company'),
                    }}
                    filter={
                      <ColumnFilterButton active={!!filters.company.trim()} label="company">
                        <Input
                          value={filters.company}
                          onChange={(e) => setFilters((f) => ({ ...f, company: e.target.value }))}
                          placeholder="Contains…"
                          className="h-8"
                        />
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th scope="col">
                  <ColumnHead
                    label="Location"
                    filter={
                      <ColumnFilterButton active={!!filters.location.trim()} label="location">
                        <Input
                          value={filters.location}
                          onChange={(e) => setFilters((f) => ({ ...f, location: e.target.value }))}
                          placeholder="Contains…"
                          className="h-8"
                        />
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th scope="col" aria-sort={sortAria(sort === 'stage', 'asc')}>
                  <ColumnHead
                    label="Stage"
                    sort={{
                      active: sort === 'stage',
                      direction: 'asc',
                      onClick: () => toggleSort('stage'),
                    }}
                    filter={
                      stageOptions.length > 1 ? (
                        <ColumnFilterButton active={filters.stages.length > 0} label="stage">
                          <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
                            {stageOptions.map((stage) => {
                              const selected = filters.stages.includes(stage)
                              return (
                                <button
                                  key={stage}
                                  type="button"
                                  onClick={() =>
                                    setFilters((f) => ({
                                      ...f,
                                      stages: selected
                                        ? f.stages.filter((s) => s !== stage)
                                        : [...f.stages, stage],
                                    }))
                                  }
                                  className={cn(
                                    selected &&
                                      'rounded-full ring-2 ring-ring ring-offset-1 ring-offset-background',
                                  )}
                                >
                                  <StageBadge stage={stage} />
                                </button>
                              )
                            })}
                          </div>
                        </ColumnFilterButton>
                      ) : undefined
                    }
                  />
                </th>
                <th scope="col">
                  <ColumnHead
                    label="Work"
                    filter={
                      <ColumnFilterButton active={!!filters.workModel} label="work model">
                        <Select
                          value={filters.workModel || 'any'}
                          onValueChange={(v) =>
                            setFilters((f) => ({ ...f, workModel: v === 'any' ? '' : v }))
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            {workModels.map((m) => (
                              <SelectItem key={m} value={m}>
                                {m.charAt(0).toUpperCase() + m.slice(1)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th scope="col">
                  <ColumnHead
                    label="Source"
                    filter={
                      <ColumnFilterButton active={!!filters.source} label="source">
                        <Select
                          value={filters.source || 'any'}
                          onValueChange={(v) =>
                            setFilters((f) => ({ ...f, source: v === 'any' ? '' : v }))
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            {sources.map((s) => (
                              <SelectItem key={s} value={s}>
                                {s}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ColumnFilterButton>
                    }
                  />
                </th>
                <th scope="col">
                  <ColumnHead
                    label="Materials"
                    filter={
                      <ColumnFilterButton active={filters.materials !== 'any'} label="materials">
                        <Select
                          value={filters.materials}
                          onValueChange={(v) =>
                            setFilters((f) => ({
                              ...f,
                              materials: v as ColumnFilters['materials'],
                            }))
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            <SelectItem value="resume">Resume</SelectItem>
                            <SelectItem value="cover">Cover</SelectItem>
                            <SelectItem value="both">Both</SelectItem>
                          </SelectContent>
                        </Select>
                      </ColumnFilterButton>
                    }
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              {displayJobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-muted-foreground">
                    No jobs match these filters.
                  </td>
                </tr>
              ) : (
                displayJobs.map((job) => (
                  <tr
                    key={job.url}
                    className="cursor-pointer border-t border-border/50 hover:bg-accent/30"
                    onClick={() => onOpen(job.url)}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <ScoreEditor job={job} onSaved={onScoreSaved} />
                    </td>
                    <td className="font-medium">
                      <span className="line-clamp-2 break-words">{job.title || 'Untitled'}</span>
                    </td>
                    <td className="text-muted-foreground">
                      <span className="flex min-w-0 items-center gap-1">
                        <Building2 className="size-3 shrink-0" aria-hidden />
                        <span className="truncate">{job.company || job.site || '—'}</span>
                      </span>
                    </td>
                    <td className="text-muted-foreground">
                      <span className="flex min-w-0 items-center gap-1">
                        <MapPin className="size-3 shrink-0" aria-hidden />
                        <span className="truncate">{job.location || '—'}</span>
                      </span>
                    </td>
                    <td>
                      <StageBadge stage={job.funnel_stage} />
                    </td>
                    <td>
                      <WorkModelBadge workModel={job.work_model} />
                    </td>
                    <td className="text-muted-foreground">
                      <span className="block truncate">{job.source}</span>
                    </td>
                    <td>
                      <div className="flex min-w-0 flex-wrap gap-1">
                        <JobMetaBadges job={job} />
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto rounded-t-2xl">
          <SheetHeader className="text-left">
            <SheetTitle>Filter jobs</SheetTitle>
          </SheetHeader>
          <FiltersPanel
            filters={filters}
            setFilters={setFilters}
            stages={stageOptions}
            sources={sources}
            workModels={workModels}
            className="mt-4 pb-6"
          />
          <div className="sticky bottom-0 flex gap-2 border-t bg-background py-3">
            <Button type="button" variant="outline" className="flex-1" onClick={clearFilters}>
              Clear all
            </Button>
            <Button type="button" className="flex-1" onClick={() => setFiltersOpen(false)}>
              Show {displayJobs.length} jobs
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}

import { useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Check, Filter, SearchX } from 'lucide-react'
import { Chip, ValueChip } from '@/components/Chip'
import { EmptyState } from '@/components/EmptyState'
import { JobCardView } from '@/components/JobCardView'
import { JobKeyChips } from '@/components/JobMetaBadges'
import { placeLine } from '@/components/JobSummary'
import { ScoreEditor } from '@/components/ScoreEditor'
import { StageBadge } from '@/components/StageBadge'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import { Badge } from '@/components/ui/badge'
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
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { FUNNEL_STAGES, JobCard, STAGE_LABELS, STAGE_TONE } from '@/lib/api'
import {
  applyColumnFilters,
  countActiveFilters,
  DEFAULT_COLUMN_FILTERS,
  sortJobs,
  suggestTextValues,
  type ColumnFilters,
  type SortKey,
  uniqueValues,
} from '@/lib/jobListFilters'
import { NAV_ICONS } from '@/lib/navIcons'
import { cn } from '@/lib/utils'

type Props = {
  jobs: JobCard[]
  stages: string[]
  onOpen: (url: string) => void
  onScoreSaved?: () => void
  toolbarStart?: ReactNode
  searching?: boolean
}

const SORT_LABELS: Record<SortKey, string> = {
  'score-desc': 'Best match first',
  'score-asc': 'Lowest score first',
  'title-asc': 'Title A–Z',
  'title-desc': 'Title Z–A',
  'company-asc': 'Company A–Z',
  stage: 'Stage',
}

const SORT_SHORT: Record<SortKey, string> = {
  'score-desc': 'Best match',
  'score-asc': 'Low score',
  'title-asc': 'Title A–Z',
  'title-desc': 'Title Z–A',
  'company-asc': 'Company',
  stage: 'Stage',
}

function StageToggle({ stage, selected, onToggle }: { stage: string; selected: boolean; onToggle: () => void }) {
  const Icon = NAV_ICONS[stage]
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onToggle}
      className="touch-target relative rounded-full"
    >
      {selected ? (
        <Chip icon={Check} tone={STAGE_TONE[stage]}>{STAGE_LABELS[stage] || stage}</Chip>
      ) : (
        <Chip icon={Icon}>{STAGE_LABELS[stage] || stage}</Chip>
      )}
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
        <p className="text-label text-foreground">Filter by {label}</p>
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

function SuggestInput({
  jobs,
  field,
  label,
  filters,
  setFilters,
  id,
}: {
  jobs: JobCard[]
  field: 'title' | 'company' | 'location'
  label: string
  filters: ColumnFilters
  setFilters: Dispatch<SetStateAction<ColumnFilters>>
  id: string
}) {
  const [focused, setFocused] = useState(false)
  const suggestions = useMemo(
    () => suggestTextValues(jobs, field, filters[field]),
    [jobs, field, filters[field]],
  )
  const showSuggestions = focused && suggestions.length > 0
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          value={filters[field]}
          onChange={(e) => setFilters((f) => ({ ...f, [field]: e.target.value }))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={`Type part of a ${label.toLowerCase()}`}
          autoComplete="off"
          inputMode="search"
          enterKeyHint="done"
        />
        {showSuggestions ? (
          <div className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-popover border bg-popover p-1 shadow-e1">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="block min-h-11 w-full truncate rounded-md px-3 py-2 text-left text-body hover:bg-surface-muted md:min-h-0"
                // onMouseDown fires before the input's onBlur, so the tap
                // registers instead of the sheet swallowing focus first.
                onMouseDown={(e) => {
                  e.preventDefault()
                  setFilters((f) => ({ ...f, [field]: s }))
                  setFocused(false)
                }}
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function FiltersPanel({
  filters,
  setFilters,
  stages,
  sources,
  workModels,
  jobs,
  className,
}: {
  filters: ColumnFilters
  setFilters: Dispatch<SetStateAction<ColumnFilters>>
  stages: string[]
  sources: string[]
  workModels: string[]
  jobs: JobCard[]
  className?: string
}) {
  return (
    <div className={cn('space-y-field', className)}>
      <SuggestInput
        jobs={jobs}
        field="title"
        label="Title"
        id="filter-title"
        filters={filters}
        setFilters={setFilters}
      />
      <SuggestInput
        jobs={jobs}
        field="company"
        label="Company"
        id="filter-company"
        filters={filters}
        setFilters={setFilters}
      />
      <SuggestInput
        jobs={jobs}
        field="location"
        label="Location"
        id="filter-location"
        filters={filters}
        setFilters={setFilters}
      />
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
          <div className="flex flex-wrap gap-2">
            {stages.map((stage) => {
              const selected = filters.stages.includes(stage)
              return (
                <StageToggle
                  key={stage}
                  stage={stage}
                  selected={selected}
                  onToggle={() =>
                    setFilters((f) => ({
                      ...f,
                      stages: selected ? f.stages.filter((s) => s !== stage) : [...f.stages, stage],
                    }))
                  }
                />
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

export function JobsTable({ jobs, stages, onOpen, onScoreSaved, toolbarStart, searching }: Props) {
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

  const multiStage = useMemo(() => new Set(jobs.map((j) => j.funnel_stage)).size > 1, [jobs])

  const noMatches = jobs.length === 0 ? (
    <EmptyState
      icon={SearchX}
      title={searching ? 'No jobs match your search' : 'No jobs in this view'}
      description={searching ? 'Try a different word, or clear the search.' : 'Pick another stage, or check back after the next daily search.'}
    />
  ) : (
    <EmptyState
      icon={SearchX}
      title="No jobs match these filters"
      description="Remove a filter to see more jobs."
      action={
        <Button type="button" size="sm" variant="secondary" onClick={clearFilters}>
          Clear filters
        </Button>
      }
    />
  )

  return (
    <div className="space-y-3">
      <div
        className={cn(
          'sticky -top-3 z-10 -mx-3 -mt-3 flex items-center gap-2 bg-background px-3 py-2 md:static md:mx-0 md:mt-0 md:px-0 md:py-0',
          activeFilterCount === 0 && 'md:hidden',
        )}
      >
        {toolbarStart}
        {activeFilterCount > 0 ? (
          <p className="hidden text-caption text-muted-foreground tabular-nums md:block">
            Showing {displayJobs.length} of {jobs.length} jobs
          </p>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
            <SelectTrigger className="w-auto gap-1.5 md:hidden" aria-label="Sort jobs">
              <ArrowUpDown className="size-4 text-muted-foreground" aria-hidden />
              <span>{SORT_SHORT[sort]}</span>
            </SelectTrigger>
            <SelectContent align="end">
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
            variant="secondary"
            className="md:hidden"
            onClick={() => setFiltersOpen(true)}
            aria-label={activeFilterCount ? `Filters, ${activeFilterCount} on` : 'Filters'}
          >
            <Filter />
            <span className="max-[359px]:sr-only">Filters</span>
            {activeFilterCount > 0 ? <Badge>{activeFilterCount}</Badge> : null}
          </Button>
          {activeFilterCount > 0 ? (
            <Button type="button" size="sm" variant="ghost" className="max-md:hidden" onClick={clearFilters}>
              Clear filters
            </Button>
          ) : null}
        </div>
      </div>

      {filterChips.length > 0 ? (
        <div className="scrollbar-none -mx-3 flex gap-2 overflow-x-auto px-3 md:mx-0 md:flex-wrap md:px-0">
          {filterChips.map((chip) => (
            <ValueChip key={chip.label} onRemove={chip.onClear} removeLabel={`filter ${chip.label}`} className="shrink-0">
              {chip.label}
            </ValueChip>
          ))}
        </div>
      ) : null}

      {activeFilterCount > 0 ? (
        <p className="text-caption text-muted-foreground tabular-nums md:hidden">
          Showing {displayJobs.length} of {jobs.length} jobs
        </p>
      ) : null}

      <div className="flex flex-col gap-2 md:hidden">
        {displayJobs.length === 0
          ? noMatches
          : displayJobs.map((job) => (
              <JobCardView
                key={job.url}
                job={job}
                stage={job.funnel_stage}
                showStage={multiStage}
                onOpen={() => onOpen(job.url)}
                onScoreSaved={onScoreSaved}
              />
            ))}
      </div>

      <div className="surface hidden overflow-hidden rounded-lg md:block">
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
            <thead className="border-b border-border bg-surface-muted text-caption text-muted-foreground">
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
                          <SelectTrigger className="h-9">
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
                          placeholder="Type to filter"
                          className="h-9"
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
                          placeholder="Type to filter"
                          className="h-9"
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
                          placeholder="Type to filter"
                          className="h-9"
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
                          <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto p-0.5">
                            {stageOptions.map((stage) => {
                              const selected = filters.stages.includes(stage)
                              return (
                                <StageToggle
                                  key={stage}
                                  stage={stage}
                                  selected={selected}
                                  onToggle={() =>
                                    setFilters((f) => ({
                                      ...f,
                                      stages: selected ? f.stages.filter((s) => s !== stage) : [...f.stages, stage],
                                    }))
                                  }
                                />
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
                          <SelectTrigger className="h-9">
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
                          <SelectTrigger className="h-9">
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
                          <SelectTrigger className="h-9">
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
                  <td colSpan={8}>{noMatches}</td>
                </tr>
              ) : (
                displayJobs.map((job) => (
                  <tr
                    key={job.url}
                    tabIndex={0}
                    aria-label={`Open ${job.title || 'job'} at ${job.company || 'unknown company'}`}
                    className="cursor-pointer border-t border-border transition-colors duration-(--dur-1) first:border-t-0 hover:bg-surface-muted"
                    onClick={() => onOpen(job.url)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.target === e.currentTarget) onOpen(job.url)
                    }}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <ScoreEditor job={job} onSaved={onScoreSaved} />
                    </td>
                    <td>
                      <span className="line-clamp-2 font-medium break-words text-foreground">{job.title || 'Untitled'}</span>
                      <span className="mt-1 flex flex-wrap gap-1.5 empty:hidden">
                        <JobKeyChips job={job} max={1} kinds={['alert', 'info']} />
                      </span>
                    </td>
                    <td className="text-muted-foreground">
                      <span className="block truncate">{job.company || job.site || '—'}</span>
                    </td>
                    <td className="text-muted-foreground">
                      <span className="block truncate" title={placeLine(job)}>
                        {job.location || 'Not stated'}
                      </span>
                    </td>
                    <td>
                      <StageBadge stage={job.funnel_stage} />
                    </td>
                    <td>
                      <WorkModelBadge workModel={job.work_model} />
                    </td>
                    <td className="text-muted-foreground">
                      <span className="block truncate capitalize">{job.source === 'manual' ? 'Added by you' : job.source}</span>
                    </td>
                    <td>
                      <div className="flex min-w-0 flex-wrap gap-1">
                        <JobKeyChips job={job} kinds={['materials']} />
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
        <SheetContent side="bottom" className="gap-0 overflow-y-auto">
          <SheetHeader className="pb-2 text-left">
            <SheetTitle>Filter jobs</SheetTitle>
            <SheetDescription>Only jobs that match every filter are shown.</SheetDescription>
          </SheetHeader>
          <FiltersPanel
            filters={filters}
            setFilters={setFilters}
            stages={stageOptions}
            sources={sources}
            workModels={workModels}
            jobs={jobs}
            className="px-4 pt-2 pb-6"
          />
          <div className="sticky bottom-0 flex gap-2 border-t border-border bg-popover px-4 py-3">
            <Button type="button" variant="secondary" className="flex-1" onClick={clearFilters}>
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

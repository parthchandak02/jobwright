import { useMemo, useState, type ReactNode } from 'react'
import { ArrowUpDown, Filter, SearchX } from 'lucide-react'
import { ValueChip } from '@/components/Chip'
import { EmptyState } from '@/components/EmptyState'
import { JobCardView } from '@/components/JobCardView'
import { FiltersSheet } from '@/components/jobs-table/FiltersSheet'
import { JobsTableHead, type SortColumn } from '@/components/jobs-table/JobsTableHead'
import { JobsTableRow } from '@/components/jobs-table/JobsTableRow'
import { useFilterChips } from '@/components/jobs-table/useFilterChips'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { FUNNEL_STAGES, type JobCard } from '@/lib/api'
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

function nextSort(prev: SortKey, column: SortColumn): SortKey {
  if (column === 'score') return prev === 'score-desc' ? 'score-asc' : 'score-desc'
  if (column === 'title') return prev === 'title-asc' ? 'title-desc' : 'title-asc'
  if (column === 'company') return 'company-asc'
  return 'stage'
}

export function JobsTable({ jobs, stages, onOpen, onScoreSaved, toolbarStart, searching }: Props) {
  const [filters, setFilters] = useState<ColumnFilters>(DEFAULT_COLUMN_FILTERS)
  const [sort, setSort] = useState<SortKey>('score-desc')
  const [filtersOpen, setFiltersOpen] = useState(false)

  const sources = useMemo(() => uniqueValues(jobs, 'source'), [jobs])
  const workModels = useMemo(() => uniqueValues(jobs, 'work_model'), [jobs])
  const stageOptions = stages.length > 0 ? stages : [...FUNNEL_STAGES]
  const displayJobs = useMemo(() => sortJobs(applyColumnFilters(jobs, filters), sort), [jobs, filters, sort])
  const activeFilterCount = countActiveFilters(filters)
  const filterChips = useFilterChips(filters, setFilters)
  const multiStage = useMemo(() => new Set(jobs.map((j) => j.funnel_stage)).size > 1, [jobs])

  const clearFilters = () => setFilters(DEFAULT_COLUMN_FILTERS)
  const shownText = `Showing ${displayJobs.length} of ${jobs.length} jobs`

  const noMatches =
    jobs.length === 0 ? (
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
          <p className="hidden text-caption text-muted-foreground tabular-nums md:block">{shownText}</p>
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

      {activeFilterCount > 0 ? <p className="text-caption text-muted-foreground tabular-nums md:hidden">{shownText}</p> : null}

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
            <JobsTableHead
              filters={filters}
              setFilters={setFilters}
              sort={sort}
              onSort={(column) => setSort((prev) => nextSort(prev, column))}
              stages={stageOptions}
              sources={sources}
              workModels={workModels}
            />
            <tbody>
              {displayJobs.length === 0 ? (
                <tr>
                  <td colSpan={8}>{noMatches}</td>
                </tr>
              ) : (
                displayJobs.map((job) => <JobsTableRow key={job.url} job={job} onOpen={onOpen} onScoreSaved={onScoreSaved} />)
              )}
            </tbody>
          </table>
        </div>
      </div>

      <FiltersSheet
        open={filtersOpen}
        onOpenChange={setFiltersOpen}
        shownCount={displayJobs.length}
        onClear={clearFilters}
        filters={filters}
        setFilters={setFilters}
        stages={stageOptions}
        sources={sources}
        workModels={workModels}
        jobs={jobs}
      />
    </div>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowUpDown, Filter, ListChecks, SearchX } from 'lucide-react'
import { ValueChip } from '@/components/Chip'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { EmptyState } from '@/components/EmptyState'
import { allBeforeApplying, BulkBar } from '@/components/jobs-table/BulkBar'
import { FiltersSheet } from '@/components/jobs-table/FiltersSheet'
import { JobsTableHead, type SortColumn } from '@/components/jobs-table/JobsTableHead'
import { JobsTableRow } from '@/components/jobs-table/JobsTableRow'
import { SelectableCard } from '@/components/jobs-table/SelectableCard'
import { useBulkActions } from '@/components/jobs-table/useBulkActions'
import { useFilterChips } from '@/components/jobs-table/useFilterChips'
import { useSelection } from '@/components/jobs-table/useSelection'
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
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

type Props = {
  jobs: JobCard[]
  stages: string[]
  onOpen: (url: string) => void
  onScoreSaved?: () => void
  toolbarStart?: ReactNode
  searching?: boolean
  /**
   * Turns on selection (checkboxes on desktop, "Select" on phones) and bulk
   * move / "Not for me". Called with the server's fresh cards after each bulk
   * action (and its undo) so the board can patch them in without a reload.
   */
  onCardsChanged?: (cards: JobCard[]) => void
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

function isTextField(el: EventTarget | null) {
  return el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))
}

export function JobsTable({ jobs, stages, onOpen, onScoreSaved, toolbarStart, searching, onCardsChanged }: Props) {
  const [filters, setFilters] = useState<ColumnFilters>(DEFAULT_COLUMN_FILTERS)
  const [sort, setSort] = useState<SortKey>('score-desc')
  const [filtersOpen, setFiltersOpen] = useState(false)
  // Phones get the card list, md+ the table: render only one (both at once doubled the DOM).
  const desktop = useMediaQuery('(min-width: 768px)')

  const sources = useMemo(() => uniqueValues(jobs, 'source'), [jobs])
  const workModels = useMemo(() => uniqueValues(jobs, 'work_model'), [jobs])
  const stageOptions = stages.length > 0 ? stages : [...FUNNEL_STAGES]
  const displayJobs = useMemo(() => sortJobs(applyColumnFilters(jobs, filters), sort), [jobs, filters, sort])
  const activeFilterCount = countActiveFilters(filters)
  const filterChips = useFilterChips(filters, setFilters)
  const multiStage = useMemo(() => new Set(jobs.map((j) => j.funnel_stage)).size > 1, [jobs])

  const selectable = Boolean(onCardsChanged)
  const selection = useSelection(displayJobs)
  // Phone only: tapping a card toggles it instead of opening it.
  const [selecting, setSelecting] = useState(false)
  const [closeOpen, setCloseOpen] = useState(false)
  const { clear: clearSelection } = selection
  const endSelection = useCallback(() => {
    clearSelection()
    setSelecting(false)
  }, [clearSelection])
  const bulk = useBulkActions(onCardsChanged, endSelection)
  const picked = selection.selectedJobs

  function onCloseConfirm(result: DismissResult) {
    setCloseOpen(false)
    void bulk.close(picked, result)
  }

  // With focus inside the desktop table: Cmd/Ctrl-A selects every shown row, Escape clears.
  const tableRef = useRef<HTMLDivElement>(null)
  const { selectAll, count: selectedCount } = selection
  useEffect(() => {
    const el = tableRef.current
    if (!el || !selectable) return
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (isTextField(e.target)) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        selectAll()
      } else if (e.key === 'Escape' && selectedCount > 0) {
        e.preventDefault()
        clearSelection()
      }
    }
    el.addEventListener('keydown', onKey)
    return () => el.removeEventListener('keydown', onKey)
  }, [desktop, selectable, selectAll, clearSelection, selectedCount])

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
        {selecting ? (
          <>
            <Button type="button" size="sm" variant="ghost" className="-ml-2" onClick={endSelection}>
              Done
            </Button>
            <p className="min-w-0 truncate text-caption text-muted-foreground">Tap jobs to select</p>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="-mr-2 ml-auto"
              onClick={selection.allState === true ? selection.clear : selection.selectAll}
              disabled={displayJobs.length === 0}
            >
              {selection.allState === true ? 'Select none' : 'Select all'}
            </Button>
          </>
        ) : (
          <>
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
                {/* Room for the Select button on phones: the funnel alone says Filters. */}
                <span className={selectable ? 'max-[419px]:sr-only' : 'max-[359px]:sr-only'}>Filters</span>
                {activeFilterCount > 0 ? <Badge>{activeFilterCount}</Badge> : null}
              </Button>
              {activeFilterCount > 0 ? (
                <Button type="button" size="sm" variant="ghost" className="max-md:hidden" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
              {selectable ? (
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  className="md:hidden"
                  onClick={() => setSelecting(true)}
                  disabled={displayJobs.length === 0}
                  aria-label="Select jobs"
                >
                  <ListChecks />
                </Button>
              ) : null}
            </div>
          </>
        )}
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

      {!desktop ? (
        <div className="flex flex-col gap-2">
          {/* Cards title themselves with h3; keep the outline h1 → h2 → h3. */}
          <h2 className="sr-only">Job list</h2>
          {displayJobs.length === 0
            ? noMatches
            : displayJobs.map((job) => (
                <SelectableCard
                  key={job.url}
                  job={job}
                  showStage={multiStage}
                  selecting={selecting}
                  selected={selection.isSelected(job)}
                  onOpen={onOpen}
                  onToggle={(j) => selection.toggle(j)}
                  onLongPress={
                    selectable
                      ? (j) => {
                          setSelecting(true)
                          if (!selection.isSelected(j)) selection.toggle(j)
                        }
                      : undefined
                  }
                  onScoreSaved={onScoreSaved}
                />
              ))}
        </div>
      ) : (
        <div ref={tableRef} className="surface overflow-hidden rounded-lg">
          <div className="overflow-x-auto">
            <table className="jobs-table">
              <colgroup>
                {selectable ? <col className="jobs-table-col-select" /> : null}
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
                selection={
                  selectable ? { state: selection.allState, shown: displayJobs.length, onToggleAll: selection.toggleAll } : undefined
                }
              />
              <tbody>
                {displayJobs.length === 0 ? (
                  <tr>
                    <td colSpan={selectable ? 9 : 8}>{noMatches}</td>
                  </tr>
      ) : (
                  displayJobs.map((job) => (
                    <JobsTableRow
                      key={job.url}
                      job={job}
                      onOpen={onOpen}
                      onScoreSaved={onScoreSaved}
                      selected={selection.isSelected(job)}
                      onToggleSelect={selectable ? selection.toggle : undefined}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

      {selectable ? (
        <>
          <p className="sr-only" aria-live="polite" aria-atomic="true">
            {selection.count > 0 ? `${selection.count} of ${displayJobs.length} jobs selected` : ''}
          </p>
          <BulkBar
            jobs={picked}
            busy={bulk.busy}
            onClear={endSelection}
            onMove={(stage) => void bulk.move(picked, stage)}
            onClose={() => setCloseOpen(true)}
          />
          <DismissDialog
            open={closeOpen}
            count={picked.length}
            jobTitle={picked.length === 1 ? picked[0].title : undefined}
            fromStage={allBeforeApplying(picked) ? 'backlog' : 'applied'}
            onCancel={() => setCloseOpen(false)}
            onConfirm={onCloseConfirm}
          />
        </>
      ) : null}
    </div>
  )
}

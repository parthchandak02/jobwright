import { Input } from '@/components/ui/input'
import type { SortKey } from '@/lib/jobListFilters'
import { ColumnFilterButton, ColumnHead } from './ColumnHead'
import { MaterialsSelect, ScoreMinSelect, SourceSelect, WorkModelSelect } from './FilterSelects'
import { StageToggles } from './StageToggle'
import type { FilterProps } from './types'

export type SortColumn = 'score' | 'title' | 'company' | 'stage'

type Props = FilterProps & {
  sort: SortKey
  onSort: (column: SortColumn) => void
  stages: string[]
  sources: string[]
  workModels: string[]
}

function TextFilter({ field, filters, setFilters }: FilterProps & { field: 'title' | 'company' | 'location' }) {
  return (
    <Input
      value={filters[field]}
      onChange={(e) => setFilters((f) => ({ ...f, [field]: e.target.value }))}
      placeholder="Type to filter"
      className="h-9"
    />
  )
}

/** Desktop table header: sortable columns, each with its own filter popover. */
export function JobsTableHead({ sort, onSort, stages, sources, workModels, ...fp }: Props) {
  const { filters } = fp
  const scoreSorted = sort === 'score-desc' || sort === 'score-asc'
  const titleSorted = sort === 'title-asc' || sort === 'title-desc'
  return (
    <thead className="border-b border-border bg-surface-muted text-caption text-muted-foreground">
      <tr>
        <ColumnHead
          label="Score"
          sort={{ active: scoreSorted, direction: sort === 'score-asc' ? 'asc' : 'desc', onClick: () => onSort('score') }}
          filter={
            <ColumnFilterButton active={filters.scoreMin != null} label="score">
              <ScoreMinSelect {...fp} variant="column" />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Title"
          sort={{ active: titleSorted, direction: sort === 'title-desc' ? 'desc' : 'asc', onClick: () => onSort('title') }}
          filter={
            <ColumnFilterButton active={!!filters.title.trim()} label="title">
              <TextFilter {...fp} field="title" />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Company"
          sort={{ active: sort === 'company-asc', direction: 'asc', onClick: () => onSort('company') }}
          filter={
            <ColumnFilterButton active={!!filters.company.trim()} label="company">
              <TextFilter {...fp} field="company" />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Location"
          filter={
            <ColumnFilterButton active={!!filters.location.trim()} label="location">
              <TextFilter {...fp} field="location" />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Stage"
          sort={{ active: sort === 'stage', direction: 'asc', onClick: () => onSort('stage') }}
          filter={
            stages.length > 1 ? (
              <ColumnFilterButton active={filters.stages.length > 0} label="stage">
                <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto p-0.5">
                  <StageToggles {...fp} stages={stages} />
                </div>
              </ColumnFilterButton>
            ) : undefined
          }
        />
        <ColumnHead
          label="Work"
          filter={
            <ColumnFilterButton active={!!filters.workModel} label="work model">
              <WorkModelSelect {...fp} variant="column" workModels={workModels} />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Source"
          filter={
            <ColumnFilterButton active={!!filters.source} label="source">
              <SourceSelect {...fp} variant="column" sources={sources} />
            </ColumnFilterButton>
          }
        />
        <ColumnHead
          label="Materials"
          filter={
            <ColumnFilterButton active={filters.materials !== 'any'} label="materials">
              <MaterialsSelect {...fp} variant="column" />
            </ColumnFilterButton>
          }
        />
      </tr>
    </thead>
  )
}

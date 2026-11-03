import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { JobCard } from '@/lib/api'
import { suggestTextValues } from '@/lib/jobListFilters'
import { MaterialsSelect, ScoreMinSelect, SourceSelect, WorkModelSelect } from './FilterSelects'
import { StageToggles } from './StageToggle'
import type { FilterProps } from './types'

function SuggestInput({
  jobs,
  field,
  label,
  filters,
  setFilters,
  id,
}: FilterProps & {
  jobs: JobCard[]
  field: 'title' | 'company' | 'location'
  label: string
  id: string
}) {
  const [focused, setFocused] = useState(false)
  const value = filters[field]
  const suggestions = useMemo(() => suggestTextValues(jobs, field, value), [jobs, field, value])
  const showSuggestions = focused && suggestions.length > 0
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          value={value}
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

type PanelProps = FilterProps & {
  stages: string[]
  sources: string[]
  workModels: string[]
  jobs: JobCard[]
}

function FiltersPanel({ filters, setFilters, stages, sources, workModels, jobs }: PanelProps) {
  const fp = { filters, setFilters }
  return (
    <div className="space-y-field px-4 pt-2 pb-6">
      <SuggestInput {...fp} jobs={jobs} field="title" label="Title" id="filter-title" />
      <SuggestInput {...fp} jobs={jobs} field="company" label="Company" id="filter-company" />
      <SuggestInput {...fp} jobs={jobs} field="location" label="Location" id="filter-location" />
      <div className="space-y-1.5">
        <Label>Min score</Label>
        <ScoreMinSelect {...fp} variant="panel" />
      </div>
      {stages.length > 1 ? (
        <div className="space-y-2">
          <Label>Stage</Label>
          <div className="flex flex-wrap gap-2">
            <StageToggles {...fp} stages={stages} />
          </div>
        </div>
      ) : null}
      <div className="space-y-1.5">
        <Label>Work model</Label>
        <WorkModelSelect {...fp} variant="panel" workModels={workModels} />
      </div>
      <div className="space-y-1.5">
        <Label>Source</Label>
        <SourceSelect {...fp} variant="panel" sources={sources} />
      </div>
      <div className="space-y-1.5">
        <Label>Materials</Label>
        <MaterialsSelect {...fp} variant="panel" />
      </div>
    </div>
  )
}

/** Phone: every filter in a bottom sheet, with Clear all and "Show N jobs". */
export function FiltersSheet({
  open,
  onOpenChange,
  shownCount,
  onClear,
  ...panel
}: PanelProps & {
  open: boolean
  onOpenChange: (open: boolean) => void
  shownCount: number
  onClear: () => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="gap-0 overflow-y-auto">
        <SheetHeader className="pb-2 text-left">
          <SheetTitle>Filter jobs</SheetTitle>
          <SheetDescription>Only jobs that match every filter are shown.</SheetDescription>
        </SheetHeader>
        <FiltersPanel {...panel} />
        <div className="sticky bottom-0 flex gap-2 border-t border-border bg-popover px-4 py-3">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClear}>
            Clear all
          </Button>
          <Button type="button" className="flex-1" onClick={() => onOpenChange(false)}>
            Show {shownCount} jobs
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

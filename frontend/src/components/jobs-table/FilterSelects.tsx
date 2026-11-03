import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { ColumnFilters } from '@/lib/jobListFilters'
import type { FilterProps } from './types'

/** `panel`: the phone filter sheet (longer labels). `column`: a table header popover. */
type Variant = 'panel' | 'column'

const SCORE_CUTOFFS = [6, 7, 8, 9] as const

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function Trigger({ variant, placeholder }: { variant: Variant; placeholder?: string }) {
  return (
    <SelectTrigger className={variant === 'column' ? 'h-9' : undefined}>
      <SelectValue placeholder={variant === 'panel' ? placeholder : undefined} />
    </SelectTrigger>
  )
}

export function ScoreMinSelect({ filters, setFilters, variant }: FilterProps & { variant: Variant }) {
  return (
    <Select
      value={filters.scoreMin == null ? 'any' : String(filters.scoreMin)}
      onValueChange={(v) => setFilters((f) => ({ ...f, scoreMin: v === 'any' ? null : Number(v) }))}
    >
      <Trigger variant={variant} placeholder="Any score" />
      <SelectContent>
        <SelectItem value="any">{variant === 'panel' ? 'Any score' : 'Any'}</SelectItem>
        {SCORE_CUTOFFS.map((n) => (
          <SelectItem key={n} value={String(n)}>
            {variant === 'panel' ? `${n}+ only` : `${n}+`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function WorkModelSelect({
  filters,
  setFilters,
  variant,
  workModels,
}: FilterProps & { variant: Variant; workModels: string[] }) {
  return (
    <Select
      value={filters.workModel || 'any'}
      onValueChange={(v) => setFilters((f) => ({ ...f, workModel: v === 'any' ? '' : v }))}
    >
      <Trigger variant={variant} placeholder="Any" />
      <SelectContent>
        <SelectItem value="any">Any</SelectItem>
        {workModels.map((m) => (
          <SelectItem key={m} value={m}>
            {capitalize(m)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function SourceSelect({
  filters,
  setFilters,
  variant,
  sources,
}: FilterProps & { variant: Variant; sources: string[] }) {
  return (
    <Select value={filters.source || 'any'} onValueChange={(v) => setFilters((f) => ({ ...f, source: v === 'any' ? '' : v }))}>
      <Trigger variant={variant} placeholder="Any" />
      <SelectContent>
        <SelectItem value="any">Any</SelectItem>
        {sources.map((s) => (
          <SelectItem key={s} value={s}>
            {s}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

const MATERIALS_LABELS: Record<Variant, Record<Exclude<ColumnFilters['materials'], 'any'>, string>> = {
  panel: { resume: 'Has resume', cover: 'Has cover letter', both: 'Has both' },
  column: { resume: 'Resume', cover: 'Cover', both: 'Both' },
}

export function MaterialsSelect({ filters, setFilters, variant }: FilterProps & { variant: Variant }) {
  const labels = MATERIALS_LABELS[variant]
  return (
    <Select
      value={filters.materials}
      onValueChange={(v) => setFilters((f) => ({ ...f, materials: v as ColumnFilters['materials'] }))}
    >
      <Trigger variant={variant} />
      <SelectContent>
        <SelectItem value="any">Any</SelectItem>
        <SelectItem value="resume">{labels.resume}</SelectItem>
        <SelectItem value="cover">{labels.cover}</SelectItem>
        <SelectItem value="both">{labels.both}</SelectItem>
      </SelectContent>
    </Select>
  )
}

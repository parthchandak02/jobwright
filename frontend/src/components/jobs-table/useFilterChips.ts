import { useMemo } from 'react'
import { STAGE_LABELS } from '@/lib/api'
import type { ColumnFilters } from '@/lib/jobListFilters'
import type { SetFilters } from './types'

export type FilterChip = { label: string; onClear: () => void }

const MATERIALS_CHIP: Record<Exclude<ColumnFilters['materials'], 'any'>, string> = {
  both: 'Resume + cover',
  resume: 'Has resume',
  cover: 'Has cover',
}

/** One removable chip per active filter. */
export function useFilterChips(filters: ColumnFilters, setFilters: SetFilters): FilterChip[] {
  return useMemo(() => {
    const chips: FilterChip[] = []
    if (filters.scoreMin != null) {
      chips.push({ label: `Score ${filters.scoreMin}+`, onClear: () => setFilters((f) => ({ ...f, scoreMin: null })) })
    }
    for (const [field, name] of [
      ['title', 'Title'],
      ['company', 'Company'],
      ['location', 'Location'],
    ] as const) {
      const text = filters[field].trim()
      if (text) chips.push({ label: `${name}: ${text}`, onClear: () => setFilters((f) => ({ ...f, [field]: '' })) })
    }
    for (const stage of filters.stages) {
      chips.push({
        label: STAGE_LABELS[stage] || stage,
        onClear: () => setFilters((f) => ({ ...f, stages: f.stages.filter((s) => s !== stage) })),
      })
    }
    if (filters.workModel) {
      chips.push({ label: filters.workModel, onClear: () => setFilters((f) => ({ ...f, workModel: '' })) })
    }
    if (filters.source) {
      chips.push({ label: filters.source, onClear: () => setFilters((f) => ({ ...f, source: '' })) })
    }
    if (filters.materials !== 'any') {
      chips.push({ label: MATERIALS_CHIP[filters.materials], onClear: () => setFilters((f) => ({ ...f, materials: 'any' })) })
    }
    return chips
  }, [filters, setFilters])
}

import type { Dispatch, SetStateAction } from 'react'
import type { ColumnFilters } from '@/lib/jobListFilters'

export type SetFilters = Dispatch<SetStateAction<ColumnFilters>>

/** What the filter controls read and write. */
export type FilterProps = {
  filters: ColumnFilters
  setFilters: SetFilters
}

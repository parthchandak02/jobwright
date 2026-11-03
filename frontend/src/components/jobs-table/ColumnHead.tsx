import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export type ColumnSort = {
  active: boolean
  direction: 'asc' | 'desc'
  onClick: () => void
}

/** Funnel button that opens one column's filter in a popover. */
export function ColumnFilterButton({ active, children, label }: { active: boolean; children: ReactNode; label: string }) {
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

function sortAria(sort?: ColumnSort): 'none' | 'ascending' | 'descending' | undefined {
  if (!sort) return undefined
  if (!sort.active) return 'none'
  return sort.direction === 'asc' ? 'ascending' : 'descending'
}

/** A `<th>`: label (a sort button when sortable) plus an optional filter popover. */
export function ColumnHead({ label, sort, filter }: { label: string; sort?: ColumnSort; filter?: ReactNode }) {
  const SortIcon = sort?.active ? (sort.direction === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown
  return (
    <th scope="col" aria-sort={sortAria(sort)}>
      <div className="jobs-table-head">
        {sort ? (
          <button type="button" className="jobs-table-sort" onClick={sort.onClick}>
            <span className="min-w-0 truncate">{label}</span>
            <SortIcon
              className={cn('size-3.5 shrink-0', sort.active ? 'text-foreground' : 'text-muted-foreground')}
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
    </th>
  )
}

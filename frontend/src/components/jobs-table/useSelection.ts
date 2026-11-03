import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { JobCard } from '@/lib/api'

export type SelectAllState = boolean | 'indeterminate'

/**
 * Toggle `url` in `prev`. With an `anchor` (Shift-click), every shown job from the
 * anchor to `url` takes the clicked job's new state.
 */
export function toggleSelected(prev: Set<string>, shown: JobCard[], url: string, anchor: string | null): Set<string> {
  const next = new Set(prev)
  const on = !prev.has(url)
  const from = anchor ? shown.findIndex((j) => j.url === anchor) : -1
  const to = shown.findIndex((j) => j.url === url)
  const urls = from !== -1 && to !== -1 ? shown.slice(Math.min(from, to), Math.max(from, to) + 1).map((j) => j.url) : [url]
  for (const u of urls) {
    if (on) next.add(u)
    else next.delete(u)
  }
  return next
}

/**
 * Selected jobs in the table, keyed by url. Only jobs in `shown` (the filtered,
 * sorted list) can stay selected: when a filter hides a job it drops out, so a
 * bulk action never touches something the person can't see.
 */
export function useSelection(shown: JobCard[]) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  // Last row toggled without Shift: the start of a Shift-click range.
  const anchor = useRef<string | null>(null)

  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev
      const urls = new Set(shown.map((j) => j.url))
      const next = new Set([...prev].filter((u) => urls.has(u)))
      return next.size === prev.size ? prev : next
    })
  }, [shown])

  const selectedJobs = useMemo(() => shown.filter((j) => selected.has(j.url)), [shown, selected])
  const count = selectedJobs.length

  const isSelected = useCallback((job: JobCard) => selected.has(job.url), [selected])

  /** Toggle one job; with `range`, set every job from the anchor to this one to its new state. */
  const toggle = useCallback(
    (job: JobCard, range = false) => {
      const from = range ? anchor.current : null
      setSelected((prev) => toggleSelected(prev, shown, job.url, from))
      if (!from) anchor.current = job.url
    },
    [shown],
  )

  const selectAll = useCallback(() => setSelected(new Set(shown.map((j) => j.url))), [shown])

  const clear = useCallback(() => {
    anchor.current = null
    setSelected(new Set())
  }, [])

  const allState: SelectAllState = count === 0 ? false : count === shown.length ? true : 'indeterminate'

  /** Header checkbox: anything unselected → select all shown; all selected → clear. */
  const toggleAll = useCallback(() => (allState === true ? clear() : selectAll()), [allState, clear, selectAll])

  return { selectedJobs, count, isSelected, toggle, selectAll, clear, toggleAll, allState }
}

export type Selection = ReturnType<typeof useSelection>

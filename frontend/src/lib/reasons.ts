import { useEffect, useState } from 'react'
import { getCriteria } from '@/lib/api'

/** Reasons people give when a job is not a fit (merged with their own dealbreakers). */
export const NOT_A_FIT_REASONS = [
  'Wrong location',
  'Too senior',
  'Too junior',
  'Not my field',
  'Mission not a fit',
  'Pay too low',
  'Needs a license or degree I lack',
  'Mostly sales or fundraising',
  'Posting expired',
]

export const GOOD_FIT_REASONS = [
  'Great mission',
  'Right level',
  'Right location',
  'Uses my background',
  'More like this',
]

let cached: string[] | null = null
let labelMap: Record<string, string> | null = null

/** Map dealbreaker id -> the user's own label (for chips). */
export function useDealbreakerLabels(): Record<string, string> {
  const [map, setMap] = useState<Record<string, string>>(labelMap ?? {})
  useEffect(() => {
    if (labelMap) return
    getCriteria()
      .then(({ criteria }) => {
        labelMap = Object.fromEntries(criteria.dealbreakers.map((d) => [d.id, d.label || d.id]))
        setMap(labelMap)
      })
      .catch(() => undefined)
  }, [])
  return map
}

/** The user's dealbreaker names first, then the common reasons (deduped). */
export function useNotAFitReasons(): string[] {
  const [labels, setLabels] = useState<string[]>(cached ?? NOT_A_FIT_REASONS)
  useEffect(() => {
    if (cached) return
    getCriteria()
      .then(({ criteria }) => {
        const mine = criteria.dealbreakers.map((d) => d.label).filter(Boolean)
        const seen = new Set<string>()
        cached = [...mine, ...NOT_A_FIT_REASONS].filter((r) => {
          const k = r.toLowerCase()
          if (seen.has(k)) return false
          seen.add(k)
          return true
        })
        setLabels(cached)
      })
      .catch(() => undefined)
  }, [])
  return labels
}

export function invalidateReasons() {
  cached = null
  labelMap = null
}

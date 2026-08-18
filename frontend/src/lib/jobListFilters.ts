import { FUNNEL_STAGES, type JobCard } from '@/lib/api'

export type SortKey =
  | 'score-desc'
  | 'score-asc'
  | 'title-asc'
  | 'title-desc'
  | 'company-asc'
  | 'stage'

export type ColumnFilters = {
  scoreMin: number | null
  title: string
  company: string
  location: string
  stages: string[]
  workModel: string
  source: string
  materials: 'any' | 'resume' | 'cover' | 'both'
}

export const DEFAULT_COLUMN_FILTERS: ColumnFilters = {
  scoreMin: null,
  title: '',
  company: '',
  location: '',
  stages: [],
  workModel: '',
  source: '',
  materials: 'any',
}

function includes(hay: string | null | undefined, needle: string): boolean {
  if (!needle.trim()) return true
  return (hay || '').toLowerCase().includes(needle.trim().toLowerCase())
}

export function countActiveFilters(filters: ColumnFilters): number {
  let count = 0
  if (filters.scoreMin != null) count++
  if (filters.title.trim()) count++
  if (filters.company.trim()) count++
  if (filters.location.trim()) count++
  if (filters.stages.length > 0) count++
  if (filters.workModel) count++
  if (filters.source) count++
  if (filters.materials !== 'any') count++
  return count
}

export function applyColumnFilters(jobs: JobCard[], filters: ColumnFilters): JobCard[] {
  return jobs.filter((job) => {
    if (filters.scoreMin != null && (job.fit_score ?? -1) < filters.scoreMin) return false
    if (!includes(job.title, filters.title)) return false
    if (!includes(job.company, filters.company)) return false
    if (!includes(job.location, filters.location)) return false
    if (filters.stages.length > 0 && !filters.stages.includes(job.funnel_stage)) return false
    if (filters.workModel && (job.work_model || '').toLowerCase() !== filters.workModel) {
      return false
    }
    if (filters.source && job.source !== filters.source) return false
    if (filters.materials === 'resume' && !job.has_resume) return false
    if (filters.materials === 'cover' && !job.has_cover) return false
    if (filters.materials === 'both' && (!job.has_resume || !job.has_cover)) return false
    return true
  })
}

export function sortJobs(jobs: JobCard[], sort: SortKey): JobCard[] {
  const stageRank = new Map<string, number>(FUNNEL_STAGES.map((stage, index) => [stage, index]))
  const copy = [...jobs]

  copy.sort((a, b) => {
    switch (sort) {
      case 'score-desc':
        return (b.fit_score ?? -1) - (a.fit_score ?? -1)
      case 'score-asc':
        return (a.fit_score ?? 99) - (b.fit_score ?? 99)
      case 'title-asc':
        return (a.title || '').localeCompare(b.title || '')
      case 'title-desc':
        return (b.title || '').localeCompare(a.title || '')
      case 'company-asc':
        return (a.company || '').localeCompare(b.company || '')
      case 'stage':
        return (
          (stageRank.get(a.funnel_stage) ?? 99) - (stageRank.get(b.funnel_stage) ?? 99)
        )
      default:
        return 0
    }
  })

  return copy
}

export function uniqueValues(jobs: JobCard[], key: 'source' | 'work_model'): string[] {
  const values = new Set<string>()
  for (const job of jobs) {
    const raw = key === 'source' ? job.source : job.work_model
    const v = (raw || '').trim()
    if (v) values.add(key === 'work_model' ? v.toLowerCase() : v)
  }
  return [...values].sort((a, b) => a.localeCompare(b))
}

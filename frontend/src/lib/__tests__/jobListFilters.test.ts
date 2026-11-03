import { describe, expect, it } from 'vitest'

import {
  DEFAULT_COLUMN_FILTERS,
  applyColumnFilters,
  countActiveFilters,
  sortJobs,
  suggestTextValues,
  uniqueValues,
} from '@/lib/jobListFilters'

import { job } from './fixtures'

const jobs = [
  job({ title: 'Program Manager', company: 'Acme', location: 'Oakland, CA', fit_score: 8,
    funnel_stage: 'applied', source: 'linkedin', work_model: 'Remote', has_resume: true, has_cover: true }),
  job({ title: 'Data Analyst', company: 'Globex', location: 'SF Bay Area', fit_score: 5,
    funnel_stage: 'backlog', source: 'workday', work_model: 'hybrid', has_resume: true }),
  job({ title: 'Chief of Staff', company: 'Initech', location: 'San Francisco, CA', fit_score: null,
    funnel_stage: 'prepare', source: 'linkedin', work_model: null }),
]

describe('countActiveFilters', () => {
  it('is zero for defaults', () => {
    expect(countActiveFilters(DEFAULT_COLUMN_FILTERS)).toBe(0)
  })

  it('counts each active filter and ignores whitespace-only text', () => {
    expect(
      countActiveFilters({
        ...DEFAULT_COLUMN_FILTERS, scoreMin: 6, title: 'pm', company: '  ', stages: ['applied'], materials: 'both',
      }),
    ).toBe(4)
  })
})

describe('applyColumnFilters', () => {
  const titles = (f: Partial<typeof DEFAULT_COLUMN_FILTERS>) =>
    applyColumnFilters(jobs, { ...DEFAULT_COLUMN_FILTERS, ...f }).map((j) => j.title)

  it('returns everything with default filters', () => {
    expect(titles({})).toHaveLength(3)
  })

  it('filters by min score (unscored jobs drop out)', () => {
    expect(titles({ scoreMin: 5 })).toEqual(['Program Manager', 'Data Analyst'])
  })

  it('matches text case-insensitively and trims the needle', () => {
    expect(titles({ company: '  GLOBEX ' })).toEqual(['Data Analyst'])
    expect(titles({ location: 'ca' })).toEqual(['Program Manager', 'Chief of Staff'])
  })

  it('filters by stage, work model (lower-cased), source and materials', () => {
    expect(titles({ stages: ['prepare', 'applied'] })).toEqual(['Program Manager', 'Chief of Staff'])
    expect(titles({ workModel: 'remote' })).toEqual(['Program Manager'])
    expect(titles({ source: 'workday' })).toEqual(['Data Analyst'])
    expect(titles({ materials: 'resume' })).toEqual(['Program Manager', 'Data Analyst'])
    expect(titles({ materials: 'cover' })).toEqual(['Program Manager'])
    expect(titles({ materials: 'both' })).toEqual(['Program Manager'])
  })
})

describe('sortJobs', () => {
  const order = (key: Parameters<typeof sortJobs>[1]) => sortJobs(jobs, key).map((j) => j.title)

  it('sorts by score with unscored jobs last in both directions', () => {
    expect(order('score-desc')).toEqual(['Program Manager', 'Data Analyst', 'Chief of Staff'])
    expect(order('score-asc')).toEqual(['Data Analyst', 'Program Manager', 'Chief of Staff'])
  })

  it('sorts by title, company and funnel stage', () => {
    expect(order('title-asc')).toEqual(['Chief of Staff', 'Data Analyst', 'Program Manager'])
    expect(order('title-desc')).toEqual(['Program Manager', 'Data Analyst', 'Chief of Staff'])
    expect(order('company-asc')).toEqual(['Program Manager', 'Data Analyst', 'Chief of Staff'])
    expect(order('stage')).toEqual(['Data Analyst', 'Chief of Staff', 'Program Manager'])
  })

  it('does not mutate the input', () => {
    const before = jobs.map((j) => j.title)
    sortJobs(jobs, 'title-asc')
    expect(jobs.map((j) => j.title)).toEqual(before)
  })
})

describe('uniqueValues', () => {
  it('returns sorted distinct non-empty values', () => {
    expect(uniqueValues(jobs, 'source')).toEqual(['linkedin', 'workday'])
    expect(uniqueValues(jobs, 'work_model')).toEqual(['hybrid', 'remote'])
  })
})

describe('suggestTextValues', () => {
  it('returns nothing for an empty query', () => {
    expect(suggestTextValues(jobs, 'location', '  ')).toEqual([])
  })

  it('returns matching values, shortest first, de-duplicated', () => {
    const more = [...jobs, job({ location: 'oakland, ca' })]
    expect(suggestTextValues(more, 'location', 'ca')).toEqual(['Oakland, CA', 'San Francisco, CA'])
  })

  it('caps suggestions at six', () => {
    const many = Array.from({ length: 10 }, (_, i) => job({ company: `Org ${i}` }))
    expect(suggestTextValues(many, 'company', 'org')).toHaveLength(6)
  })
})

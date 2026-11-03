import type { JobCard } from '@/lib/api'

let seq = 0

/** A JobCard with safe defaults; override only what a test cares about. */
export function job(overrides: Partial<JobCard> = {}): JobCard {
  seq += 1
  return {
    job_id: `job${seq}`,
    url: `https://example.com/jobs/${seq}`,
    title: `Role ${seq}`,
    company: 'Example Co',
    location: 'Remote',
    funnel_stage: 'backlog',
    fit_score: null,
    source: 'linkedin',
    work_model: null,
    has_resume: false,
    has_cover: false,
    ...overrides,
  } as JobCard
}

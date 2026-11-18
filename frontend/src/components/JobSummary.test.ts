import { describe, expect, it } from 'vitest'
import { listingHref, placeLine } from '@/components/JobSummary'
import { job } from '@/lib/__tests__/fixtures'

describe('listingHref', () => {
  it('prefers the employer apply URL over the listing URL', () => {
    expect(listingHref(job({
      url: 'https://www.linkedin.com/jobs/view/1',
      application_url: 'https://boards.greenhouse.io/co/jobs/1',
    }))).toBe('https://boards.greenhouse.io/co/jobs/1')
  })

  it('falls back to the listing URL when no apply URL is saved', () => {
    expect(listingHref(job({ url: 'https://jobs.example.com/1', application_url: null }))).toBe(
      'https://jobs.example.com/1',
    )
  })

  it('treats junk None/null strings as missing so Open posting stays hidden', () => {
    expect(listingHref(job({ url: '', application_url: 'None' }))).toBeNull()
    expect(listingHref(job({ url: 'null', application_url: null }))).toBeNull()
    expect(listingHref(job({ url: '  ', application_url: '' }))).toBeNull()
  })
})

describe('placeLine', () => {
  it('joins location and work model when they say different things', () => {
    expect(placeLine({ location: 'Oakland, CA', work_model: 'hybrid' })).toBe('Oakland, CA · Hybrid')
  })

  it('does not repeat a work model already in the location string', () => {
    expect(placeLine({ location: 'Remote - US', work_model: 'remote' })).toBe('Remote - US')
  })

  it('falls back to location, then work model, then a plain placeholder', () => {
    expect(placeLine({ location: 'SF', work_model: null })).toBe('SF')
    expect(placeLine({ location: null, work_model: 'onsite' })).toBe('Onsite')
    expect(placeLine({ location: '  ', work_model: null })).toBe('Location not stated')
  })
})

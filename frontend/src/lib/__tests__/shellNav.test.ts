import { describe, expect, it } from 'vitest'
import { isLinkActive, phoneTabs, type NavLinkShape } from '@/lib/shellNav'

type L = NavLinkShape & { name: string }
const jobs: L = { name: 'jobs', path: '/' }
const review: L = { name: 'review', path: '/review' }
const quality: L = { name: 'quality', path: '/quality' }
const admin: L = { name: 'admin', path: '/admin' }
const claude: L = { name: 'claude', path: '/profile', search: '?tab=claude', phoneOptional: true }
const settings: L = { name: 'settings', path: '/profile' }

describe('isLinkActive', () => {
  const links = [jobs, review, claude, settings]
  it('marks Claude, not Settings, on the Claude tab', () => {
    expect(isLinkActive(claude, '/profile', '?tab=claude', links)).toBe(true)
    expect(isLinkActive(settings, '/profile', '?tab=claude', links)).toBe(false)
  })
  it('marks Settings on other tabs', () => {
    expect(isLinkActive(settings, '/profile', '?tab=search', links)).toBe(true)
    expect(isLinkActive(claude, '/profile', '?tab=search', links)).toBe(false)
    expect(isLinkActive(settings, '/profile', '', links)).toBe(true)
  })
  it('marks Settings on the Claude tab when the Claude link is not shown', () => {
    expect(isLinkActive(settings, '/profile', '?tab=claude', [jobs, settings])).toBe(true)
  })
  it('treats job pages as Jobs', () => {
    expect(isLinkActive(jobs, '/jobs/abc', '', links)).toBe(true)
    expect(isLinkActive(jobs, '/review', '', links)).toBe(false)
  })
})

describe('phoneTabs', () => {
  it('keeps the optional tab while it fits in five', () => {
    expect(phoneTabs([jobs, review, quality, claude, settings]).map((l) => l.name)).toContain('claude')
  })
  it('drops it when a sixth tab would crowd the bar', () => {
    const tabs = phoneTabs([jobs, review, quality, admin, claude, settings])
    expect(tabs).toHaveLength(5)
    expect(tabs.map((l) => l.name)).not.toContain('claude')
  })
})

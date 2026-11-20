/** @vitest-environment jsdom */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const writeClipboardText = vi.fn(async (_t: string) => true)
const toastSuccess = vi.fn()

vi.mock('@/lib/clipboard', () => ({ writeClipboardText: (t: string) => writeClipboardText(t) }))
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }))

import { ReviewCard } from '@/components/review/ReviewCard'
import type { JobCard } from '@/lib/api'
import { ContactDetails } from './ContactDetails'
import { CONTACT_DETAIL_ALLOWLIST, pickContactDetails, shouldShowContactDetails } from './contactDetails'

const FAKE_JOB = {
  job_id: 'job-1', whatsapp_notified_at: null, url: 'https://jobs.example.com/1', title: 'Senior Product Designer',
  company: 'Northwind Labs', site: 'indeed', location: 'San Francisco, CA', salary: '$165,000 - $190,000',
  work_model: 'hybrid', sponsorship_status: 'not_found', fit_score: 9, keywords: 'design', reasoning: 'Strong fit.',
  funnel_stage: 'backlog', outcome: null, source: 'discover', applied_manually: false, applied_at: null,
  first_response_at: null, follow_up_at: null, notes: null, board_updated_by: 'agent', board_updated_at: null,
  has_resume: false, has_cover: false, application_url: 'https://jobs.example.com/1',
  discovered_at: '2026-09-28T06:12:00', apply_status: null,
} as JobCard

beforeEach(() => { vi.useFakeTimers(); writeClipboardText.mockResolvedValue(true) })
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('pickContactDetails and shouldShowContactDetails', () => {
  it('keeps only the explicit allowlist and omits empty values, passwords and unknown keys', () => {
    const picked = pickContactDetails({
      full_name: 'Alex Rivera', preferred_name: 'Alex', email: 'alex@example.com', password: 'do-not-leak-password',
      phone: '   ', address: '123 Main St', city: 'San Francisco', province_state: 'CA', country: 'United States',
      postal_code: '94107', linkedin_url: 'https://www.linkedin.com/in/alex-rivera',
      github_url: 'https://github.com/alex-rivera', portfolio_url: 'https://alex.example.com', unknown_secret: 'secret',
    })
    expect(CONTACT_DETAIL_ALLOWLIST.map((f) => f.key)).toEqual([
      'full_name', 'email', 'phone', 'city', 'province_state', 'country', 'postal_code', 'linkedin_url', 'github_url',
    ])
    expect(picked.map((p) => p.key)).toEqual([
      'full_name', 'email', 'city', 'province_state', 'country', 'postal_code', 'linkedin_url', 'github_url',
    ])
    expect(picked.some((p) => (p.key as string) === 'password' || (p.key as string) === 'unknown_secret')).toBe(false)
  })

  it('shows only for stages before Applied', () => {
    expect([shouldShowContactDetails('backlog'), shouldShowContactDetails('prepare')]).toEqual([true, true])
    expect(['applied', 'in_progress', 'offer', 'closed', null].map(shouldShowContactDetails)).toEqual([
      false, false, false, false, false,
    ])
  })
})

describe('ContactDetails', () => {
  it('stays folded by default, blocks password/unknown keys, and copies without logging or storing', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    const personal = {
      full_name: 'Alex Rivera', email: 'alex@example.com', phone: '', city: 'San Francisco',
      password: 'hunter2-secret-password', unknown_extra: 'should-never-appear-in-dom',
    }
    const { container, rerender } = render(createElement(ContactDetails, { jobKey: 'job-1', personal }))
    const toggle = screen.getByRole('button', { name: 'Your details' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('alex@example.com')).toBeNull()

    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Alex Rivera')).toBeTruthy()
    expect(screen.getByText('alex@example.com')).toBeTruthy()
    expect(screen.queryByText('Phone')).toBeNull()
    for (const secret of ['hunter2-secret-password', 'password', 'should-never-appear-in-dom', 'unknown_extra']) {
      expect(container.textContent).not.toContain(secret)
    }

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy Email' })); await Promise.resolve() })
    expect(writeClipboardText).toHaveBeenCalledWith('alex@example.com')
    expect(toastSuccess).toHaveBeenCalledWith('Copied')
    expect(screen.getByRole('button', { name: 'Email copied' })).toBeTruthy()
    expect(logSpy).not.toHaveBeenCalled()
    expect(infoSpy).not.toHaveBeenCalled()
    expect(setItemSpy).not.toHaveBeenCalled()

    rerender(createElement(ContactDetails, { jobKey: 'job-2', personal }))
    expect(screen.getByRole('button', { name: 'Your details' }).getAttribute('aria-expanded')).toBe('false')
  })

  it('renders nothing when empty and never appears inside ReviewCard', () => {
    const { container } = render(createElement(ContactDetails, { jobKey: 'job-1', personal: { password: 'x', phone: ' ' } }))
    expect(container.firstChild).toBeNull()
    window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as typeof window.matchMedia
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    render(createElement(ReviewCard, { job: FAKE_JOB, detail: FAKE_JOB, onSwipe: () => undefined, onOpenFull: () => undefined }))
    expect(screen.queryByText('Your details')).toBeNull()
  })
})

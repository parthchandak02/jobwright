/** @vitest-environment jsdom */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const writeClipboardText = vi.fn(async (_t: string) => true)
const toastSuccess = vi.fn()

vi.mock('@/lib/clipboard', () => ({ writeClipboardText: (t: string) => writeClipboardText(t) }))
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }))

import { ReviewCard } from '@/components/review/ReviewCard'
import type { AnswerFieldSpec, ApplicationAnswers, JobCard } from '@/lib/api'
import { SavedAnswers } from './SavedAnswers'
import { pickSavedAnswers, SAVED_ANSWER_SECTIONS, shouldShowSavedAnswers } from './savedAnswers'

const f = (key: string, label: string, section: AnswerFieldSpec['section'], attestation = false): AnswerFieldSpec => ({
  key, label, category: attestation ? 'attestation' : 'common', attestation, required: false, hint: '', choices: [], section,
})
const e = (value: string) => ({ value, source: 'settings', updated_at: '2026-11-20T10:00:00Z' })

const FAKE_ANSWERS: ApplicationAnswers = {
  version: 1,
  sections: [
    { id: 'contact', title: 'Contact and address' }, { id: 'education', title: 'Education' },
    { id: 'eligibility', title: 'Work eligibility' }, { id: 'experience', title: 'Experience' },
    { id: 'pay_start', title: 'Pay and start date' }, { id: 'diversity', title: 'Diversity questions (optional)' },
    { id: 'other', title: 'Other questions forms asked' },
  ],
  fields: [
    f('phone', 'Phone', 'contact'), f('city', 'City', 'contact'),
    f('education_highest', 'Highest education (degree, school, year)', 'education'),
    f('work_authorized', 'Legally authorized to work in the country of the job', 'eligibility', true),
    f('requires_sponsorship', 'Will need visa sponsorship now or in the future', 'eligibility', true),
    f('relocation', 'Willing to relocate', 'eligibility', true),
    f('years_experience', 'Years of relevant work experience (number)', 'experience'),
    f('salary_expectation', 'Salary expectation (as you want it written)', 'pay_start', true),
    f('start_date', 'Earliest start date / availability', 'pay_start', true),
    f('notice_period', 'Notice period', 'pay_start'),
    f('eeo_gender', 'Gender (EEO, voluntary)', 'diversity', true),
    f('eeo_race', 'Race / ethnicity (EEO, voluntary)', 'diversity', true),
    f('how_heard', 'How did you hear about us', 'other'),
  ],
  answers: {
    phone: e('555-0100'), city: e('San Francisco'),
    education_highest: e("Bachelor's degree, UC Berkeley, 2018"),
    work_authorized: e('Yes'), requires_sponsorship: e('No'), relocation: e('   '),
    years_experience: e('8'), salary_expectation: e('$170,000 USD per year'),
    start_date: e(''), notice_period: e('Two weeks'),
    eeo_gender: e('Woman'), eeo_race: e('Decline to self-identify'), how_heard: e('Company website'),
  },
  custom: { cpa: { question: 'Hold a CPA license?', value: 'No', source: 'settings', updated_at: '2026-11-20T10:00:00Z' } },
  missing: [],
}

const FAKE_JOB = {
  job_id: 'job-1', whatsapp_notified_at: null, url: 'https://jobs.example.com/1', title: 'Senior Product Designer',
  company: 'Northwind Labs', site: 'indeed', location: 'San Francisco, CA', salary: '$165,000 - $190,000',
  work_model: 'hybrid', sponsorship_status: 'not_found', fit_score: 9, keywords: 'design', reasoning: 'Strong fit.',
  funnel_stage: 'backlog', outcome: null, source: 'discover', applied_manually: false, applied_at: null,
  first_response_at: null, follow_up_at: null, notes: null, board_updated_by: 'agent', board_updated_at: null,
  has_resume: false, has_cover: false, application_url: 'https://jobs.example.com/1',
  discovered_at: '2026-09-28T06:12:00', apply_status: null,
} as JobCard

const renderSaved = (jobKey: string, data: ApplicationAnswers | null) =>
  render(createElement(MemoryRouter, null, createElement(SavedAnswers, { jobKey, data })))

beforeEach(() => { vi.useFakeTimers(); writeClipboardText.mockResolvedValue(true) })
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('pickSavedAnswers and shouldShowSavedAnswers', () => {
  it('keeps only education, eligibility, experience and pay_start, omitting empty, contact, diversity and other', () => {
    expect(SAVED_ANSWER_SECTIONS).toEqual(['education', 'eligibility', 'experience', 'pay_start'])
    const sections = pickSavedAnswers(FAKE_ANSWERS)
    expect(sections.map((s) => [s.id, s.title, s.items.map((i) => i.key)])).toEqual([
      ['education', 'Education', ['education_highest']],
      ['eligibility', 'Work eligibility', ['work_authorized', 'requires_sponsorship']],
      ['experience', 'Experience', ['years_experience']],
      ['pay_start', 'Pay and start date', ['salary_expectation', 'notice_period']],
    ])
    const keys = sections.flatMap((s) => s.items.map((i) => i.key))
    for (const k of ['phone', 'city', 'eeo_gender', 'eeo_race', 'how_heard', 'relocation', 'start_date']) expect(keys).not.toContain(k)
  })

  it('shows only for stages before Applied', () => {
    expect([shouldShowSavedAnswers('backlog'), shouldShowSavedAnswers('prepare')]).toEqual([true, true])
    expect(['applied', 'in_progress', 'offer', 'closed', null].map(shouldShowSavedAnswers)).toEqual([false, false, false, false, false])
  })
})

describe('SavedAnswers', () => {
  it('stays folded by default, hides diversity and contact answers, is read-only, and copies without logging or storing', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    const { container, rerender } = renderSaved('job-1', FAKE_ANSWERS)

    const toggle = screen.getByRole('button', { name: 'Your answers' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('$170,000 USD per year')).toBeNull()

    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    for (const text of ['Education', 'Work eligibility', 'Experience', 'Pay and start date', "Bachelor's degree, UC Berkeley, 2018", '$170,000 USD per year', 'Two weeks']) {
      expect(screen.getByText(text)).toBeTruthy()
    }
    for (const hidden of ['Contact and address', 'Diversity questions (optional)', '555-0100', 'San Francisco', 'Woman', 'Decline to self-identify', 'Company website', 'Hold a CPA license?']) {
      expect(container.textContent).not.toContain(hidden)
    }
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: /save|undo/i })).toBeNull()
    expect(screen.getByRole('link', { name: 'Change in Settings' }).getAttribute('href')).toBe('/profile?tab=about#application-details')

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy Pay expectation' })); await Promise.resolve() })
    expect(writeClipboardText).toHaveBeenCalledWith('$170,000 USD per year')
    expect(toastSuccess).toHaveBeenCalledWith('Copied')
    expect(screen.getByRole('button', { name: 'Pay expectation copied' })).toBeTruthy()
    expect(logSpy).not.toHaveBeenCalled()
    expect(infoSpy).not.toHaveBeenCalled()
    expect(setItemSpy).not.toHaveBeenCalled()

    rerender(createElement(MemoryRouter, null, createElement(SavedAnswers, { jobKey: 'job-2', data: FAKE_ANSWERS })))
    expect(screen.getByRole('button', { name: 'Your answers' }).getAttribute('aria-expanded')).toBe('false')
  })

  it('renders nothing when allowed answers are empty and never appears inside ReviewCard', () => {
    const { container } = renderSaved('job-1', { ...FAKE_ANSWERS, answers: { phone: e('555-0100'), eeo_gender: e('Woman'), work_authorized: e('   ') } })
    expect(container.firstChild).toBeNull()
    window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as typeof window.matchMedia
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    render(createElement(ReviewCard, { job: FAKE_JOB, detail: FAKE_JOB, onSwipe: () => undefined, onOpenFull: () => undefined }))
    expect(screen.queryByText('Your answers')).toBeNull()
  })
})

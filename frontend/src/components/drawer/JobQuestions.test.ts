/** @vitest-environment jsdom */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const toastSuccess = vi.fn()
const apiFetch = vi.fn()
const providePending = vi.fn()

vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
    providePending: (...args: unknown[]) => providePending(...args),
    getBaseMaterials: vi.fn(async () => ({ resume_markdown: '', has_resume_pdf: false, resume_pdf_mtime: null, cover_letter_examples: [] })),
    getPersonalDetails: vi.fn(async () => ({})),
    getApplicationAnswers: vi.fn(async () => ({ version: 1, answers: {}, custom: {}, fields: [], missing: [] })),
    getConnector: vi.fn(async () => ({ clients: [] })),
    listRuns: vi.fn(async () => []),
  }
})

import { JobDrawer } from '@/components/JobDrawer'
import { listPending, type JobCard, type PendingInput } from '@/lib/api'
import { questionsForJob } from '@/lib/claudeQuestions'

const q = (over: Partial<PendingInput>): PendingInput => ({
  id: 'p1', kind: 'answer', prompt: 'Are you authorized to work in the US?', company: 'Northwind Labs',
  job_id: 'abc123def456', status: 'open', created_at: '2026-11-24T10:00:00Z', expires_at: null,
  resolved_at: null, resolved_by: null, choices: ['Yes', 'No'], asked_by: 'connector', ...over,
})

const PENDING: PendingInput[] = [
  q({}),
  q({ id: 'p2', prompt: 'Desired salary', choices: [] }),
  q({ id: 'p3', job_id: 'other1234567', prompt: 'Other job question' }),
  q({ id: 'p4', kind: 'captcha', prompt: 'Solve the captcha' }),
  q({ id: 'p5', status: 'resolved', prompt: 'Already answered' }),
]

const FAKE_JOB = {
  job_id: 'abc123def456', whatsapp_notified_at: null, url: 'https://jobs.example.com/1', title: 'Senior Product Designer',
  company: 'Northwind Labs', site: 'indeed', location: 'San Francisco, CA', salary: null,
  work_model: 'hybrid', sponsorship_status: 'not_found', fit_score: 9, keywords: 'design', reasoning: 'Strong fit.',
  funnel_stage: 'prepare', outcome: null, source: 'discover', applied_manually: false, applied_at: null,
  first_response_at: null, follow_up_at: null, notes: null, board_updated_by: 'agent', board_updated_at: null,
  has_resume: false, has_cover: false, application_url: 'https://jobs.example.com/1',
  discovered_at: '2026-09-28T06:12:00', apply_status: null,
} as JobCard

const flush = () => act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve() })

beforeEach(() => {
  vi.useFakeTimers()
  // listPending calls the module's own apiFetch, so answer it at the fetch level.
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ pending: PENDING }), { status: 200 })))
  if (!globalThis.CSS?.escape) vi.stubGlobal('CSS', { escape: (s: string) => s })
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }) as unknown as typeof window.matchMedia
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  apiFetch.mockImplementation(async (path: string) => {
    if (path === '/jobs/abc123def456') return FAKE_JOB
    if (path.endsWith('/connections')) return { csv_contacts: [], web_contacts: [], manual_contacts: [] }
    if (path.endsWith('/history')) return { history: [] }
    if (path.startsWith('/apply/picks')) return { picks: [] }
    return {}
  })
  providePending.mockImplementation(async (id: string) => ({ ...q({ id }), status: 'resolved' }))
})

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('questionsForJob', () => {
  it('keeps only open answer questions for the given job', () => {
    expect(questionsForJob(PENDING, 'abc123def456').map((p) => p.id)).toEqual(['p1', 'p2'])
    expect(questionsForJob(PENDING, null)).toEqual([])
  })
})

describe('listPending', () => {
  it('filters by kind when asked', async () => {
    const r = await listPending('open', 'answer')
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/apply/pending?status=open')
    expect(r.pending.map((p) => p.id)).toEqual(['p1', 'p2', 'p3', 'p5'])
  })
})

describe('JobDrawer questions from Claude', () => {
  it('shows matching questions, saves an answer, hides it and reloads the drawer', async () => {
    render(createElement(MemoryRouter, null, createElement(JobDrawer, { jobKey: 'abc123def456', onClose: () => {}, onChanged: () => {} })))
    await flush()

    expect(screen.getByText('Your Claude needs 2 answers')).toBeTruthy()
    expect(screen.getByText('Are you authorized to work in the US?')).toBeTruthy()
    expect(screen.getByText('Desired salary')).toBeTruthy()
    expect(screen.queryByText('Other job question')).toBeNull()
    expect(screen.queryByText('Solve the captcha')).toBeNull()
    expect(screen.queryByText('Already answered')).toBeNull()

    const jobLoads = () => apiFetch.mock.calls.filter(([p]) => p === '/jobs/abc123def456').length
    const before = jobLoads()

    // Two choices render as buttons.
    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }))
    const saveButtons = screen.getAllByRole('button', { name: 'Save' })
    await act(async () => { fireEvent.click(saveButtons[0]) })
    await flush()

    expect(providePending).toHaveBeenCalledWith('p1', 'Yes')
    expect(toastSuccess).toHaveBeenCalledWith('Saved. Your Claude will use it on every form that asks.')
    expect(screen.queryByText('Are you authorized to work in the US?')).toBeNull()
    expect(screen.getByText('Your Claude needs an answer')).toBeTruthy()
    expect(jobLoads()).toBeGreaterThan(before)
  })
})

/** @vitest-environment jsdom */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const writeClipboardText = vi.fn(async (_t: string) => true)
const toastSuccess = vi.fn()
const getConnector = vi.fn()
const apiFetch = vi.fn()

vi.mock('@/lib/clipboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/clipboard')>()
  return { ...actual, writeClipboardText: (t: string) => writeClipboardText(t) }
})
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args), getConnector: () => getConnector(),
    getBaseMaterials: vi.fn(async () => ({ resume_markdown: '', has_resume_pdf: false, resume_pdf_mtime: null, cover_letter_examples: [] })),
    getPersonalDetails: vi.fn(async () => ({})),
    getApplicationAnswers: vi.fn(async () => ({ version: 1, answers: {}, custom: {}, fields: [], missing: [] })),
    listRuns: vi.fn(async () => []),
  }
})

import { JobDrawer } from '@/components/JobDrawer'
import type { ConnectorStatus, JobCard } from '@/lib/api'
import { ApplyWithClaude } from './ApplyWithClaude'

const FAKE_JOB = {
  job_id: 'abc123def456', whatsapp_notified_at: null, url: 'https://jobs.example.com/1', title: 'Senior Product Designer',
  company: 'Northwind Labs', site: 'indeed', location: 'San Francisco, CA', salary: '$165,000 - $190,000',
  work_model: 'hybrid', sponsorship_status: 'not_found', fit_score: 9, keywords: 'design', reasoning: 'Strong fit.',
  funnel_stage: 'backlog', outcome: null, source: 'discover', applied_manually: false, applied_at: null,
  first_response_at: null, follow_up_at: null, notes: null, board_updated_by: 'agent', board_updated_at: null,
  has_resume: false, has_cover: false, application_url: 'https://jobs.example.com/1',
  discovered_at: '2026-09-28T06:12:00', apply_status: null,
} as JobCard

const CONNECTED_STATUS: ConnectorStatus = {
  enabled: true, url: 'https://jobwright.example.com/mcp', apply_via: 'connector', apply_enabled: false,
  apply_min_score: 8, apply_daily_cap: 2, can_choose_server: false, scopes: [],
  clients: [{ id: 'grant-1', client_name: 'Claude', email: 'alex@example.com', scopes: ['jobs:read', 'jobs:write', 'apply'], created_at: 1790000000, last_used_at: 1790500000, active: true }],
  missing_answers: 0, apply_paused: false,
  daily_pick: { scheduled: true, time: '07:30', days: 'daily', next_at: null, apply_at: null, veto_minutes: 180 },
}

const DISCONNECTED_STATUS: ConnectorStatus = { ...CONNECTED_STATUS, clients: [] }

const renderHelper = (job: Pick<JobCard, 'job_id' | 'title' | 'company'> = FAKE_JOB) =>
  render(createElement(MemoryRouter, null, createElement(ApplyWithClaude, { job })))

beforeEach(() => {
  vi.useFakeTimers()
  writeClipboardText.mockResolvedValue(true)
  getConnector.mockResolvedValue(CONNECTED_STATUS)
  if (!globalThis.CSS?.escape) vi.stubGlobal('CSS', { escape: (s: string) => s })
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }) as unknown as typeof window.matchMedia
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('ApplyWithClaude', () => {
  it('renders collapsed by default and expands to show a copyable prompt and Open Claude link when connected', async () => {
    const { rerender } = renderHelper()
    await act(async () => { await Promise.resolve() })

    const toggle = screen.getByRole('button', { name: 'Apply with Claude' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText(/start_application/)).toBeNull()

    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    const expectedPrompt =
      'Apply to Senior Product Designer at Northwind Labs (job_id: abc123def456) in jobwright: call start_application("abc123def456") and fill the application with Claude in Chrome.'
    expect(screen.getByText(expectedPrompt)).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Connect Claude' })).toBeNull()

    const openLink = screen.getByRole('link', { name: 'Open Claude' })
    expect(openLink.getAttribute('href')).toBe('https://claude.ai/new')
    expect(openLink.getAttribute('target')).toBe('_blank')

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' })); await Promise.resolve() })
    expect(writeClipboardText).toHaveBeenCalledWith(expectedPrompt)
    expect(toastSuccess).toHaveBeenCalledWith('Copied')
    expect(screen.getByRole('button', { name: 'Prompt copied' })).toBeTruthy()

    rerender(createElement(MemoryRouter, null, createElement(ApplyWithClaude, {
      job: { job_id: '999888777666', title: 'Staff Designer', company: 'Cobalt Maps' },
    })))
    await act(async () => { await Promise.resolve() })
    expect(screen.getByRole('button', { name: 'Apply with Claude' }).getAttribute('aria-expanded')).toBe('false')
  })

  it('shows a link to /profile?tab=claude when no client is connected', async () => {
    getConnector.mockResolvedValue(DISCONNECTED_STATUS)
    renderHelper()
    await act(async () => { await Promise.resolve() })

    const toggle = screen.getByRole('button', { name: 'Apply with Claude' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('link', { name: 'Connect Claude' }).getAttribute('href')).toBe('/profile?tab=claude')
    expect(screen.queryByRole('link', { name: 'Open Claude' })).toBeNull()
    expect(screen.queryByText(/start_application/)).toBeNull()
  })

  it('renders inside JobDrawer only when beforeApplying is true', async () => {
    apiFetch.mockImplementation(async (path: string) => {
      if (path === '/jobs/abc123def456') return { ...FAKE_JOB, funnel_stage: 'backlog' }
      if (path === '/jobs/other1234567') return { ...FAKE_JOB, job_id: 'other1234567', funnel_stage: 'applied' }
      if (path.endsWith('/connections')) return { csv_contacts: [], web_contacts: [], manual_contacts: [] }
      if (path.endsWith('/history')) return { history: [] }
      if (path.startsWith('/apply/picks')) return { picks: [] }
      return {}
    })

    const { rerender } = render(createElement(MemoryRouter, null, createElement(JobDrawer, { jobKey: 'abc123def456', onClose: () => {}, onChanged: () => {} })))
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(screen.getByRole('button', { name: 'Apply with Claude' }).getAttribute('aria-expanded')).toBe('false')

    rerender(createElement(MemoryRouter, null, createElement(JobDrawer, { jobKey: 'other1234567', onClose: () => {}, onChanged: () => {} })))
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(screen.queryByRole('button', { name: 'Apply with Claude' })).toBeNull()
  })
})

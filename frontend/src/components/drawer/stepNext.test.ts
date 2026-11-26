/** @vitest-environment jsdom */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const toastSuccess = vi.fn()
const apiFetch = vi.fn()

vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
    getBaseMaterials: vi.fn(async () => ({ resume_markdown: '', has_resume_pdf: false, resume_pdf_mtime: null, cover_letter_examples: [] })),
    getPersonalDetails: vi.fn(async () => ({})),
    getApplicationAnswers: vi.fn(async () => ({ version: 1, answers: {}, custom: {}, fields: [], missing: [] })),
    getConnector: vi.fn(async () => ({ clients: [] })),
    listRuns: vi.fn(async () => []),
  }
})

import { JobDrawer } from '@/components/JobDrawer'
import type { JobCard } from '@/lib/api'

const NOW = new Date('2026-11-25T18:00:00Z')
const SENT = '2026-11-25T15:00:00.000000+00:00'

const card = (over: Partial<JobCard>) =>
  ({
    job_id: 'aaaa00000001', whatsapp_notified_at: SENT, url: 'https://jobs.example.com/1', title: 'Program Manager',
    company: 'Northwind Labs', site: 'indeed', location: 'Remote', salary: null, work_model: 'remote',
    sponsorship_status: 'not_found', fit_score: 9, keywords: '', reasoning: 'Strong fit.', funnel_stage: 'prepare',
    outcome: null, source: 'discover', applied_manually: false, applied_at: null, first_response_at: null,
    follow_up_at: null, notes: null, board_updated_by: 'agent', board_updated_at: null, has_resume: false,
    has_cover: false, application_url: 'https://jobs.example.com/1', discovered_at: '2026-11-25T06:00:00', apply_status: null,
    ...over,
  }) as JobCard

const BOARD = [card({}), card({ job_id: 'bbbb00000002', title: 'Data Analyst', company: 'Acme', fit_score: 8, funnel_stage: 'backlog' })]
let jobs: Record<string, JobCard> = {}

const flush = () => act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve() })

function renderDrawer(jobKey: string, board: JobCard[] = BOARD, onOpenJob = vi.fn()) {
  const el = (key: string) =>
    createElement(MemoryRouter, null, createElement(JobDrawer, { jobKey: key, onClose: () => {}, onChanged: () => {}, onOpenJob, boardJobs: board }))
  const view = render(el(jobKey))
  return { onOpenJob, rerender: (key: string) => view.rerender(el(key)) }
}

const click = async (name: string | RegExp) => {
  await act(async () => { fireEvent.click(screen.getAllByRole('button', { name })[0]) })
  await flush()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  jobs = Object.fromEntries(BOARD.map((j) => [j.job_id, { ...j }]))
  // moveJob and listPending call the module's own apiFetch, so answer them at the fetch level.
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const move = String(url).match(/\/jobs\/(\w+)\/move$/)
    if (!move) return new Response(JSON.stringify({ pending: [] }), { status: 200 })
    const from = jobs[move[1]].funnel_stage
    jobs[move[1]] = { ...jobs[move[1]], funnel_stage: JSON.parse(String(init?.body)).to_stage }
    return new Response(JSON.stringify({ from_stage: from, job: jobs[move[1]] }), { status: 200 })
  }))
  if (!globalThis.CSS?.escape) vi.stubGlobal('CSS', { escape: (s: string) => s })
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }) as unknown as typeof window.matchMedia
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  apiFetch.mockImplementation(async (path: string) => {
    const one = path.match(/^\/jobs\/(\w+)$/)
    if (one) return jobs[one[1]]
    if (path.endsWith('/connections')) return { csv_contacts: [], web_contacts: [], manual_contacts: [] }
    if (path.endsWith('/history')) return { history: [] }
    if (path.startsWith('/apply/picks')) return { picks: [] }
    return {}
  })
})

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('JobDrawer Next on the list', () => {
  it('offers the next job after I applied, and Undo clears it', async () => {
    const { onOpenJob } = renderDrawer('aaaa00000001')
    await flush()
    expect(screen.queryByText(/Next: Data Analyst/)).toBeNull()

    await click('I applied')
    expect(screen.getByText('Applied. Next: Data Analyst at Acme.')).toBeTruthy()
    await click('Next on the list')
    expect(onOpenJob).toHaveBeenCalledWith('bbbb00000002')

    const undo = toastSuccess.mock.calls.at(-1)?.[1]?.action
    await act(async () => { undo.onClick() })
    await flush()
    expect(screen.queryByText(/Next: Data Analyst/)).toBeNull()
  })

  it('offers the next job after Not for me', async () => {
    const { onOpenJob } = renderDrawer('aaaa00000001')
    await flush()

    await click('Not for me')
    fireEvent.change(screen.getByLabelText('Other reason'), { target: { value: 'Too far' } })
    await click('Close job')
    expect(jobs.aaaa00000001.funnel_stage).toBe('closed')
    expect(screen.getByText('Skipped. Next: Data Analyst at Acme.')).toBeTruthy()
    await click('Next on the list')
    expect(onOpenJob).toHaveBeenCalledWith('bbbb00000002')
  })

  it('says the list is done when nothing is left, and resets when switching jobs', async () => {
    jobs.bbbb00000002.funnel_stage = 'applied'
    const board = BOARD.map((j) => (j.job_id === 'bbbb00000002' ? { ...j, funnel_stage: 'applied' } : j))
    const { rerender } = renderDrawer('aaaa00000001', board)
    await flush()

    await click('I applied')
    expect(screen.getByText("That's the whole list done. Nice work.")).toBeTruthy()

    rerender('bbbb00000002')
    await flush()
    rerender('aaaa00000001')
    await flush()
    expect(screen.queryByText("That's the whole list done. Nice work.")).toBeNull()
  })
})

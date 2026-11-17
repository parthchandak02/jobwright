/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const listRuns = vi.fn()
const startJobTailor = vi.fn()

vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    status: number
    code?: string
    constructor(message: string, status: number, code?: string) {
      super(message)
      this.status = status
      this.code = code
    }
  }
  return {
    ApiError,
    listRuns: (...args: unknown[]) => listRuns(...args),
    startJobTailor: (...args: unknown[]) => startJobTailor(...args),
  }
})

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const attach = vi.fn()
const reset = vi.fn()
let trackerState: 'idle' | 'running' | 'error' | 'failed' = 'idle'
let onDoneCb: ((r: { failed: boolean; rc: number | null }) => void) | undefined

vi.mock('@/lib/useRunStream', () => ({
  useRunTracker: (opts: { onDone?: (r: { failed: boolean; rc: number | null }) => void }) => {
    onDoneCb = opts.onDone
    return {
      attach,
      reset,
      state: trackerState,
      begin: vi.fn(),
      fail: vi.fn(),
      finish: vi.fn(),
      active: false,
      handle: null,
      log: '',
      rc: null,
      stages: [],
      currentStage: null,
      completedCount: 0,
      progress: 0,
      elapsedMs: 0,
      stopping: false,
      start: vi.fn(),
      stop: vi.fn(),
    }
  },
}))

import { ApiError } from '@/lib/api'
import { usePrepareMaterials } from './usePrepareMaterials'

const handle = {
  run_id: 'run-1',
  pid: 1,
  started_at: '2026-11-17T12:00:00+00:00',
  kind: 'tailor',
  stages: ['tailor', 'cover', 'docx'],
  log_path: '/tmp/x.log',
  job_id: 'job-a',
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  trackerState = 'idle'
  onDoneCb = undefined
})

beforeEach(() => {
  listRuns.mockResolvedValue([])
  startJobTailor.mockResolvedValue(handle)
})

describe('usePrepareMaterials autoStart', () => {
  it('starts once under StrictMode double effect (server claim on second)', async () => {
    let calls = 0
    startJobTailor.mockImplementation(async () => {
      calls += 1
      if (calls === 1) return handle
      throw new ApiError('Prepare already auto-started for this job today', 409, 'prepare_auto_already')
    })
    // After the first spawn, listRuns can show the live run for the 409 path.
    listRuns
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValue([
        {
          run_id: 'run-1',
          running: true,
          job_id: 'job-a',
          kind: 'tailor',
          started_at: handle.started_at,
        },
      ])
    const { unmount } = renderHook(
      () => usePrepareMaterials('job-a', () => undefined, { autoStart: true }),
      { reactStrictMode: true },
    )
    await waitFor(() => expect(startJobTailor).toHaveBeenCalled())
    await waitFor(() => expect(attach).toHaveBeenCalled())
    // At most one successful spawn; a racing StrictMode remount gets 409.
    expect(startJobTailor.mock.calls.every((c) => c[2]?.auto === true)).toBe(true)
    expect(calls).toBeGreaterThanOrEqual(1)
    expect(calls).toBeLessThanOrEqual(2)
    unmount()
  })

  it('on remount after a failure, a 409 claim skip does not spawn another run', async () => {
    startJobTailor.mockRejectedValueOnce(new Error('boom'))
    const first = renderHook(() => usePrepareMaterials('job-a', () => undefined, { autoStart: true }))
    await waitFor(() => expect(first.result.current.error).toBeTruthy())
    first.unmount()

    startJobTailor.mockReset()
    listRuns.mockResolvedValue([])
    startJobTailor.mockRejectedValueOnce(
      new ApiError('Prepare already auto-started for this job today', 409, 'prepare_auto_already'),
    )
    const second = renderHook(() => usePrepareMaterials('job-a', () => undefined, { autoStart: true }))
    await waitFor(() => expect(startJobTailor).toHaveBeenCalledTimes(1))
    expect(second.result.current.error).toBeNull()
    expect(second.result.current.running).toBe(false)
    second.unmount()
  })

  it('does not start when switching to a job whose caller set autoStart false', async () => {
    const { rerender } = renderHook(
      ({ key, auto }: { key: string | null; auto: boolean }) =>
        usePrepareMaterials(key, () => undefined, { autoStart: auto }),
      { initialProps: { key: 'job-a', auto: true } },
    )
    await waitFor(() => expect(startJobTailor).toHaveBeenCalledWith('job-a', undefined, { auto: true }))
    startJobTailor.mockClear()
    listRuns.mockResolvedValue([])
    rerender({ key: 'job-b', auto: false })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(startJobTailor).not.toHaveBeenCalled()
  })

  it('attaches a live prepare run instead of starting another', async () => {
    listRuns.mockResolvedValue([
      {
        run_id: 'live-1',
        running: true,
        job_id: 'job-a',
        kind: 'tailor',
        started_at: '2026-11-17T12:00:00+00:00',
      },
    ])
    renderHook(() => usePrepareMaterials('job-a', () => undefined, { autoStart: true }))
    await waitFor(() => expect(attach).toHaveBeenCalled())
    expect(startJobTailor).not.toHaveBeenCalled()
    expect(attach).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'live-1' }),
      expect.any(Number),
    )
  })

  it('surfaces a start failure inline and keeps manual Prepare working', async () => {
    startJobTailor.mockRejectedValueOnce(new Error('no resume'))
    const { result } = renderHook(() => usePrepareMaterials('job-a', () => undefined, { autoStart: true }))
    await waitFor(() => expect(result.current.error).toMatch(/no resume/i))
    startJobTailor.mockResolvedValueOnce({ ...handle, run_id: 'manual' })
    await act(async () => {
      await result.current.start()
    })
    expect(startJobTailor).toHaveBeenLastCalledWith('job-a')
    expect(attach).toHaveBeenCalled()
  })

  it('does not auto-retry after the run reports failure', async () => {
    const { result, rerender } = renderHook(() =>
      usePrepareMaterials('job-a', () => undefined, { autoStart: true }),
    )
    await waitFor(() => expect(startJobTailor).toHaveBeenCalledTimes(1))
    act(() => {
      onDoneCb?.({ failed: true, rc: 1 })
    })
    await waitFor(() => expect(result.current.error).toMatch(/failed/i))
    startJobTailor.mockClear()
    rerender()
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(startJobTailor).not.toHaveBeenCalled()
  })
})

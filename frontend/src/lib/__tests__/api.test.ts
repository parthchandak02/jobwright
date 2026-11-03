import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch } from '@/lib/api'

function stubFetch(response: Response) {
  const fetchMock = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError)
    return err as ApiError
  }
  throw new Error('expected a rejection')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ApiError', () => {
  it('keeps message, status and code', () => {
    const err = new ApiError('nope', 403, 'no_profile')
    expect(err).toBeInstanceOf(Error)
    expect([err.message, err.status, err.code]).toEqual(['nope', 403, 'no_profile'])
  })
})

describe('apiFetch error parsing', () => {
  it('uses a string detail', async () => {
    stubFetch(Response.json({ detail: 'Upload your resume first.' }, { status: 400 }))
    const err = await caught(apiFetch('/x'))
    expect([err.message, err.status, err.code]).toEqual(['Upload your resume first.', 400, undefined])
  })

  it('reads detail and code from an object detail', async () => {
    stubFetch(Response.json({ detail: { detail: 'Pick a chat', code: 'no_chat' } }, { status: 409 }))
    const err = await caught(apiFetch('/x'))
    expect([err.message, err.status, err.code]).toEqual(['Pick a chat', 409, 'no_chat'])
  })

  it('reads a top-level code (middleware errors)', async () => {
    stubFetch(Response.json({ detail: 'No profile for this login yet.', code: 'no_profile' }, { status: 403 }))
    const err = await caught(apiFetch('/x'))
    expect([err.message, err.code]).toEqual(['No profile for this login yet.', 'no_profile'])
  })

  it('stringifies bodies without a detail', async () => {
    stubFetch(Response.json({ error: 'boom' }, { status: 500 }))
    const err = await caught(apiFetch('/x'))
    expect(err.message).toBe('{"error":"boom"}')
  })

  it('falls back to the status text for non-JSON bodies', async () => {
    stubFetch(new Response('<html>bad gateway</html>', { status: 502, statusText: 'Bad Gateway' }))
    const err = await caught(apiFetch('/x'))
    expect([err.message, err.status]).toEqual(['Bad Gateway', 502])
  })

  it('returns parsed JSON and sends credentials on success', async () => {
    const fetchMock = stubFetch(Response.json({ ok: true }))
    await expect(apiFetch('/me')).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/me', expect.objectContaining({ credentials: 'include' }))
  })
})

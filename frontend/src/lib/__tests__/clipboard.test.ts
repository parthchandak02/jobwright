import { afterEach, describe, expect, it, vi } from 'vitest'

import { hasCopyableMarkdown, writeClipboardText } from '@/lib/clipboard'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('hasCopyableMarkdown', () => {
  it('is false when markdown is missing or blank', () => {
    expect(hasCopyableMarkdown(null)).toBe(false)
    expect(hasCopyableMarkdown(undefined)).toBe(false)
    expect(hasCopyableMarkdown('')).toBe(false)
    expect(hasCopyableMarkdown('   \n\t  ')).toBe(false)
  })

  it('is true when markdown has content', () => {
    expect(hasCopyableMarkdown('# Alex Rivera\n\nEngineer')).toBe(true)
  })
})

describe('writeClipboardText', () => {
  it('writes the markdown string to the clipboard', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const markdown = '## Cover letter\n\nDear hiring team,'
    await expect(writeClipboardText(markdown)).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(writeText).toHaveBeenCalledWith(markdown)
  })

  it('returns false when the clipboard write fails', async () => {
    const writeText = vi.fn(async () => {
      throw new Error('denied')
    })
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await expect(writeClipboardText('x')).resolves.toBe(false)
  })
})

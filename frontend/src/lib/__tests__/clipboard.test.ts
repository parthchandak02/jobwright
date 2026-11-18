import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  hasCopyableMarkdown,
  markdownToPlainText,
  materialsCopyPlainText,
  writeClipboardText,
} from '@/lib/clipboard'

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

describe('markdownToPlainText', () => {
  it('strips headings, emphasis and links but keeps bullets and line breaks', () => {
    const plain = markdownToPlainText(
      [
        '# Alex Rivera',
        '',
        '**Senior** engineer at [Example](https://example.com).',
        '',
        '- Shipped _products_',
        '- Led *teams*',
        '',
        'See ![logo](https://example.com/logo.png) notes.',
      ].join('\n'),
    )

    expect(plain).toContain('Alex Rivera')
    expect(plain).toContain('Senior engineer at Example.')
    expect(plain).toContain('- Shipped products')
    expect(plain).toContain('- Led teams')
    expect(plain).toContain('See logo notes.')
    expect(plain).not.toMatch(/[#*_`[\]]/)
    expect(plain).toContain('\n')
  })
})

describe('materialsCopyPlainText', () => {
  it('returns null when Copy should stay disabled', () => {
    expect(materialsCopyPlainText(null)).toBeNull()
    expect(materialsCopyPlainText(undefined)).toBeNull()
    expect(materialsCopyPlainText('')).toBeNull()
    expect(materialsCopyPlainText('   \n')).toBeNull()
  })

  it('returns plain text without Markdown symbols when copyable', () => {
    const plain = materialsCopyPlainText('## Cover\n\nDear **team**,')
    expect(plain).not.toBeNull()
    expect(plain).toContain('Cover')
    expect(plain).toContain('Dear team,')
    expect(plain!).not.toMatch(/[#*_]/)
  })
})

describe('writeClipboardText', () => {
  it('writes plain text via the Clipboard API when available', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await expect(writeClipboardText('Dear hiring team,')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(writeText).toHaveBeenCalledWith('Dear hiring team,')
  })

  it('falls back to execCommand when Clipboard API is missing', async () => {
    vi.stubGlobal('navigator', {})

    const textarea = {
      value: '',
      style: {} as Record<string, string>,
      setAttribute: vi.fn(),
      focus: vi.fn(),
      select: vi.fn(),
    }
    const body = {
      appendChild: vi.fn(),
      removeChild: vi.fn(),
    }
    const execCommand = vi.fn(() => true)
    vi.stubGlobal('document', {
      createElement: vi.fn((tag: string) => {
        expect(tag).toBe('textarea')
        return textarea
      }),
      body,
      execCommand,
    })

    await expect(writeClipboardText('paste me')).resolves.toBe(true)
    expect(textarea.value).toBe('paste me')
    expect(body.appendChild).toHaveBeenCalledWith(textarea)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(body.removeChild).toHaveBeenCalledWith(textarea)
  })

  it('falls back to execCommand when Clipboard API throws', async () => {
    const writeText = vi.fn(async () => {
      throw new Error('denied')
    })
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const textarea = {
      value: '',
      style: {} as Record<string, string>,
      setAttribute: vi.fn(),
      focus: vi.fn(),
      select: vi.fn(),
    }
    const execCommand = vi.fn(() => true)
    vi.stubGlobal('document', {
      createElement: vi.fn(() => textarea),
      body: { appendChild: vi.fn(), removeChild: vi.fn() },
      execCommand,
    })

    await expect(writeClipboardText('retry')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalled()
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('returns false when both clipboard paths fail', async () => {
    const writeText = vi.fn(async () => {
      throw new Error('denied')
    })
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    vi.stubGlobal('document', {
      createElement: vi.fn(() => {
        throw new Error('no document')
      }),
      body: { appendChild: vi.fn(), removeChild: vi.fn() },
      execCommand: vi.fn(() => false),
    })

    await expect(writeClipboardText('x')).resolves.toBe(false)
  })
})

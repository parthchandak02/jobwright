import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadPdf, fileNameFrom } from './JobMaterialsPreview'

describe('tailored PDF download', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads the file name the server sends', () => {
    expect(fileNameFrom("attachment; filename*=utf-8''Alex%20Rivera%20-%20Resume.pdf")).toBe(
      'Alex Rivera - Resume.pdf',
    )
    expect(fileNameFrom('attachment; filename="Resume.pdf"')).toBe('Resume.pdf')
    expect(fileNameFrom(null)).toBe('Resume.pdf')
  })

  it('reports failure when the PDF cannot be made', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('PDF not available', { status: 503 })))
    expect(await downloadPdf('/api/jobs/x/materials/resume.pdf?download=1')).toBe(false)
  })
})

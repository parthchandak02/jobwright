import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ProfileMaterials } from '@/components/ProfileMaterials'
import { apiFetch, apiUpload, type SettingsData } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  data: SettingsData
  reload: () => Promise<void>
  onProfileChanged: () => void
}

export function DocumentsTab({ data, reload, onProfileChanged }: Props) {
  const [busy, setBusy] = useState<null | 'resume' | 'cover'>(null)
  const resumeFileRef = useRef<HTMLInputElement>(null)
  const coverFileRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    await reload()
    onProfileChanged()
  }

  async function uploadResumePdf(file: File | undefined) {
    if (!file) return
    setBusy('resume')
    try {
      await apiUpload('/settings/resume.pdf', file)
      toast.success('Resume saved.')
      await refresh()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  async function uploadCoverPdfs(files: FileList | File[] | undefined) {
    if (!files || files.length === 0) return
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) {
      toast.error('Please add PDF files.')
      return
    }
    setBusy('cover')
    try {
      for (const file of pdfs) {
        await apiUpload('/settings/cover-letters', file)
      }
      toast.success(
        pdfs.length === 1
          ? 'Cover letter added. We’ll use it for your next letters.'
          : `${pdfs.length} cover letters added. We’ll use them for your next letters.`,
      )
      await refresh()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  async function removeCoverPdf(id: string) {
    setBusy('cover')
    try {
      await apiFetch(`/settings/cover-letters/${encodeURIComponent(id)}`, { method: 'DELETE' })
      toast.success('Cover letter removed.')
      await refresh()
    } catch (e) {
      toast.error(errorMessage(e))
      throw e
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <input
        ref={resumeFileRef}
        type="file"
        accept="application/pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          void uploadResumePdf(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      <input
        ref={coverFileRef}
        type="file"
        accept="application/pdf"
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          void uploadCoverPdfs(e.target.files ?? undefined)
          e.target.value = ''
        }}
      />
      <ProfileMaterials
        resume={{
          pdfUrl: data.has_resume_pdf ? `/api/settings/resume.pdf?t=${data.resume_pdf_mtime ?? 0}` : null,
          markdown: data.resume_markdown,
          updatedAt: data.resume_pdf_mtime,
          replacing: busy === 'resume',
          onReplace: () => resumeFileRef.current?.click(),
        }}
        examples={data.cover_letter_examples || []}
        uploading={busy === 'cover'}
        onAddCovers={() => coverFileRef.current?.click()}
        onDropCovers={(files) => void uploadCoverPdfs(files)}
        onRemoveCover={removeCoverPdf}
      />
    </div>
  )
}

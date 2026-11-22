import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Check, Copy, Download, SlidersHorizontal } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Segmented } from '@/components/ui/segmented'
import {
  hasCopyableMarkdown,
  materialsCopyPlainText,
  writeClipboardText,
} from '@/lib/clipboard'
import { cn } from '@/lib/utils'

export type MaterialViewOption = {
  key: string
  label: string
  pdfUrl: string | null
  markdown: string
  pdfTitle: string
  emptyPdf?: string
  emptyMarkdown?: string
}

type Props = {
  views: MaterialViewOption[]
  viewKey: string
  onViewKeyChange: (key: string) => void
  /** Tailored DOCX/PDF paths; download menu only when the active view key is `tailored`. */
  tailoredDocx?: string | null
  tailoredPdf?: string | null
  /** Route that renders (if needed) and downloads the upload-ready tailored PDF. */
  pdfDownloadUrl?: string | null
  tailorActions?: ReactNode
  className?: string
}

const PDF_VIEWER_HASH = '#toolbar=0&navpanes=0&scrollbar=1&zoom=page-width'

function pdfViewerSrc(url: string): string {
  return `${url.split('#')[0]}${PDF_VIEWER_HASH}`
}

function download(path: string) {
  window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
}

export const PDF_UNAVAILABLE = 'PDF not available, download Word instead'

export function fileNameFrom(disposition: string | null): string {
  const star = disposition?.match(/filename\*=utf-8''([^;]+)/i)
  if (star) return decodeURIComponent(star[1])
  return disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? 'Resume.pdf'
}

/** Fetch first so a failed render shows our message instead of a raw error page. */
export async function downloadPdf(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { credentials: 'same-origin' })
    if (!res.ok) return false
    const href = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = href
    a.download = fileNameFrom(res.headers.get('content-disposition'))
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(href), 10_000)
    return true
  } catch {
    return false
  }
}

function MaterialsCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const plain = materialsCopyPlainText(text)

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      className="h-9 shrink-0 gap-1.5 px-2.5"
      disabled={!plain}
      aria-label="Copy text"
      onClick={() => {
        if (!plain) return
        void (async () => {
          const ok = await writeClipboardText(plain)
          if (!ok) {
            toast.error('Copy failed')
            return
          }
          setCopied(true)
          toast.success('Copied')
          window.setTimeout(() => setCopied(false), 1500)
        })()
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      <span aria-live="polite" className="hidden @min-[22rem]/preview:inline">
        {copied ? 'Copied' : 'Copy text'}
      </span>
    </Button>
  )
}

export function JobMaterialsPreview({
  views,
  viewKey,
  onViewKeyChange,
  tailoredDocx,
  tailoredPdf,
  pdfDownloadUrl,
  tailorActions,
  className,
}: Props) {
  const [pdfBusy, setPdfBusy] = useState(false)
  const [pdfError, setPdfError] = useState(false)
  const active = useMemo(
    () => views.find((v) => v.key === viewKey) ?? views[0],
    [views, viewKey],
  )

  const defaultFormat = active?.pdfUrl ? 'pdf' : 'markdown'
  const [format, setFormat] = useState<'pdf' | 'markdown'>(defaultFormat)

  useEffect(() => {
    setFormat(active?.pdfUrl ? 'pdf' : 'markdown')
  }, [active?.key, active?.pdfUrl])

  if (!active) {
    return (
      <div className="materials-preview-frame flex min-h-[10rem] items-center px-4 py-3">
        <p className="text-body text-muted-foreground">Nothing to preview yet.</p>
      </div>
    )
  }

  const hasMarkdown = hasCopyableMarkdown(active.markdown)
  const isTailored = viewKey === 'tailored'
  const showPdfButton = isTailored && Boolean(pdfDownloadUrl)
  const showDownload = isTailored && !pdfDownloadUrl && (tailoredDocx || tailoredPdf)

  async function onDownloadPdf() {
    if (!pdfDownloadUrl) return
    setPdfBusy(true)
    const ok = await downloadPdf(pdfDownloadUrl)
    setPdfBusy(false)
    setPdfError(!ok)
    if (!ok) toast.error(PDF_UNAVAILABLE)
  }

  return (
    <div className={cn('materials-preview-frame @container/preview', className)}>
      <div className="materials-preview-toolbar">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Select value={viewKey} onValueChange={onViewKeyChange}>
            <SelectTrigger
              className="h-9 min-w-0 flex-1 basis-[10rem] @min-[26rem]/preview:max-w-[16rem]"
              aria-label="Choose which version to preview"
            >
              <SelectValue placeholder="Choose version" />
            </SelectTrigger>
            <SelectContent>
              {views.map((view) => (
                <SelectItem key={view.key} value={view.key}>
                  {view.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Segmented
            value={format}
            onValueChange={setFormat}
            aria-label="Show as"
            className="shrink-0"
            itemClassName="px-2.5 text-caption"
            options={[
              { value: 'pdf', label: 'PDF', disabled: !active.pdfUrl },
              { value: 'markdown', label: 'Markdown' },
            ]}
          />

          <MaterialsCopyButton text={active.markdown} />

          {showPdfButton ? (
            <>
              <Button
                type="button"
                size="sm"
                className="h-9 shrink-0 gap-1.5 px-2.5"
                disabled={pdfBusy}
                onClick={() => void onDownloadPdf()}
              >
                <Download className="size-3.5" />
                {pdfBusy ? 'Making PDF…' : 'Download PDF'}
              </Button>
              {tailoredDocx ? (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="h-9 shrink-0 px-2.5"
                  aria-label="Download Word file"
                  onClick={() => download(tailoredDocx)}
                >
                  Word
                </Button>
              ) : null}
            </>
          ) : null}

          {showDownload ? (
            <Select
              onValueChange={(v) => {
                if (v === 'docx' && tailoredDocx) download(tailoredDocx)
                if (v === 'pdf' && tailoredPdf) download(tailoredPdf)
              }}
            >
              <SelectTrigger
                className="h-9 w-auto shrink-0 gap-1.5 px-2.5"
                aria-label="Download tailored file"
              >
                <Download className="size-3.5" />
                <span className="hidden @min-[22rem]/preview:inline">Download</span>
              </SelectTrigger>
              <SelectContent>
                {tailoredDocx ? <SelectItem value="docx">DOCX</SelectItem> : null}
                {tailoredPdf ? <SelectItem value="pdf">PDF</SelectItem> : null}
              </SelectContent>
            </Select>
          ) : null}
        </div>

        {showPdfButton && pdfError ? (
          <p role="status" className="basis-full text-caption text-muted-foreground">
            {PDF_UNAVAILABLE}
          </p>
        ) : null}

        {tailorActions ? (
          <div className="flex flex-wrap items-center gap-2">{tailorActions}</div>
        ) : null}
      </div>

      <div className="materials-preview-body">
        {format === 'pdf' ? (
          active.pdfUrl ? (
            <iframe
              title={active.pdfTitle}
              className="materials-pdf-frame"
              src={pdfViewerSrc(active.pdfUrl)}
            />
          ) : (
            <p className="px-4 py-6 text-body text-muted-foreground">
              {active.emptyPdf ?? 'No PDF for this version.'}
            </p>
          )
        ) : hasMarkdown ? (
          <div className="materials-preview materials-preview-body-md">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
              {active.markdown}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="px-4 py-6 text-body text-muted-foreground">
            {active.emptyMarkdown ?? 'No markdown for this version.'}
          </p>
        )}
      </div>
    </div>
  )
}

/** Shared tailor action pair for materials sections. */
export function MaterialsTailorActions({
  autoButton,
  onCustom,
  customDisabled,
}: {
  autoButton: ReactNode
  onCustom: () => void
  customDisabled?: boolean
}) {
  return (
    <>
      {autoButton}
      <Button type="button" size="sm" variant="secondary" disabled={customDisabled} onClick={onCustom}>
        <SlidersHorizontal />
        Custom
      </Button>
    </>
  )
}

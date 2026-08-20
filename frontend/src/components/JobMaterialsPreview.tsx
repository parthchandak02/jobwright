import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Download, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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

export function JobMaterialsPreview({
  views,
  viewKey,
  onViewKeyChange,
  tailoredDocx,
  tailoredPdf,
  tailorActions,
  className,
}: Props) {
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
        <p className="text-sm text-muted-foreground">Nothing to preview yet.</p>
      </div>
    )
  }

  const hasMarkdown = active.markdown.trim().length > 0
  const showDownload = viewKey === 'tailored' && (tailoredDocx || tailoredPdf)

  return (
    <div className={cn('materials-preview-frame @container/preview', className)}>
      <div className="materials-preview-toolbar">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Select value={viewKey} onValueChange={onViewKeyChange}>
            <SelectTrigger
              className="h-8 min-w-0 flex-1 basis-[10rem] @min-[26rem]/preview:max-w-[16rem]"
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

          <Tabs
            value={format}
            onValueChange={(v) => setFormat(v as 'pdf' | 'markdown')}
            className="shrink-0"
          >
            <TabsList className="h-8">
              <TabsTrigger value="pdf" disabled={!active.pdfUrl} className="px-2.5 text-xs">
                PDF
              </TabsTrigger>
              <TabsTrigger value="markdown" className="px-2.5 text-xs">
                Markdown
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {showDownload ? (
            <Select
              onValueChange={(v) => {
                if (v === 'docx' && tailoredDocx) download(tailoredDocx)
                if (v === 'pdf' && tailoredPdf) download(tailoredPdf)
              }}
            >
              <SelectTrigger
                className="h-8 w-auto shrink-0 gap-1.5 px-2.5"
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
            <p className="px-4 py-6 text-sm text-muted-foreground">
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
          <p className="px-4 py-6 text-sm text-muted-foreground">
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
      <Button type="button" size="sm" variant="ai" disabled={customDisabled} onClick={onCustom}>
        <Sparkles />
        Custom
      </Button>
    </>
  )
}

import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { cn } from '@/lib/utils'

export type ResumePreviewProps = {
  pdfUrl: string | null
  markdown: string
  className?: string
  actions?: ReactNode
  pdfTitle?: string
  emptyPdf?: string
  emptyMarkdown?: string
}

type View = 'pdf' | 'text'

const PDF_VIEWER_HASH = '#toolbar=0&navpanes=0&scrollbar=1&zoom=page-width'

function pdfViewerSrc(url: string): string {
  return `${url.split('#')[0]}${PDF_VIEWER_HASH}`
}

function prefersText(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
}

export function ResumePreview({
  pdfUrl,
  markdown,
  className,
  actions,
  pdfTitle = 'Resume PDF preview',
  emptyPdf = 'No PDF on file.',
  emptyMarkdown = 'The text version appears a moment after the PDF is uploaded.',
}: ResumePreviewProps) {
  const [view, setView] = useState<View>(() => (pdfUrl && !prefersText() ? 'pdf' : 'text'))

  useEffect(() => {
    if (!pdfUrl) setView('text')
  }, [pdfUrl])

  const hasMarkdown = markdown.trim().length > 0

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          size="sm"
          aria-label="Preview format"
          value={view}
          onValueChange={setView}
          options={[
            { value: 'pdf', label: 'PDF', disabled: !pdfUrl },
            { value: 'text', label: 'Text' },
          ]}
        />
        <div className="ml-auto flex items-center gap-1">
          {pdfUrl ? (
            <Button asChild size="sm" variant="ghost">
              <a href={pdfUrl.split('#')[0]} target="_blank" rel="noreferrer">
                <ExternalLink />
                Open PDF
              </a>
            </Button>
          ) : null}
          {actions}
        </div>
      </div>

      {view === 'pdf' ? (
        pdfUrl ? (
          <iframe
            title={pdfTitle}
            className="block h-[min(80vh,960px)] w-full rounded-lg border bg-surface"
            src={pdfViewerSrc(pdfUrl)}
          />
        ) : (
          <p className="rounded-lg bg-surface-muted px-4 py-3 text-caption text-muted-foreground">{emptyPdf}</p>
        )
      ) : hasMarkdown ? (
        <div className="materials-preview max-h-[70vh] overflow-y-auto overscroll-contain rounded-lg border bg-surface px-4 py-4 text-body md:px-6 md:py-5">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{markdown}</ReactMarkdown>
        </div>
      ) : (
        <p className="rounded-lg bg-surface-muted px-4 py-3 text-caption text-muted-foreground">{emptyMarkdown}</p>
      )}
    </div>
  )
}

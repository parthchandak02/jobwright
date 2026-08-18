import type { ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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

const PDF_VIEWER_HASH = '#toolbar=0&navpanes=0&scrollbar=1&zoom=page-width'

function pdfViewerSrc(url: string): string {
  const base = url.split('#')[0]
  return `${base}${PDF_VIEWER_HASH}`
}

export function ResumePreview({
  pdfUrl,
  markdown,
  className,
  actions,
  pdfTitle = 'Resume PDF preview',
  emptyPdf = 'No PDF on file.',
  emptyMarkdown = 'No markdown yet. It appears after the PDF is converted on the server.',
}: ResumePreviewProps) {
  const defaultTab = useMemo(() => (pdfUrl ? 'pdf' : 'markdown'), [pdfUrl])
  const [tab, setTab] = useState(defaultTab)

  useEffect(() => {
    setTab(defaultTab)
  }, [defaultTab])

  const hasMarkdown = markdown.trim().length > 0

  return (
    <div className={cn('space-y-2', className)}>
      <Tabs value={tab} onValueChange={setTab} className="gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList className="h-8">
            <TabsTrigger value="pdf" disabled={!pdfUrl}>
              PDF
            </TabsTrigger>
            <TabsTrigger value="markdown">Markdown</TabsTrigger>
          </TabsList>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>

        <TabsContent value="pdf">
          {pdfUrl ? (
            <iframe
              title={pdfTitle}
              className="resume-pdf-frame"
              src={pdfViewerSrc(pdfUrl)}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{emptyPdf}</p>
          )}
        </TabsContent>

        <TabsContent value="markdown">
          {hasMarkdown ? (
            <div className="materials-preview resume-md-pane">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{markdown}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{emptyMarkdown}</p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

export type MaterialsData = {
  resume_md: string | null
  resume_docx: string | null
  cover_md: string | null
  cover_docx: string | null
  resume_preview?: string | null
  cover_preview?: string | null
}

type Props = {
  materials: MaterialsData | null
  className?: string
}

type PreviewKind = 'resume' | 'cover'

function download(path: string | null) {
  if (!path) return
  window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
}

export function MaterialsPanel({ materials, className }: Props) {
  const hasResume = !!(materials?.resume_preview || materials?.resume_md || materials?.resume_docx)
  const hasCover = !!(materials?.cover_preview || materials?.cover_md || materials?.cover_docx)
  const hasAny = hasResume || hasCover

  const defaultTab = useMemo(() => {
    if (hasResume) return 'resume'
    if (hasCover) return 'cover'
    return 'resume'
  }, [hasResume, hasCover])

  const [tab, setTab] = useState(defaultTab)

  useEffect(() => {
    setTab(defaultTab)
  }, [defaultTab])

  if (!hasAny) return null

  const downloadPath = tab === 'cover' ? materials?.cover_docx : materials?.resume_docx

  return (
    <div className={cn('space-y-2', className)}>
      <Tabs value={tab} onValueChange={setTab} className="gap-2">
        <div className="flex items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="resume" disabled={!hasResume}>
              Resume
            </TabsTrigger>
            <TabsTrigger value="cover" disabled={!hasCover}>
              Cover
            </TabsTrigger>
          </TabsList>
          {downloadPath ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="shrink-0"
              onClick={() => download(downloadPath)}
            >
              <Download />
              Download DOCX
            </Button>
          ) : null}
        </div>
        <TabsContent value="resume">
          <PreviewPane markdown={materials?.resume_preview} kind="resume" />
        </TabsContent>
        <TabsContent value="cover">
          <PreviewPane markdown={materials?.cover_preview} kind="cover" />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function PreviewPane({ markdown, kind }: { markdown?: string | null; kind: PreviewKind }) {
  if (!markdown?.trim()) {
    return (
      <div className="flex min-h-[10rem] items-center rounded-md border border-border/60 bg-muted/30 px-4 py-3">
        <p className="text-sm text-muted-foreground">Not generated yet</p>
      </div>
    )
  }
  return (
    <div
      className={cn(
        'materials-preview max-h-80 min-h-[10rem] overflow-y-auto rounded-md border border-border/60 bg-muted/30 px-4 py-3 text-sm leading-relaxed text-foreground/90',
        kind === 'cover' && 'materials-preview-cover',
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{markdown}</ReactMarkdown>
    </div>
  )
}

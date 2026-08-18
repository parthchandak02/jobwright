import { useEffect, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

export type MaterialsData = {
  resume_txt: string | null
  resume_docx: string | null
  cover_txt: string | null
  cover_docx: string | null
  resume_preview?: string | null
  cover_preview?: string | null
}

type Props = {
  materials: MaterialsData | null
  className?: string
}

function download(path: string | null) {
  if (!path) return
  window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
}

export function MaterialsPanel({ materials, className }: Props) {
  const hasResume = !!(materials?.resume_preview || materials?.resume_txt || materials?.resume_docx)
  const hasCover = !!(materials?.cover_preview || materials?.cover_txt || materials?.cover_docx)
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

  const downloadPath =
    tab === 'cover'
      ? materials?.cover_docx || materials?.cover_txt
      : materials?.resume_docx || materials?.resume_txt
  const downloadLabel =
    tab === 'cover'
      ? materials?.cover_docx
        ? 'Download DOCX'
        : 'Download TXT'
      : materials?.resume_docx
        ? 'Download DOCX'
        : 'Download TXT'

  return (
    <div className={cn('space-y-2', className)}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="resume" disabled={!hasResume}>
            Resume
          </TabsTrigger>
          <TabsTrigger value="cover" disabled={!hasCover}>
            Cover
          </TabsTrigger>
        </TabsList>
        <TabsContent value="resume">
          <PreviewPane text={materials?.resume_preview} />
        </TabsContent>
        <TabsContent value="cover">
          <PreviewPane text={materials?.cover_preview} />
        </TabsContent>
      </Tabs>
      {downloadPath ? (
        <button
          type="button"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => download(downloadPath)}
        >
          <Download className="size-3" />
          {downloadLabel}
        </button>
      ) : null}
    </div>
  )
}

function PreviewPane({ text }: { text?: string | null }) {
  if (!text?.trim()) {
    return (
      <div className="flex max-h-48 min-h-[6rem] items-center rounded-md border border-border/60 bg-muted/30 px-3 py-2">
        <p className="text-xs text-muted-foreground">Not generated yet</p>
      </div>
    )
  }
  return (
    <div className="max-h-48 overflow-y-auto rounded-md border border-border/60 bg-muted/30 p-3 text-xs leading-relaxed whitespace-pre-wrap text-foreground/90">
      {text}
    </div>
  )
}

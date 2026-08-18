import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { CustomTailorDialog } from '@/components/CustomTailorDialog'
import { RunProgressButton } from '@/components/RunProgressButton'
import { RunProgressDialog } from '@/components/RunProgressDialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { STAGE_LABELS } from '@/lib/useAutoSearch'
import { useTailorMaterials } from '@/lib/useTailorMaterials'
import type { TailorInstructions } from '@/lib/api'
import { cn } from '@/lib/utils'

export type MaterialsData = {
  resume_md: string | null
  resume_docx: string | null
  cover_md: string | null
  cover_docx: string | null
  resume_pdf?: string | null
  cover_pdf?: string | null
  resume_preview?: string | null
  cover_preview?: string | null
}

type Props = {
  materials: MaterialsData | null
  className?: string
  jobUrl?: string
  onTailored?: () => void
}

type PreviewKind = 'resume' | 'cover'

function download(path: string | null | undefined) {
  if (!path) return
  window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
}

export function MaterialsPanel({ materials, className, jobUrl, onTailored }: Props) {
  const hasResume = !!(materials?.resume_preview || materials?.resume_md || materials?.resume_docx)
  const hasCover = !!(materials?.cover_preview || materials?.cover_md || materials?.cover_docx)
  const hasAny = hasResume || hasCover
  const showPanel = hasAny || !!jobUrl

  const defaultTab = useMemo(() => {
    if (hasResume) return 'resume'
    if (hasCover) return 'cover'
    return 'resume'
  }, [hasResume, hasCover])

  const [tab, setTab] = useState(defaultTab)
  const [logOpen, setLogOpen] = useState(false)
  const [customOpen, setCustomOpen] = useState(false)
  const tailor = useTailorMaterials(jobUrl, () => onTailored?.())
  const prevTailorState = useRef(tailor.state)

  useEffect(() => {
    setTab(defaultTab)
  }, [defaultTab])

  useEffect(() => {
    const prev = prevTailorState.current
    prevTailorState.current = tailor.state
    if (prev === 'starting' && tailor.state === 'running' && !logOpen) {
      toast.success('Auto Tailor running in the background. Click Auto Tailor again for logs.')
    }
    if (prev !== 'starting' && prev !== 'running') return
    if (tailor.state === 'finished') toast.success('Tailor finished')
    if (tailor.state === 'failed' || tailor.state === 'error') {
      toast.error('Tailor failed. Click Auto Tailor to view logs.')
    }
  }, [tailor.state, logOpen])

  function onAutoTailor() {
    if (tailor.active) {
      setLogOpen(true)
      return
    }
    tailor.start()
  }

  function onCustomStart(instructions: TailorInstructions) {
    setCustomOpen(false)
    tailor.start(instructions)
    setLogOpen(true)
  }

  if (!showPanel) return null

  const docxPath = tab === 'cover' ? materials?.cover_docx : materials?.resume_docx
  const pdfPath = tab === 'cover' ? materials?.cover_pdf : materials?.resume_pdf

  return (
    <div className={cn('space-y-2', className)}>
      <Tabs value={tab} onValueChange={setTab} className="gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList>
            <TabsTrigger value="resume" disabled={!hasResume}>
              Resume
            </TabsTrigger>
            <TabsTrigger value="cover" disabled={!hasCover}>
              Cover
            </TabsTrigger>
          </TabsList>
          <div className="flex flex-wrap items-center gap-2">
            {jobUrl ? (
              <>
                <RunProgressButton
                  run={tailor}
                  idleLabel="Auto Tailor"
                  stageLabels={STAGE_LABELS}
                  titleIdle="Keyword pass in the background. Click again for logs."
                  titleActive="Tailoring in progress. Click to view logs"
                  onClick={onAutoTailor}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ai"
                  disabled={tailor.active}
                  onClick={() => setCustomOpen(true)}
                >
                  <Sparkles />
                  Custom Tailor
                </Button>
              </>
            ) : null}
            {docxPath ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="shrink-0"
                onClick={() => download(docxPath)}
              >
                <Download />
                DOCX
              </Button>
            ) : null}
            {pdfPath ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="shrink-0"
                onClick={() => download(pdfPath)}
              >
                <Download />
                PDF
              </Button>
            ) : null}
          </div>
        </div>
        <TabsContent value="resume">
          <PreviewPane markdown={materials?.resume_preview} kind="resume" />
        </TabsContent>
        <TabsContent value="cover">
          <PreviewPane markdown={materials?.cover_preview} kind="cover" />
        </TabsContent>
      </Tabs>
      <CustomTailorDialog
        open={customOpen}
        onClose={() => setCustomOpen(false)}
        onStart={onCustomStart}
        starting={tailor.active}
      />
      <RunProgressDialog
        open={logOpen}
        onClose={() => setLogOpen(false)}
        title="Tailor Resume & Cover Letter"
        description="Keyword pass on your base resume, then a cover letter from your samples. Closing this window does not stop the run."
        stageLabels={STAGE_LABELS}
        run={tailor}
      />
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

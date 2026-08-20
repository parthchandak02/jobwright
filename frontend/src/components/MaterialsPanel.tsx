import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CustomTailorDialog } from '@/components/CustomTailorDialog'
import {
  JobMaterialsPreview,
  MaterialsTailorActions,
  type MaterialViewOption,
} from '@/components/JobMaterialsPreview'
import { RunProgressButton } from '@/components/RunProgressButton'
import { RunProgressDialog } from '@/components/RunProgressDialog'
import type { CoverLetterExample, SettingsData } from '@/lib/api'
import { STAGE_LABELS } from '@/lib/useAutoSearch'
import { useTailorMaterials } from '@/lib/useTailorMaterials'
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
  settings: SettingsData | null
  className?: string
  jobUrl?: string
  onTailored?: () => void
}

function coverExampleName(example: CoverLetterExample): string {
  return example.filename.replace(/\.(pdf|txt)$/i, '').replaceAll('_', ' ')
}

function useTailorToasts(
  run: ReturnType<typeof useTailorMaterials>,
  logOpen: boolean,
  label: string,
) {
  const prev = useRef(run.state)
  useEffect(() => {
    const was = prev.current
    prev.current = run.state
    if (was === 'starting' && run.state === 'running' && !logOpen) {
      toast.success(`${label} running in the background. Click Auto Tailor again for logs.`)
    }
    if (was !== 'starting' && was !== 'running') return
    if (run.state === 'finished') toast.success(`${label} finished`)
    if (run.state === 'failed' || run.state === 'error') {
      toast.error(`${label} failed. Click Auto Tailor to view logs.`)
    }
  }, [run.state, logOpen, label])
}

type MaterialSectionShellProps = {
  jobUrl?: string
  views: MaterialViewOption[]
  viewKey: string
  onViewKeyChange: (key: string) => void
  tailoredDocx?: string | null
  tailoredPdf?: string | null
  tailor: ReturnType<typeof useTailorMaterials>
  customOpen: boolean
  onCustomOpen: (open: boolean) => void
  logOpen: boolean
  onLogOpen: (open: boolean) => void
  onCustomStart: (instructions: string) => void
  tailorScope: 'resume' | 'cover'
  logTitle: string
  logDescription: string
}

function MaterialSectionShell({
  jobUrl,
  views,
  viewKey,
  onViewKeyChange,
  tailoredDocx,
  tailoredPdf,
  tailor,
  customOpen,
  onCustomOpen,
  logOpen,
  onLogOpen,
  onCustomStart,
  tailorScope,
  logTitle,
  logDescription,
}: MaterialSectionShellProps) {
  function onAutoTailor() {
    if (tailor.active) {
      onLogOpen(true)
      return
    }
    tailor.start()
  }

  return (
    <>
      <JobMaterialsPreview
        views={views}
        viewKey={viewKey}
        onViewKeyChange={onViewKeyChange}
        tailoredDocx={tailoredDocx}
        tailoredPdf={tailoredPdf}
        tailorActions={
          jobUrl ? (
            <MaterialsTailorActions
              customDisabled={tailor.active}
              onCustom={() => onCustomOpen(true)}
              autoButton={
                <RunProgressButton
                  run={tailor}
                  idleLabel="Auto Tailor"
                  stageLabels={STAGE_LABELS}
                  titleIdle="Runs in the background. Click again for logs."
                  titleActive="Tailoring in progress. Click to view logs"
                  onClick={onAutoTailor}
                />
              }
            />
          ) : null
        }
      />
      <CustomTailorDialog
        open={customOpen}
        onClose={() => onCustomOpen(false)}
        onStart={onCustomStart}
        starting={tailor.active}
        scope={tailorScope}
      />
      <RunProgressDialog
        open={logOpen}
        onClose={() => onLogOpen(false)}
        title={logTitle}
        description={logDescription}
        stageLabels={STAGE_LABELS}
        run={tailor}
      />
    </>
  )
}

export function JobResumeMaterials({
  materials,
  settings,
  jobUrl,
  onTailored,
  className,
}: Omit<Props, never>) {
  const [viewKey, setViewKey] = useState('base')
  const [logOpen, setLogOpen] = useState(false)
  const [customOpen, setCustomOpen] = useState(false)
  const tailor = useTailorMaterials(jobUrl, 'resume', () => onTailored?.())
  useTailorToasts(tailor, logOpen, 'Resume tailor')

  const baseResumePdf =
    settings?.has_resume_pdf && settings.resume_pdf_mtime != null
      ? `/api/settings/resume.pdf?t=${settings.resume_pdf_mtime}`
      : null
  const resumePdfUrl =
    jobUrl && materials?.resume_pdf
      ? `/api/jobs/${encodeURIComponent(jobUrl)}/materials/resume.pdf`
      : null

  const views = useMemo<MaterialViewOption[]>(() => {
    if (!settings) return []
    return [
      {
        key: 'base',
        label: 'Base resume',
        pdfUrl: baseResumePdf,
        markdown: settings.resume_markdown,
        pdfTitle: 'Base resume PDF',
        emptyPdf: 'No base resume PDF on file. Add one on the Profile page.',
        emptyMarkdown: 'No base resume markdown yet.',
      },
      {
        key: 'tailored',
        label: 'Tailored for this job',
        pdfUrl: resumePdfUrl,
        markdown: materials?.resume_preview ?? '',
        pdfTitle: 'Tailored resume PDF',
        emptyPdf: 'No tailored PDF yet. Run Auto Tailor.',
        emptyMarkdown: 'Not generated yet. Run Auto Tailor.',
      },
    ]
  }, [settings, baseResumePdf, resumePdfUrl, materials?.resume_preview])

  if (!settings && !materials) return null

  return (
    <div className={className}>
      {views.length ? (
        <MaterialSectionShell
          jobUrl={jobUrl}
          views={views}
          viewKey={viewKey}
          onViewKeyChange={setViewKey}
          tailoredDocx={materials?.resume_docx}
          tailoredPdf={materials?.resume_pdf}
          tailor={tailor}
          customOpen={customOpen}
          onCustomOpen={setCustomOpen}
          logOpen={logOpen}
          onLogOpen={setLogOpen}
          onCustomStart={(instructions) => {
            setCustomOpen(false)
            tailor.start(instructions)
            setLogOpen(true)
            setViewKey('tailored')
          }}
          tailorScope="resume"
          logTitle="Tailor Resume"
          logDescription="Keyword pass on your base resume, then DOCX export. Closing this window does not stop the run."
        />
      ) : (
        <p className="text-sm text-muted-foreground">Loading base resume…</p>
      )}
    </div>
  )
}

export function JobCoverMaterials({
  materials,
  settings,
  jobUrl,
  onTailored,
  className,
}: Omit<Props, never>) {
  const [viewKey, setViewKey] = useState('base')
  const [logOpen, setLogOpen] = useState(false)
  const [customOpen, setCustomOpen] = useState(false)
  const tailor = useTailorMaterials(jobUrl, 'cover', () => onTailored?.())
  useTailorToasts(tailor, logOpen, 'Cover letter tailor')

  const examples = settings?.cover_letter_examples ?? []
  const coverPdfUrl =
    jobUrl && materials?.cover_pdf
      ? `/api/jobs/${encodeURIComponent(jobUrl)}/materials/cover.pdf`
      : null

  const views = useMemo<MaterialViewOption[]>(() => {
    const sampleViews: MaterialViewOption[] = examples.map((example) => ({
      key: `sample:${example.id}`,
      label: `Sample · ${coverExampleName(example)}`,
      pdfUrl:
        example.kind !== 'txt'
          ? `/api/settings/cover-letters/${encodeURIComponent(example.id)}/pdf?t=${example.mtime}`
          : null,
      markdown: example.markdown,
      pdfTitle: `${example.filename} preview`,
      emptyPdf: 'No PDF on file.',
      emptyMarkdown: 'No markdown yet.',
    }))
    return [
      ...sampleViews,
      {
        key: 'tailored',
        label: 'Tailored for this job',
        pdfUrl: coverPdfUrl,
        markdown: materials?.cover_preview ?? '',
        pdfTitle: 'Tailored cover letter PDF',
        emptyPdf: 'No tailored PDF yet. Run Auto Tailor.',
        emptyMarkdown: 'Not generated yet. Run Auto Tailor.',
      },
    ]
  }, [examples, coverPdfUrl, materials?.cover_preview])

  useEffect(() => {
    if (!views.length) return
    if (views.some((v) => v.key === viewKey)) return
    setViewKey(views[0].key)
  }, [views, viewKey])

  if (!settings && !materials) return null

  return (
    <div className={className}>
      {views.length ? (
        <MaterialSectionShell
          jobUrl={jobUrl}
          views={views}
          viewKey={viewKey}
          onViewKeyChange={setViewKey}
          tailoredDocx={materials?.cover_docx}
          tailoredPdf={materials?.cover_pdf}
          tailor={tailor}
          customOpen={customOpen}
          onCustomOpen={setCustomOpen}
          logOpen={logOpen}
          onLogOpen={setLogOpen}
          onCustomStart={(instructions) => {
            setCustomOpen(false)
            tailor.start(instructions)
            setLogOpen(true)
            setViewKey('tailored')
          }}
          tailorScope="cover"
          logTitle="Tailor Cover Letter"
          logDescription="Tweak a cover letter from your profile samples for this job, then DOCX export. Closing this window does not stop the run."
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          No cover letter samples yet. Add PDFs on the Profile page.
        </p>
      )}
    </div>
  )
}

export function MaterialsPanel({ materials, settings, className, jobUrl, onTailored }: Props) {
  if (!jobUrl && !settings && !materials) return null
  return (
    <div className={cn('space-y-8', className)}>
      <JobResumeMaterials
        materials={materials}
        settings={settings}
        jobUrl={jobUrl}
        onTailored={onTailored}
      />
      <JobCoverMaterials
        materials={materials}
        settings={settings}
        jobUrl={jobUrl}
        onTailored={onTailored}
      />
    </div>
  )
}

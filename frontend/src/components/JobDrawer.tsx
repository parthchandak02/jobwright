import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { DrawerSection } from '@/components/DrawerSection'
import { DrawerStageNav } from '@/components/DrawerStageNav'
import { JobSummary } from '@/components/JobSummary'
import { ConnectionsPanel, type ConnectionContact } from '@/components/ConnectionsPanel'
import { MaterialsPanel, type MaterialsData } from '@/components/MaterialsPanel'
import { apiFetch, JobCard, laneTone, STAGE_LABELS } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'
import type { CSSProperties } from 'react'

type Props = {
  jobUrl: string | null
  onClose: () => void
  onChanged: () => void
  onRequestClose?: (url: string, title: string | null) => void
}

type Connections = {
  csv_contacts: ConnectionContact[]
  web_contacts: ConnectionContact[]
  manual_contacts: ConnectionContact[]
}

const AUTOSAVE_MS = 400

function JobDescriptionPane({ text }: { text: string }) {
  return (
    <div className="job-drawer-jd">
      <div className="job-drawer-jd-scroll">{text}</div>
      <div className="job-drawer-jd-hint" aria-hidden="true">
        <span>Scroll</span>
        <ChevronDown className="size-2.5 opacity-70" />
      </div>
    </div>
  )
}

export function JobDrawer({ jobUrl, onClose, onChanged, onRequestClose }: Props) {
  const open = !!jobUrl
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<MaterialsData | null>(null)
  const [connections, setConnections] = useState<Connections | null>(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadedUrl = useRef<string | null>(null)

  async function load(url: string) {
    const enc = encodeURIComponent(url)
    const j = await apiFetch<JobCard>(`/jobs/${enc}`)
    setJob(j)
    setNotes(j.notes || '')
    loadedUrl.current = url

    const [mRes, cRes] = await Promise.allSettled([
      apiFetch<MaterialsData>(`/jobs/${enc}/materials`),
      apiFetch<Connections>(`/jobs/${enc}/connections`),
    ])
    setMaterials(mRes.status === 'fulfilled' ? mRes.value : null)
    setConnections(cRes.status === 'fulfilled' ? cRes.value : null)
  }

  useEffect(() => {
    if (!jobUrl) {
      setJob(null)
      setMaterials(null)
      setConnections(null)
      loadedUrl.current = null
      return
    }
    void load(jobUrl).catch((e) => toast.error(errorMessage(e)))
  }, [jobUrl])

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    }
  }, [])

  function scheduleSave(nextNotes: string) {
    if (!jobUrl || loadedUrl.current !== jobUrl) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      void persistNotes(nextNotes)
    }, AUTOSAVE_MS)
  }

  async function persistNotes(nextNotes: string) {
    if (!jobUrl) return
    const originalNotes = job?.notes || ''
    if (nextNotes === originalNotes) return
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}`, {
        method: 'PATCH',
        body: JSON.stringify({ notes: nextNotes }),
      })
      onChanged()
      await load(jobUrl)
      toast.success('Saved')
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  async function moveStage(toStage: string) {
    if (!jobUrl) return
    if (toStage === 'closed') {
      if (onRequestClose) {
        onRequestClose(jobUrl, job?.title || null)
        return
      }
      return
    }
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}/move`, {
        method: 'POST',
        body: JSON.stringify({ to_stage: toStage }),
      })
      toast.success(`Moved to ${STAGE_LABELS[toStage] || toStage}`)
      onChanged()
      await load(jobUrl)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const hasMaterials = !!(
    materials?.resume_preview ||
    materials?.cover_preview ||
    materials?.resume_docx ||
    materials?.cover_docx ||
    materials?.resume_md ||
    materials?.cover_md
  )
  const showMaterialsSection = hasMaterials || job?.funnel_stage === 'prepare'

  const lane = job ? laneTone(job.funnel_stage) : undefined

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        showClose={false}
        className="flex h-dvh min-h-0 flex-col gap-0 overflow-hidden border-l-border/60 bg-background p-0 sm:w-3/5 sm:max-w-[60vw]"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>{job?.title || 'Job details'}</SheetTitle>
          <SheetDescription>{job?.company || job?.site || 'Job drawer'}</SheetDescription>
        </SheetHeader>

        <div className="job-drawer-scroll">
          <div className="min-w-0 px-4 pb-6 pt-4">
            {!job ? (
              <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading job…
              </div>
            ) : (
              <>
                <DrawerSection first>
                  <div
                    style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
                    className={cn('job-drawer-summary job-card-pad relative rounded-xl', lane && 'lane-card')}
                  >
                    <JobSummary
                      job={job}
                      onScoreSaved={async () => {
                        onChanged()
                        if (jobUrl) await load(jobUrl).catch((e) => toast.error(errorMessage(e)))
                      }}
                    />
                  </div>
                </DrawerSection>

                <DrawerSection>
                  <DrawerStageNav
                    stage={job.funnel_stage}
                    disabled={busy}
                    onMove={(toStage) => void moveStage(toStage)}
                  />
                </DrawerSection>

                {job.full_description?.trim() ? (
                  <DrawerSection title="Job Description">
                    <JobDescriptionPane text={job.full_description.trim()} />
                  </DrawerSection>
                ) : null}

                {jobUrl ? (
                  <DrawerSection title="Connections">
                    <ConnectionsPanel
                      jobUrl={jobUrl}
                      connections={connections}
                      onChanged={() => {
                        void load(jobUrl).catch((e) => toast.error(errorMessage(e)))
                      }}
                    />
                  </DrawerSection>
                ) : null}

                {showMaterialsSection ? (
                  <DrawerSection title="Materials">
                    <MaterialsPanel
                      materials={materials}
                      jobUrl={jobUrl ?? undefined}
                      onTailored={() => {
                        onChanged()
                        if (jobUrl) void load(jobUrl).catch((e) => toast.error(errorMessage(e)))
                      }}
                    />
                  </DrawerSection>
                ) : null}

                <DrawerSection title="Notes">
                  <Textarea
                    id="notes"
                    value={notes}
                    rows={3}
                    placeholder="Notes…"
                    onChange={(e) => {
                      const v = e.target.value
                      setNotes(v)
                      scheduleSave(v)
                    }}
                    onBlur={() => void persistNotes(notes)}
                  />
                </DrawerSection>
              </>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

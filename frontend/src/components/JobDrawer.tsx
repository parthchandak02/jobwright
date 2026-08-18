import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { DrawerMetaLine } from '@/components/DrawerMetaLine'
import { DrawerSection } from '@/components/DrawerSection'
import { FormField } from '@/components/FormField'
import { JobFitSummary } from '@/components/JobFitSummary'
import { ListingAccordion } from '@/components/ListingAccordion'
import { MaterialsPanel, type MaterialsData } from '@/components/MaterialsPanel'
import { ScoreBadge } from '@/components/ScoreBadge'
import { apiFetch, JobCard, OUTCOMES } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  jobUrl: string | null
  applyEnabled: boolean
  onClose: () => void
  onChanged: () => void
  /** Optional: open close dialog from parent instead of inline select confirm */
  onRequestClose?: (url: string, title: string | null) => void
}

type Connections = {
  csv_contacts: Array<Record<string, unknown>>
  web_contacts: Array<Record<string, unknown>>
}

const AUTOSAVE_MS = 400

export function JobDrawer({
  jobUrl,
  applyEnabled,
  onClose,
  onChanged,
  onRequestClose,
}: Props) {
  const open = !!jobUrl
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<MaterialsData | null>(null)
  const [connections, setConnections] = useState<Connections | null>(null)
  const [notes, setNotes] = useState('')
  const [followUp, setFollowUp] = useState('')
  const [busy, setBusy] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadedUrl = useRef<string | null>(null)

  async function load(url: string) {
    const enc = encodeURIComponent(url)
    const j = await apiFetch<JobCard>(`/jobs/${enc}`)
    setJob(j)
    setNotes(j.notes || '')
    setFollowUp(j.follow_up_at || '')
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
      setMoreOpen(false)
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

  function scheduleSave(nextNotes: string, nextFollowUp: string) {
    if (!jobUrl || loadedUrl.current !== jobUrl) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      void persistMeta(nextNotes, nextFollowUp)
    }, AUTOSAVE_MS)
  }

  async function persistMeta(nextNotes: string, nextFollowUp: string) {
    if (!jobUrl) return
    const originalNotes = job?.notes || ''
    const originalFollow = job?.follow_up_at || ''
    if (nextNotes === originalNotes && (nextFollowUp || '') === (originalFollow || '')) return
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}`, {
        method: 'PATCH',
        body: JSON.stringify({ notes: nextNotes, follow_up_at: nextFollowUp || null }),
      })
      onChanged()
      await load(jobUrl)
      toast.success('Saved')
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  async function toggleResponse() {
    if (!jobUrl || !job) return
    setBusy(true)
    try {
      const enc = encodeURIComponent(jobUrl)
      if (job.first_response_at) {
        await apiFetch(`/jobs/${enc}/response`, { method: 'DELETE' })
      } else {
        await apiFetch(`/jobs/${enc}/response`, { method: 'POST' })
      }
      onChanged()
      await load(jobUrl)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function setOutcome(outcome: string) {
    if (!jobUrl) return
    if (onRequestClose) {
      onRequestClose(jobUrl, job?.title || null)
      return
    }
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}/move`, {
        method: 'POST',
        body: JSON.stringify({ to_stage: 'closed', outcome }),
      })
      toast.success(`Closed as ${outcome}`)
      onChanged()
      await load(jobUrl)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function markApplied() {
    if (!jobUrl) return
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}/applied`, { method: 'POST' })
      toast.success('Marked applied')
      onChanged()
      await load(jobUrl)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function runApply(dryRun: boolean) {
    if (!jobUrl) return
    setBusy(true)
    try {
      await apiFetch('/apply', {
        method: 'POST',
        body: JSON.stringify({ url: jobUrl, dry_run: dryRun, confirm: !dryRun, limit: 1 }),
      })
      toast.success(dryRun ? 'Dry-run started' : 'Live apply started')
      onChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const workModelLabel = useMemo(() => {
    const w = job?.work_model?.trim()
    if (!w) return null
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
  }, [job?.work_model])

  const hasContacts =
    !!(connections?.csv_contacts?.length || connections?.web_contacts?.length)

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="gap-0 border-l-border/60 bg-background/90 p-0 backdrop-blur-xl sm:max-w-lg">
        <SheetHeader className="space-y-2 border-b border-border/60 px-4 py-4 text-left">
          {!job ? (
            <>
              <SheetTitle>Loading…</SheetTitle>
              <SheetDescription className="sr-only">Loading job details</SheetDescription>
            </>
          ) : (
            <>
              <div className="flex items-start gap-3 pr-8">
                <ScoreBadge score={job.fit_score} className="mt-0.5 h-7 min-w-7 rounded-lg text-sm" />
                <div className="min-w-0 flex-1">
                  <SheetTitle className="text-left text-base leading-snug">
                    {job.title || 'Untitled'}
                  </SheetTitle>
                  <SheetDescription className="mt-0.5 text-left text-sm">
                    {job.company || job.site || 'Unknown company'}
                  </SheetDescription>
                </div>
              </div>
              <DrawerMetaLine
                stage={job.funnel_stage}
                fitScore={job.fit_score}
                workModel={workModelLabel}
                outcome={job.outcome}
              />
            </>
          )}
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-7rem)]">
          <div className="px-4 pb-6">
            {!job ? (
              <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading job…
              </div>
            ) : (
              <>
                {/* 1 Orient — facts */}
                <DrawerSection first>
                  <DetailGrid>
                    <DetailRow label="Location" value={job.location} />
                    <DetailRow label="Salary" value={job.salary} />
                    <DetailRow label="Source" value={job.source} />
                    {workModelLabel ? <DetailRow label="Work model" value={workModelLabel} /> : null}
                  </DetailGrid>
                </DrawerSection>

                {/* 2 Understand */}
                {(job.keywords || job.reasoning || job.full_description) && (
                  <DrawerSection title="Fit">
                    <JobFitSummary keywords={job.keywords} reasoning={job.reasoning} />
                    <ListingAccordion description={job.full_description} />
                  </DrawerSection>
                )}

                {/* 3 Review materials */}
                {(materials?.resume_preview ||
                  materials?.cover_preview ||
                  materials?.resume_docx ||
                  materials?.cover_docx ||
                  materials?.resume_txt ||
                  materials?.cover_txt) && (
                  <DrawerSection title="Materials">
                    <MaterialsPanel materials={materials} />
                  </DrawerSection>
                )}

                {/* 4 Act */}
                <DrawerSection title="Actions">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" asChild>
                      <a href={job.application_url || job.url} target="_blank" rel="noreferrer">
                        <ExternalLink /> Open listing
                      </a>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void toggleResponse()}
                    >
                      {job.first_response_at ? 'Clear reply' : 'Got a reply'}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void markApplied()}
                    >
                      Mark applied
                    </Button>
                  </div>
                </DrawerSection>

                {/* 5 Track */}
                <DrawerSection title="Tracking">
                  <FormField label="Notes" htmlFor="notes">
                    <Textarea
                      id="notes"
                      value={notes}
                      rows={3}
                      onChange={(e) => {
                        const v = e.target.value
                        setNotes(v)
                        scheduleSave(v, followUp)
                      }}
                      onBlur={() => void persistMeta(notes, followUp)}
                    />
                  </FormField>
                  <FormField label="Follow-up" htmlFor="followup">
                    <Input
                      id="followup"
                      type="date"
                      value={followUp.slice(0, 10)}
                      onChange={(e) => {
                        const v = e.target.value
                        setFollowUp(v)
                        scheduleSave(notes, v)
                      }}
                      onBlur={() => void persistMeta(notes, followUp)}
                    />
                  </FormField>
                </DrawerSection>

                {/* 6 Admin / optional */}
                <DrawerSection>
                  <details
                    className="group"
                    open={moreOpen}
                    onToggle={(e) => setMoreOpen((e.target as HTMLDetailsElement).open)}
                  >
                    <summary className="cursor-pointer list-none text-sm font-medium text-foreground marker:content-none [&::-webkit-details-marker]:hidden">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="text-muted-foreground transition-transform group-open:rotate-90">
                          ▸
                        </span>
                        More
                      </span>
                    </summary>
                    <div className="mt-4 space-y-5">
                      <div className="space-y-2">
                        <p className="text-sm font-medium text-foreground">Connections</p>
                        {hasContacts ? (
                          <ul className="space-y-1 text-sm">
                            {(connections?.csv_contacts || []).slice(0, 5).map((c, i) => (
                              <li key={`c-${i}`}>
                                {[c.first_name, c.last_name].filter(Boolean).join(' ') ||
                                  String(c.name || 'Contact')}
                                {c.position ? (
                                  <span className="text-muted-foreground">
                                    {' '}
                                    · {String(c.position)}
                                  </span>
                                ) : null}
                              </li>
                            ))}
                            {(connections?.web_contacts || []).slice(0, 3).map((c, i) => (
                              <li key={`w-${i}`}>
                                {String(c.name || 'Web')}
                                {c.role ? (
                                  <span className="text-muted-foreground"> · {String(c.role)}</span>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">No contacts yet</p>
                        )}
                      </div>

                      <div className="space-y-2">
                        <p className="text-sm font-medium text-foreground">Close with outcome</p>
                        {onRequestClose ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busy || !jobUrl}
                            onClick={() => jobUrl && onRequestClose(jobUrl, job.title)}
                          >
                            Close job…
                          </Button>
                        ) : (
                          <Select disabled={busy} onValueChange={(v) => void setOutcome(v)}>
                            <SelectTrigger>
                              <SelectValue placeholder="Choose outcome…" />
                            </SelectTrigger>
                            <SelectContent>
                              {OUTCOMES.map((o) => (
                                <SelectItem key={o} value={o} className="capitalize">
                                  {o}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                      </div>

                      <div className="space-y-2">
                        <p className="text-sm font-medium text-foreground">Gated apply</p>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busy}
                            onClick={() => void runApply(true)}
                          >
                            Dry-run apply
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={busy || !applyEnabled}
                            title={applyEnabled ? 'Live apply' : 'apply_enabled is false'}
                            onClick={() => {
                              if (window.confirm('Submit live application for this job?')) {
                                void runApply(false)
                              }
                            }}
                          >
                            Live apply
                          </Button>
                        </div>
                      </div>
                    </div>
                  </details>
                </DrawerSection>
              </>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

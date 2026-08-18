import { useEffect, useState } from 'react'
import { DollarSign, ExternalLink, Loader2, MapPin, Radio } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/FormField'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { MetaField } from '@/components/MetaField'
import { SectionLabel } from '@/components/SectionLabel'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import { apiFetch, JobCard, OUTCOMES, STAGE_LABELS } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Props = {
  jobUrl: string | null
  applyEnabled: boolean
  onClose: () => void
  onChanged: () => void
}

type Materials = {
  resume_txt: string | null
  resume_docx: string | null
  cover_txt: string | null
  cover_docx: string | null
}

type Connections = {
  csv_contacts: Array<Record<string, unknown>>
  web_contacts: Array<Record<string, unknown>>
}

export function JobDrawer({ jobUrl, applyEnabled, onClose, onChanged }: Props) {
  const open = !!jobUrl
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<Materials | null>(null)
  const [connections, setConnections] = useState<Connections | null>(null)
  const [notes, setNotes] = useState('')
  const [followUp, setFollowUp] = useState('')
  const [busy, setBusy] = useState(false)

  async function load(url: string) {
    const enc = encodeURIComponent(url)
    const j = await apiFetch<JobCard>(`/jobs/${enc}`)
    setJob(j)
    setNotes(j.notes || '')
    setFollowUp(j.follow_up_at || '')

    const [mRes, cRes] = await Promise.allSettled([
      apiFetch<Materials>(`/jobs/${enc}/materials`),
      apiFetch<Connections>(`/jobs/${enc}/connections`),
    ])
    setMaterials(mRes.status === 'fulfilled' ? mRes.value : null)
    setConnections(cRes.status === 'fulfilled' ? cRes.value : null)
    if (mRes.status === 'rejected' || cRes.status === 'rejected') {
      toast.error('Some job details could not be loaded')
    }
  }

  useEffect(() => {
    if (!jobUrl) {
      setJob(null)
      return
    }
    void load(jobUrl).catch((e) => toast.error(errorMessage(e)))
  }, [jobUrl])

  async function saveMeta() {
    if (!jobUrl) return
    setBusy(true)
    try {
      await apiFetch(`/jobs/${encodeURIComponent(jobUrl)}`, {
        method: 'PATCH',
        body: JSON.stringify({ notes, follow_up_at: followUp || null }),
      })
      toast.success('Saved')
      onChanged()
      await load(jobUrl)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
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

  function download(path: string | null) {
    if (!path) return
    window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="gap-0 border-l-border/60 bg-background/80 p-0 backdrop-blur-xl sm:max-w-lg">
        <SheetHeader className="border-b">
          <SheetTitle className="pr-6 text-left">{job?.title || 'Loading…'}</SheetTitle>
          <SheetDescription className="text-left">
            {job?.company}
            {job ? ` · ${STAGE_LABELS[job.funnel_stage] || job.funnel_stage}` : ''}
            {job?.fit_score != null ? ` · score ${job.fit_score}` : ''}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-8rem)]">
          <div className="space-y-5 p-4">
            {!job ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading job…
              </div>
            ) : (
              <>
                <JobMetaBadges job={job} />

                <section className="space-y-2">
                  <SectionLabel>Details</SectionLabel>
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Work model</span>
                    <WorkModelBadge workModel={job.work_model} />
                  </div>
                  <div className="space-y-1.5">
                    <MetaField icon={MapPin} label="Location" value={job.location} className="text-xs" />
                    <MetaField icon={DollarSign} label="Salary" value={job.salary} className="text-xs" />
                    <MetaField icon={Radio} label="Source" value={job.source} className="text-xs" />
                  </div>
                </section>

                <div className="flex flex-wrap gap-2">
                  <Button size="sm" asChild>
                    <a href={job.application_url || job.url} target="_blank" rel="noreferrer">
                      <ExternalLink /> Open listing
                    </a>
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => void toggleResponse()}>
                    {job.first_response_at ? 'Clear reply' : 'Got a reply'}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => void markApplied()}>
                    Mark applied
                  </Button>
                </div>

                <section className="space-y-2">
                  <FormField label="Notes" htmlFor="notes">
                    <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
                  </FormField>
                  <FormField label="Follow-up" htmlFor="followup">
                    <Input
                      id="followup"
                      type="date"
                      value={followUp.slice(0, 10)}
                      onChange={(e) => setFollowUp(e.target.value)}
                    />
                  </FormField>
                  <Button size="sm" disabled={busy} onClick={() => void saveMeta()}>
                    Save
                  </Button>
                </section>

                <Separator />

                <section className="space-y-2">
                  <SectionLabel>Materials</SectionLabel>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={!materials?.resume_docx} onClick={() => download(materials?.resume_docx || null)}>
                      Resume DOCX
                    </Button>
                    <Button size="sm" variant="outline" disabled={!materials?.resume_txt} onClick={() => download(materials?.resume_txt || null)}>
                      Resume TXT
                    </Button>
                    <Button size="sm" variant="outline" disabled={!materials?.cover_docx} onClick={() => download(materials?.cover_docx || null)}>
                      Cover DOCX
                    </Button>
                    <Button size="sm" variant="outline" disabled={!materials?.cover_txt} onClick={() => download(materials?.cover_txt || null)}>
                      Cover TXT
                    </Button>
                  </div>
                </section>

                <section className="space-y-2">
                  <SectionLabel>Connections</SectionLabel>
                  <ul className="space-y-1 text-sm">
                    {(connections?.csv_contacts || []).slice(0, 5).map((c, i) => (
                      <li key={`c-${i}`} className="text-foreground">
                        {[c.first_name, c.last_name].filter(Boolean).join(' ') || String(c.name || 'Contact')}
                        {c.position ? (
                          <span className="text-muted-foreground"> · {String(c.position)}</span>
                        ) : null}
                      </li>
                    ))}
                    {(connections?.web_contacts || []).slice(0, 3).map((c, i) => (
                      <li key={`w-${i}`}>
                        {String(c.name || 'Web')}
                        {c.role ? <span className="text-muted-foreground"> · {String(c.role)}</span> : null}
                      </li>
                    ))}
                    {!connections?.csv_contacts?.length && !connections?.web_contacts?.length && (
                      <li className="text-muted-foreground">No contacts yet</li>
                    )}
                  </ul>
                </section>

                <section className="space-y-2">
                  <SectionLabel>Close with outcome</SectionLabel>
                  <div className="flex flex-wrap gap-2">
                    {OUTCOMES.map((o) => (
                      <Badge
                        key={o}
                        variant="outline"
                        className="cursor-pointer capitalize hover:bg-accent"
                        onClick={() => !busy && void setOutcome(o)}
                      >
                        {o}
                      </Badge>
                    ))}
                  </div>
                </section>

                <section className="space-y-2">
                  <SectionLabel>Gated apply</SectionLabel>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" disabled={busy} onClick={() => void runApply(true)}>
                      Dry-run apply
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy || !applyEnabled}
                      title={applyEnabled ? 'Live apply' : 'apply_enabled is false'}
                      onClick={() => {
                        if (window.confirm('Submit live application for this job?')) void runApply(false)
                      }}
                    >
                      Live apply
                    </Button>
                  </div>
                </section>

                {job.reasoning && <p className="text-sm italic text-muted-foreground">{job.reasoning}</p>}
                {job.full_description && (
                  <details className="rounded-lg border bg-muted/30 p-3 text-sm">
                    <summary className="cursor-pointer font-medium">Full description</summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap font-sans text-xs text-muted-foreground">
                      {job.full_description}
                    </pre>
                  </details>
                )}
              </>
            )}
          </div>
        </ScrollArea>
        <SheetFooter className="border-t">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  ChevronDown,
  DollarSign,
  ExternalLink,
  History,
  Loader2,
  MapPin,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { ConnectionsPanel, type ConnectionContact } from '@/components/ConnectionsPanel'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { DrawerSection } from '@/components/DrawerSection'
import { JobMetaBadges } from '@/components/JobMetaBadges'
import { listingHref } from '@/components/JobSummary'
import { LinkedInLogo } from '@/components/LinkedInLogo'
import { MatchExplanation } from '@/components/MatchExplanation'
import {
  JobCoverMaterials,
  JobResumeMaterials,
  type MaterialsData,
} from '@/components/MaterialsPanel'
import { RateJob } from '@/components/RateJob'
import { ScoreBadge } from '@/components/ScoreBadge'
import { SponsorshipBadge } from '@/components/SponsorshipBadge'
import { StagePicker } from '@/components/StagePicker'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { WorkModelBadge } from '@/components/WorkModelBadge'
import {
  apiFetch,
  getJobHistory,
  getJobLabels,
  jobPath,
  laneTone,
  listRuns,
  moveJob,
  STAGE_LABELS,
  startJobTailor,
  type JobCard,
  type JobLabels,
  type SettingsData,
  type StageHistoryEntry,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  /** job_id of the open job (null = closed). */
  jobKey: string | null
  onClose: () => void
  onChanged: () => void
}

type Connections = {
  csv_contacts: ConnectionContact[]
  web_contacts: ConnectionContact[]
  manual_contacts: ConnectionContact[]
}

const NOTES_SAVE_MS = 800
const PREPARE_POLL_MS = 5000

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

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Poll for (and start) the full resume + cover run for one job. */
function usePrepareMaterials(jobKey: string | null, onDone: () => void) {
  const [runId, setRunId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    setRunId(null)
    if (!jobKey) return
    let cancelled = false
    listRuns()
      .then((runs) => {
        const live = runs.find((r) => r.running && r.job_id === jobKey && r.kind === 'tailor')
        if (!cancelled && live) setRunId(live.run_id)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [jobKey])

  useEffect(() => {
    if (!runId) return
    const id = window.setInterval(() => {
      if (document.hidden) return
      void listRuns()
        .then((runs) => {
          const r = runs.find((x) => x.run_id === runId)
          if (!r || r.running) return
          setRunId(null)
          if (r.returncode != null && r.returncode !== 0) {
            toast.error('Preparing materials failed. Open Resume → Auto Tailor to see the log.')
          } else {
            toast.success('Resume and cover letter are ready.')
          }
          onDoneRef.current()
        })
        .catch(() => undefined)
    }, PREPARE_POLL_MS)
    return () => window.clearInterval(id)
  }, [runId])

  const start = useCallback(async () => {
    if (!jobKey) return
    setStarting(true)
    try {
      const handle = await startJobTailor(jobKey)
      setRunId(handle.run_id)
      toast.success('Preparing your resume and cover letter. This takes a few minutes.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setStarting(false)
    }
  }, [jobKey])

  return { running: Boolean(runId), starting, start }
}

export function JobDrawer({ jobKey, onClose, onChanged }: Props) {
  const open = !!jobKey
  const [job, setJob] = useState<JobCard | null>(null)
  const [materials, setMaterials] = useState<MaterialsData | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [connections, setConnections] = useState<Connections | null>(null)
  const [notes, setNotes] = useState('')
  const [notesState, setNotesState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [busy, setBusy] = useState(false)
  const [dismissOpen, setDismissOpen] = useState(false)
  const [history, setHistory] = useState<{ stages: StageHistoryEntry[]; labels: JobLabels } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedNotes = useRef('')
  const loadSeq = useRef(0)

  const load = useCallback(async (key: string, opts?: { keepNotes?: boolean }) => {
    const seq = ++loadSeq.current
    const j = await apiFetch<JobCard>(jobPath(key))
    if (seq !== loadSeq.current) return
    setJob(j)
    if (!opts?.keepNotes) {
      setNotes(j.notes || '')
      savedNotes.current = j.notes || ''
    }
    const [mRes, cRes, sRes] = await Promise.allSettled([
      apiFetch<MaterialsData>(`${jobPath(key)}/materials`),
      apiFetch<Connections>(`${jobPath(key)}/connections`),
      apiFetch<SettingsData>('/settings'),
    ])
    if (seq !== loadSeq.current) return
    setMaterials(mRes.status === 'fulfilled' ? mRes.value : null)
    setConnections(cRes.status === 'fulfilled' ? cRes.value : null)
    setSettings(sRes.status === 'fulfilled' ? sRes.value : null)
  }, [])

  const reload = useCallback(() => {
    if (jobKey) void load(jobKey, { keepNotes: true }).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  const prepare = usePrepareMaterials(jobKey, () => {
    onChanged()
    reload()
  })

  useEffect(() => {
    setHistory(null)
    setHistoryOpen(false)
    setNotesState('idle')
    if (!jobKey) {
      loadSeq.current++
      setJob(null)
      setMaterials(null)
      setSettings(null)
      setConnections(null)
      return
    }
    setJob(null)
    void load(jobKey).catch((e) => toast.error(errorMessage(e)))
  }, [jobKey, load])

  useEffect(
    () => () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    },
    [],
  )

  async function persistNotes(next: string) {
    if (!job || next === savedNotes.current) return
    setNotesState('saving')
    try {
      await apiFetch(jobPath(job), { method: 'PATCH', body: JSON.stringify({ notes: next }) })
      savedNotes.current = next
      setNotesState('saved')
      onChanged()
    } catch (e) {
      setNotesState('idle')
      toast.error(errorMessage(e))
    }
  }

  function onNotesChange(next: string) {
    setNotes(next)
    setNotesState('idle')
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => void persistNotes(next), NOTES_SAVE_MS)
  }

  async function doMove(toStage: string, opts?: { outcome?: string; reasons?: string[]; close_reason?: string }) {
    if (!job) return
    const fromStage = job.funnel_stage
    setBusy(true)
    try {
      const res = await moveJob(job, toStage, opts)
      setJob(res.job)
      onChanged()
      toast.success(`Moved to ${STAGE_LABELS[toStage] || toStage}`, {
        action:
          fromStage !== toStage
            ? {
                label: 'Undo',
                onClick: () => {
                  void moveJob(res.job, fromStage)
                    .then((r) => {
                      setJob(r.job)
                      onChanged()
                    })
                    .catch((e) => toast.error(errorMessage(e)))
                },
              }
            : undefined,
      })
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  function requestMove(toStage: string) {
    if (toStage === 'closed') setDismissOpen(true)
    else void doMove(toStage)
  }

  function onDismiss(result: DismissResult) {
    setDismissOpen(false)
    void doMove('closed', { outcome: result.outcome, reasons: result.reasons, close_reason: result.note || undefined })
  }

  async function toggleHistory() {
    const next = !historyOpen
    setHistoryOpen(next)
    if (next && job && !history) {
      try {
        const [h, l] = await Promise.all([getJobHistory(job), getJobLabels(job)])
        setHistory({ stages: h.history, labels: l })
      } catch (e) {
        toast.error(errorMessage(e))
      }
    }
  }

  const href = job ? listingHref(job) : null
  const lane = job ? laneTone(job.funnel_stage) : undefined
  const hasMaterials = Boolean(job?.has_resume || job?.has_cover || materials?.resume_md || materials?.cover_md)
  const beforeApplying = job ? job.funnel_stage === 'backlog' || job.funnel_stage === 'prepare' : false
  const showMaterials = !!job && (hasMaterials || job.funnel_stage !== 'backlog' || prepare.running)

  const historyItems = history
    ? [
        ...history.stages.map((h) => ({
          at: h.at,
          text: `${h.actor === 'human' ? 'You' : 'jobwright'} moved it ${
            h.from_stage ? `from ${STAGE_LABELS[h.from_stage] || h.from_stage} ` : ''
          }to ${STAGE_LABELS[h.to_stage] || h.to_stage}${h.note ? ` (${h.note})` : ''}`,
        })),
        ...history.labels.labels.map((l) => ({
          at: l.created_at,
          text:
            l.verdict === 'cleared'
              ? 'You removed your rating'
              : `You rated it ${l.label_score}/10${
                  l.reasons?.length ? `: ${l.reasons.join(', ')}` : l.rationale ? `: ${l.rationale}` : ''
                }`,
        })),
        ...history.labels.machine_scores.map((m) => ({
          at: m.created_at,
          text: `Scored ${m.score}/10${m.run_kind === 'rescore' ? ' (rescore)' : ''}`,
        })),
      ].sort((a, b) => (a.at < b.at ? 1 : -1))
    : []

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        showClose={false}
        className="flex h-dvh min-h-0 flex-col gap-0 overflow-hidden border-l-border/60 bg-background p-0 sm:w-3/5 sm:max-w-[60vw]"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>{job?.title || 'Job details'}</SheetTitle>
          <SheetDescription>{job?.company || 'Job details'}</SheetDescription>
        </SheetHeader>

        <header
          className="shrink-0 space-y-2 border-b border-border/60 bg-background px-3 pt-2 pb-2.5"
          style={lane ? ({ '--lane': lane } as CSSProperties) : undefined}
        >
          <div className="flex items-start gap-2">
            <Button type="button" size="icon-sm" variant="ghost" onClick={onClose} aria-label="Back to board">
              <ArrowLeft />
            </Button>
            <div className="min-w-0 flex-1 pt-0.5">
              <h2 className="truncate text-base leading-tight font-semibold">{job?.title || 'Loading…'}</h2>
              {job ? (
                <p className="flex items-center gap-1 truncate text-sm text-muted-foreground">
                  <Building2 className="size-3.5 shrink-0" /> {job.company || 'Unknown company'}
                </p>
              ) : null}
            </div>
            {job ? (
              <ScoreBadge
                score={job.fit_score}
                userModified={job.score_user_modified}
                className="h-8 min-w-8 rounded-lg text-sm"
              />
            ) : null}
          </div>
          {job ? (
            <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-0.5 md:mx-0 md:flex-wrap md:overflow-visible md:px-0 md:pl-10">
              {href ? (
                <Button asChild size="sm" variant={hasMaterials || !beforeApplying ? 'default' : 'outline'}>
                  <a href={href} target="_blank" rel="noreferrer">
                    <ExternalLink /> Open posting
                  </a>
                </Button>
              ) : null}
              {beforeApplying && !hasMaterials ? (
                <Button
                  size="sm"
                  variant="ai"
                  disabled={prepare.starting || prepare.running}
                  onClick={() => void prepare.start()}
                >
                  {prepare.running || prepare.starting ? <Loader2 className="animate-spin" /> : <Sparkles />}
                  {prepare.running ? 'Preparing materials…' : 'Prepare resume + letter'}
                </Button>
              ) : null}
              {beforeApplying ? (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void doMove('applied')}>
                  <CheckCircle2 /> I applied
                </Button>
              ) : null}
              {job.funnel_stage !== 'closed' ? (
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setDismissOpen(true)}>
                  <XCircle /> {beforeApplying ? 'Not for me' : 'Close'}
                </Button>
              ) : null}
            </div>
          ) : null}
        </header>

        <div className="job-drawer-scroll">
          <div className="min-w-0 px-4 pb-8 pt-3">
            {!job ? (
              <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading job…
              </div>
            ) : (
              <>
                <DrawerSection first>
                  <div className="space-y-2.5">
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <MapPin className="size-3.5" /> {job.location || 'Location not stated'}
                      </span>
                      <span className="flex items-center gap-1">
                        <DollarSign className="size-3.5" /> {job.salary || 'Pay not stated'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <WorkModelBadge workModel={job.work_model} />
                      <SponsorshipBadge status={job.sponsorship_status} />
                      <JobMetaBadges job={job} />
                    </div>
                    <StagePicker stage={job.funnel_stage} disabled={busy} onMove={requestMove} />
                    {job.funnel_stage === 'closed' && (job.outcome || job.close_reason) ? (
                      <p className="text-xs text-muted-foreground">
                        Closed{job.outcome ? `: ${job.outcome.replace('_', ' ')}` : ''}
                        {job.close_reason ? ` · ${job.close_reason}` : ''}
                      </p>
                    ) : null}
                  </div>
                </DrawerSection>

                <DrawerSection title="Why this match">
                  <div className="space-y-4">
                    <MatchExplanation job={job} />
                    <RateJob
                      job={job}
                      onRated={(updated) => {
                        setJob({ ...job, ...updated })
                        onChanged()
                      }}
                    />
                  </div>
                </DrawerSection>

                {job.full_description?.trim() ? (
                  <DrawerSection title="Job description">
                    <JobDescriptionPane text={job.full_description.trim()} />
                  </DrawerSection>
                ) : null}

                {showMaterials ? (
                  <>
                    <DrawerSection title="Resume">
                      <JobResumeMaterials
                        materials={materials}
                        settings={settings}
                        jobKey={job.job_id}
                        onTailored={() => {
                          onChanged()
                          reload()
                        }}
                      />
                    </DrawerSection>
                    <DrawerSection title="Cover letter">
                      <JobCoverMaterials
                        materials={materials}
                        settings={settings}
                        jobKey={job.job_id}
                        onTailored={() => {
                          onChanged()
                          reload()
                        }}
                      />
                    </DrawerSection>
                  </>
                ) : null}

                <DrawerSection
                  className="connections-section"
                  title={
                    <span className="inline-flex items-center gap-2">
                      <LinkedInLogo className="size-4 text-[var(--linkedin)]" />
                      Who you know there
                    </span>
                  }
                >
                  <ConnectionsPanel jobKey={job.job_id} connections={connections} onChanged={reload} />
                </DrawerSection>

                <DrawerSection
                  title={
                    <span className="flex w-full items-center justify-between gap-2">
                      Notes
                      <span className="text-xs font-normal text-muted-foreground" aria-live="polite">
                        {notesState === 'saving' ? 'Saving…' : notesState === 'saved' ? 'Saved' : ''}
                      </span>
                    </span>
                  }
                >
                  <Textarea
                    id="notes"
                    value={notes}
                    rows={3}
                    placeholder="Notes for yourself…"
                    onChange={(e) => onNotesChange(e.target.value)}
                    onBlur={() => {
                      if (saveTimer.current) clearTimeout(saveTimer.current)
                      void persistNotes(notes)
                    }}
                  />
                </DrawerSection>

                <DrawerSection>
                  <button
                    type="button"
                    onClick={() => void toggleHistory()}
                    className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                    aria-expanded={historyOpen}
                  >
                    <History className="size-3.5" /> History
                    <ChevronDown className={cn('size-3.5 transition-transform', historyOpen && 'rotate-180')} />
                  </button>
                  {historyOpen ? (
                    history ? (
                      <ul className="mt-3 space-y-1.5 text-xs text-muted-foreground">
                        {historyItems.map((e, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="shrink-0 tabular-nums">{fmtWhen(e.at)}</span>
                            <span className="text-foreground/80">{e.text}</span>
                          </li>
                        ))}
                        {!historyItems.length ? <li>No history yet.</li> : null}
                      </ul>
                    ) : (
                      <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                        <Loader2 className="size-3.5 animate-spin" /> Loading…
                      </p>
                    )
                  ) : null}
                </DrawerSection>
              </>
            )}
          </div>
        </div>
      </SheetContent>
      <DismissDialog
        open={dismissOpen}
        jobTitle={job?.title}
        fromStage={job?.funnel_stage}
        onCancel={() => setDismissOpen(false)}
        onConfirm={onDismiss}
      />
    </Sheet>
  )
}

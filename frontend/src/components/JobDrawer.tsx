import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeft,
  BellRing,
  CheckCircle2,
  ChevronDown,
  Copy,
  ExternalLink,
  History,
  Loader2,
  MoreHorizontal,
  Sparkles,
  XCircle,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ConnectionsPanel, type ConnectionContact } from '@/components/ConnectionsPanel'
import { DetailGrid, DetailRow } from '@/components/DetailRow'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { DrawerSection } from '@/components/DrawerSection'
import { followUpLabel } from '@/components/JobMetaBadges'
import { listingHref } from '@/components/JobSummary'
import { LinkedInLogo } from '@/components/LinkedInLogo'
import { MatchExplanation } from '@/components/MatchExplanation'
import {
  JobCoverMaterials,
  JobResumeMaterials,
  type MaterialsData,
} from '@/components/MaterialsPanel'
import { RateJob } from '@/components/RateJob'
import { SaveStatus, type SaveState } from '@/components/SaveStatus'
import { StagePicker } from '@/components/StagePicker'
import { workModelLabel } from '@/components/WorkModelBadge'
import { Button, type ButtonProps } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import {
  apiFetch,
  followUpJob,
  getJobHistory,
  getJobLabels,
  jobPath,
  listRuns,
  moveJob,
  OUTCOME_LABELS,
  STAGE_LABELS,
  startJobTailor,
  type JobCard,
  type JobLabels,
  type SettingsData,
  type StageHistoryEntry,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  jobKey: string | null
  onClose: () => void
  onChanged: () => void
}

type Connections = {
  csv_contacts: ConnectionContact[]
  web_contacts: ConnectionContact[]
  manual_contacts: ConnectionContact[]
}

type DrawerAction = {
  key: string
  label: string
  short: string
  icon: LucideIcon
  variant: NonNullable<ButtonProps['variant']>
  href?: string
  onClick?: () => void
  disabled?: boolean
  busy?: boolean
}

const NOTES_SAVE_MS = 800
const PREPARE_POLL_MS = 5000

const SPONSORSHIP: Record<string, string> = {
  required: 'Employer would need to sponsor',
  not_required: 'US citizens or green card holders only',
  not_found: 'Not mentioned',
}

function JobDescriptionPane({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)

  useLayoutEffect(() => {
    setExpanded(false)
  }, [text])

  useLayoutEffect(() => {
    const el = ref.current
    if (el && !expanded) setOverflows(el.scrollHeight > el.clientHeight + 8)
  }, [text, expanded])

  return (
    <div>
      <div
        ref={ref}
        data-collapsed={!expanded ? 'true' : 'false'}
        className="job-drawer-jd materials-preview text-body text-foreground"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
      {overflows || expanded ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="mt-1 -ml-3"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          <ChevronDown className={cn('transition-transform duration-(--dur-2)', expanded && 'rotate-180')} />
          {expanded ? 'Show less' : 'Show full description'}
        </Button>
      ) : null}
    </div>
  )
}

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function fmtDay(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

function ActionButton({ action, className, compact }: { action: DrawerAction; className?: string; compact?: boolean }) {
  const Icon = action.busy ? Loader2 : action.icon
  const content = (
    <>
      <Icon className={cn(action.busy && 'animate-spin')} aria-hidden />
      <span className={cn(compact && 'truncate')}>{compact ? action.short : action.label}</span>
    </>
  )
  const cls = cn(compact && 'h-14 min-w-0 flex-1 flex-col gap-1 px-1 text-micro has-[>svg]:px-1', className)
  if (action.href) {
    return (
      <Button asChild variant={action.variant} className={cls}>
        <a href={action.href} target="_blank" rel="noreferrer" aria-label={compact ? action.label : undefined}>
          {content}
        </a>
      </Button>
    )
  }
  return (
    <Button
      type="button"
      variant={action.variant}
      className={cls}
      disabled={action.disabled}
      onClick={action.onClick}
      aria-label={compact ? action.label : undefined}
    >
      {content}
    </Button>
  )
}

function PhoneActionBar({ actions }: { actions: DrawerAction[] }) {
  if (!actions.length) return null
  const lead = actions.find((a) => a.variant === 'ai' || a.variant === 'primary')
  const shown = actions.length > 4 ? actions.slice(0, 3) : actions
  const more = actions.length > 4 ? actions.slice(3) : []
  return (
    <div className="flex shrink-0 gap-1 border-t border-border bg-background px-2 pt-1.5 pb-[calc(0.375rem+var(--safe-bottom))] shadow-e1 md:hidden">
      {shown.map((a) => (
        <ActionButton key={a.key} action={a === lead ? a : { ...a, variant: 'ghost' }} compact />
      ))}
      {more.length ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" className="h-14 flex-1 flex-col gap-1 px-1 text-micro">
              <MoreHorizontal aria-hidden /> More
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top">
            {more.map((a) => (
              <DropdownMenuItem key={a.key} disabled={a.disabled} onSelect={() => a.onClick?.()}>
                <a.icon /> {a.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  )
}

function Callout({ icon: Icon, children, actions, tone }: { icon: LucideIcon; children: ReactNode; actions?: ReactNode; tone?: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Icon className="mt-[0.2rem] size-4 shrink-0" style={tone ? { color: `var(${tone})` } : undefined} aria-hidden />
        <div className="min-w-0 text-body text-foreground">{children}</div>
      </div>
      {actions ? <div className="flex flex-wrap gap-2 max-sm:pl-7">{actions}</div> : null}
    </div>
  )
}

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
  const [notesState, setNotesState] = useState<SaveState>('idle')
  const [notesSavedAt, setNotesSavedAt] = useState<number | null>(null)
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
      setNotesSavedAt(Date.now())
      onChanged()
    } catch (e) {
      setNotesState('error')
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

  async function doFollowUp(action: 'followed_up' | 'no_response') {
    if (!job) return
    setBusy(true)
    try {
      setJob(await followUpJob(job, action))
      onChanged()
      toast.success(action === 'followed_up' ? "Nice. We'll remind you again later." : 'Moved to Closed (no response).')
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
  const hasMaterials = Boolean(job?.has_resume || job?.has_cover || materials?.resume_md || materials?.cover_md)
  const beforeApplying = job ? job.funnel_stage === 'backlog' || job.funnel_stage === 'prepare' : false
  const closed = job?.funnel_stage === 'closed'
  const showMaterials = !!job && (hasMaterials || job.funnel_stage !== 'backlog' || prepare.running)

  const actions: DrawerAction[] = []
  if (job) {
    if (beforeApplying && !hasMaterials) {
      actions.push({
        key: 'prepare',
        label: prepare.running ? 'Preparing resume + letter…' : 'Prepare resume + letter',
        short: prepare.running ? 'Preparing…' : 'Prepare',
        icon: Sparkles,
        variant: 'ai',
        busy: prepare.running || prepare.starting,
        disabled: prepare.starting || prepare.running,
        onClick: () => void prepare.start(),
      })
    }
    if (href) {
      actions.push({
        key: 'open',
        label: 'Open posting',
        short: 'Posting',
        icon: ExternalLink,
        variant: beforeApplying && hasMaterials ? 'primary' : 'secondary',
        href,
      })
    }
    if (beforeApplying) {
      actions.push({
        key: 'applied',
        label: 'I applied',
        short: 'I applied',
        icon: CheckCircle2,
        variant: 'secondary',
        disabled: busy,
        onClick: () => void doMove('applied'),
      })
    }
    if (!closed) {
      actions.push({
        key: 'dismiss',
        label: beforeApplying ? 'Not for me' : 'Close job',
        short: beforeApplying ? 'Not for me' : 'Close',
        icon: XCircle,
        variant: 'ghost',
        disabled: busy,
        onClick: () => setDismissOpen(true),
      })
    }
  }

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

  const place = job ? [job.company || 'Unknown company', job.location].filter(Boolean).join(' · ') : ''
  const closedText =
    job && closed && !job.duplicate_of && (job.outcome || job.close_reason)
      ? [
          job.outcome ? OUTCOME_LABELS[job.outcome] || job.outcome.replace('_', ' ') : null,
          job.close_reason ? (job.close_reason === 'no_response' ? 'No response' : job.close_reason) : null,
        ]
          .filter(Boolean)
          .join(' · ')
      : null

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        showClose={false}
        className="flex h-dvh min-h-0 flex-col gap-0 overflow-hidden bg-background p-0 sm:w-3/5 sm:max-w-[52rem] md:min-w-[36rem]"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>{job?.title || 'Job details'}</SheetTitle>
          <SheetDescription>{job?.company || 'Job details'}</SheetDescription>
        </SheetHeader>

        <header className="flex shrink-0 items-start gap-2 border-b border-border bg-background px-2 py-2 md:px-3 md:py-3">
          <Button type="button" size="icon" variant="ghost" onClick={onClose} aria-label="Back to board" className="shrink-0">
            <ArrowLeft />
          </Button>
          <div className="min-w-0 flex-1 py-1 md:py-0.5">
            <h2 className="line-clamp-2 text-heading text-foreground">{job?.title || 'Loading…'}</h2>
            {job ? <p className="mt-0.5 truncate text-caption text-muted-foreground">{place}</p> : null}
          </div>
        </header>

        <div className="job-drawer-scroll">
          <div className="mx-auto min-w-0 max-w-[46rem] px-4 pb-10 md:px-6">
            {!job ? (
              <div className="flex items-center gap-2 py-8 text-body text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading job…
              </div>
            ) : (
              <>
                <DrawerSection first className="flex flex-col gap-4">
                  <div className="surface space-y-4 rounded-lg p-4 md:p-5">
                    <MatchExplanation job={job} />
                    {job.funnel_stage === 'closed' && job.duplicate_of ? (
                      <p className="flex items-center gap-2 text-body text-muted-foreground">
                        <Copy className="size-4 shrink-0" aria-hidden />
                        <span>
                          Closed as a duplicate of{' '}
                          <Link
                            to={jobPath(job.duplicate_of.job_id)}
                            className="font-medium text-foreground underline underline-offset-2"
                          >
                            {job.duplicate_of.title || 'another posting'}
                          </Link>
                        </span>
                      </p>
                    ) : closedText ? (
                      <p className="flex items-center gap-2 text-body text-muted-foreground">
                        <XCircle className="size-4 shrink-0" aria-hidden /> Closed: {closedText}
                      </p>
                    ) : null}
                    <div className="border-t border-border pt-4">
                      <RateJob
                        job={job}
                        onRated={(updated) => {
                          setJob({ ...job, ...updated })
                          onChanged()
                        }}
                      />
                    </div>
                  </div>

                  {job.followup_due ? (
                    <Callout
                      icon={BellRing}
                      tone="--stage-in-progress"
                      actions={
                        <>
                          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void doFollowUp('followed_up')}>
                            I followed up
                          </Button>
                          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void doFollowUp('no_response')}>
                            No response
                          </Button>
                        </>
                      }
                    >
                      {followUpLabel(job.applied_days_ago)}. No reply yet, so a short note can help.
                    </Callout>
                  ) : null}

                  {actions.length ? (
                    <div className="hidden flex-wrap gap-2 md:flex">
                      {actions.map((a) => (
                        <ActionButton key={a.key} action={a} />
                      ))}
                    </div>
                  ) : null}
                </DrawerSection>

                <DrawerSection title="Stage">
                  <StagePicker stage={job.funnel_stage} disabled={busy} onMove={requestMove} />
                </DrawerSection>

                <DrawerSection title="Details">
                  <DetailGrid className="space-y-2">
                    <DetailRow label="Location" value={job.location || 'Not stated'} />
                    <DetailRow label="Work model" value={workModelLabel(job.work_model) || 'Not stated'} />
                    <DetailRow label="Pay" value={job.salary || 'Not stated'} />
                    <DetailRow label="Sponsorship" value={SPONSORSHIP[job.sponsorship_status] || SPONSORSHIP.not_found} />
                    <DetailRow
                      label="Found"
                      value={job.source === 'manual' ? `Added by you${fmtDay(job.discovered_at) ? ` · ${fmtDay(job.discovered_at)}` : ''}` : [fmtDay(job.discovered_at), job.site ? `on ${job.site}` : null].filter(Boolean).join(' ')}
                    />
                    {job.applied_at ? <DetailRow label="Applied" value={fmtDay(job.applied_at)} /> : null}
                    {job.whatsapp_notified_at ? <DetailRow label="On WhatsApp" value={`Sent ${fmtDay(job.whatsapp_notified_at)}`} /> : null}
                    {job.is_dead ? <DetailRow label="Posting" value="No longer accepting applications" /> : null}
                  </DetailGrid>
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
                  title={
                    <span className="inline-flex items-center gap-2">
                      <LinkedInLogo className="size-4 text-linkedin" />
                      Who you know there
                    </span>
                  }
                >
                  <ConnectionsPanel jobKey={job.job_id} connections={connections} onChanged={reload} />
                </DrawerSection>

                <DrawerSection
                  title="Notes"
                  actions={<SaveStatus state={notesState} savedAt={notesSavedAt} onRetry={() => void persistNotes(notes)} />}
                >
                  <Textarea
                    id="notes"
                    value={notes}
                    rows={3}
                    aria-label="Notes"
                    placeholder="Write notes for yourself"
                    onChange={(e) => onNotesChange(e.target.value)}
                    onBlur={() => {
                      if (saveTimer.current) clearTimeout(saveTimer.current)
                      void persistNotes(notes)
                    }}
                  />
                </DrawerSection>

                <DrawerSection>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => void toggleHistory()}
                    className="-ml-3 text-muted-foreground"
                    aria-expanded={historyOpen}
                  >
                    <History /> History
                    <ChevronDown className={cn('transition-transform duration-(--dur-2)', historyOpen && 'rotate-180')} />
                  </Button>
                  {historyOpen ? (
                    history ? (
                      <ul className="mt-3 space-y-2 text-caption">
                        {historyItems.map((e, i) => (
                          <li key={i} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
                            <span className="shrink-0 text-muted-foreground tabular-nums sm:w-44">{fmtWhen(e.at)}</span>
                            <span className="text-foreground">{e.text}</span>
                          </li>
                        ))}
                        {!historyItems.length ? <li className="text-muted-foreground">No history yet.</li> : null}
                      </ul>
                    ) : (
                      <p className="mt-3 flex items-center gap-2 text-caption text-muted-foreground">
                        <Loader2 className="size-3.5 animate-spin" /> Loading…
                      </p>
                    )
                  ) : null}
                </DrawerSection>
              </>
            )}
          </div>
        </div>

        {job ? <PhoneActionBar actions={actions} /> : null}
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

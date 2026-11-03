import { useState, type ReactNode } from 'react'
import { ArrowLeft, BellRing, CheckCircle2, ExternalLink, Loader2, Sparkles, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { ConnectionsPanel } from '@/components/ConnectionsPanel'
import { DismissDialog, type DismissResult } from '@/components/DismissDialog'
import { DrawerSection } from '@/components/DrawerSection'
import { followUpLabel } from '@/components/JobMetaBadges'
import { listingHref } from '@/components/JobSummary'
import { LinkedInLogo } from '@/components/LinkedInLogo'
import { JobCoverMaterials, JobResumeMaterials } from '@/components/MaterialsPanel'
import { StagePicker } from '@/components/StagePicker'
import { Callout } from '@/components/drawer/Callout'
import { DesktopActions, PhoneActionBar, type DrawerAction } from '@/components/drawer/DrawerActions'
import { JobDescriptionPane } from '@/components/drawer/JobDescriptionPane'
import { JobDetails } from '@/components/drawer/JobDetails'
import { JobSidePanel } from '@/components/drawer/JobSidePanel'
import { JobHistory } from '@/components/drawer/JobHistory'
import { JobNotes } from '@/components/drawer/JobNotes'
import { MatchCard } from '@/components/drawer/MatchCard'
import { useJobDrawerData } from '@/components/drawer/useJobDrawerData'
import { useJobNotes } from '@/components/drawer/useJobNotes'
import { usePrepareMaterials } from '@/components/drawer/usePrepareMaterials'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { followUpJob, moveJob, STAGE_LABELS, type JobCard } from '@/lib/api'
import { DOCK_QUERY } from '@/lib/jobPanel'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  jobKey: string | null
  onClose: () => void
  /** Something on the job's board card changed (stage, score, materials): refetch the board. */
  onChanged: () => void
  /** Desktop panel: show another job (previous / next) without closing. */
  onOpenJob?: (jobId: string) => void
  /** The job's board card, if loaded: the panel header shows it while the job loads. */
  preview?: JobCard | null
}

/** Sheet drawer only (below the docked-panel width): two columns from this width up. */
const WIDE_QUERY = '(min-width: 1440px)'

/**
 * One job: decision summary, actions, stage, details, description, materials, people, notes.
 * Desktop (DOCK_QUERY) renders it in a panel docked beside the board (`JobSidePanel`);
 * tablets and phones keep the sheet / full-screen drawer with the phone action bar.
 */
export function JobDrawer({ jobKey, onClose, onChanged, onOpenJob, preview }: Props) {
  const open = !!jobKey
  const docked = useMediaQuery(DOCK_QUERY)
  const wideScreen = useMediaQuery(WIDE_QUERY)
  const { job, setJob, materials, base, connections, reload } = useJobDrawerData(jobKey)
  const notes = useJobNotes(job)
  const [busy, setBusy] = useState(false)
  const [dismissOpen, setDismissOpen] = useState(false)

  const materialsChanged = () => {
    onChanged()
    reload()
  }
  const prepare = usePrepareMaterials(jobKey, materialsChanged)

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

  const href = job ? listingHref(job) : null
  const hasMaterials = Boolean(job?.has_resume || job?.has_cover || materials?.resume_md || materials?.cover_md)
  const beforeApplying = job ? job.funnel_stage === 'backlog' || job.funnel_stage === 'prepare' : false
  const closed = job?.funnel_stage === 'closed'
  const showMaterials = !!job && (hasMaterials || job.funnel_stage !== 'backlog' || prepare.running)
  const description = job?.full_description?.trim() || ''

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

  const placeOf = (j: JobCard) => [j.company || 'Unknown company', j.location].filter(Boolean).join(' · ')
  const place = job ? placeOf(job) : ''
  const hasRightColumn = !!job && (!!description || showMaterials)

  const renderBody = (wide: boolean): ReactNode => {
    const twoColumns = wide && hasRightColumn
    let body: ReactNode = null
    if (!job) {
      body = (
        <div className="job-drawer-scroll">
          <div className="mx-auto min-w-0 max-w-[46rem] px-4 pb-10 md:px-6">
            <div className="flex items-center gap-2 py-8 text-body text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Loading job…
            </div>
          </div>
        </div>
      )
    } else {
      const summary = (
        <DrawerSection first className="flex flex-col gap-4">
          <MatchCard
            job={job}
            onRated={(updated) => {
              setJob({ ...job, ...updated })
              onChanged()
            }}
          />
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
          <DesktopActions actions={actions} />
        </DrawerSection>
      )
      const stage = (
        <DrawerSection title="Stage">
          <StagePicker
            stage={job.funnel_stage}
            disabled={busy}
            onMove={requestMove}
            className={docked ? 'flex-wrap' : undefined}
          />
        </DrawerSection>
      )
      const details = <JobDetails job={job} />
      const descriptionSection = (first?: boolean) =>
        description ? (
          <DrawerSection first={first} title="Job description">
            <JobDescriptionPane text={description} foldable={!docked} />
          </DrawerSection>
        ) : null
      const materialsSections = (first?: boolean) =>
        showMaterials ? (
          <>
            <DrawerSection first={first} title="Resume">
              <JobResumeMaterials materials={materials} settings={base} jobKey={job.job_id} onTailored={materialsChanged} />
            </DrawerSection>
            <DrawerSection title="Cover letter">
              <JobCoverMaterials materials={materials} settings={base} jobKey={job.job_id} onTailored={materialsChanged} />
            </DrawerSection>
          </>
        ) : null
      const people = (
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
      )
      const extras = (
        <>
          <JobNotes notes={notes} />
          <JobHistory job={job} />
        </>
      )

      body = twoColumns ? (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="job-drawer-scroll border-r border-border">
            <div className="min-w-0 px-6 pb-10">
              {summary}
              {stage}
              {details}
              {people}
              {extras}
            </div>
          </div>
          <div className="job-drawer-scroll">
            <div className="min-w-0 px-6 pb-10">
              {descriptionSection(true)}
              {materialsSections(!description)}
            </div>
          </div>
        </div>
      ) : (
        <div className="job-drawer-scroll">
          <div className="mx-auto min-w-0 max-w-[46rem] px-4 pb-10 md:px-6">
            {summary}
            {stage}
            {details}
            {descriptionSection()}
            {materialsSections()}
            {people}
            {extras}
          </div>
        </div>
      )
    }
    return body
  }

  const dismissDialog = (
    <DismissDialog
      open={dismissOpen}
      jobTitle={job?.title}
      fromStage={job?.funnel_stage}
      onCancel={() => setDismissOpen(false)}
      onConfirm={onDismiss}
    />
  )

  if (docked) {
    if (!jobKey) return null
    // While a newly picked job loads, its board card names it so the header never blanks.
    const shown = job ?? (preview?.job_id === jobKey ? preview : null)
    return (
      <JobSidePanel
        jobKey={jobKey}
        title={shown?.title || 'Loading…'}
        subtitle={shown ? placeOf(shown) : undefined}
        onClose={onClose}
        onOpenJob={onOpenJob}
        dialogs={dismissDialog}
      >
        {renderBody}
      </JobSidePanel>
    )
  }

  const twoColumns = wideScreen && hasRightColumn

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        showClose={false}
        className={cn(
          'flex h-dvh min-h-0 flex-col gap-0 overflow-hidden bg-background p-0 sm:w-3/5 sm:max-w-[52rem] md:min-w-[36rem]',
          twoColumns && 'sm:w-[88vw] sm:max-w-[112rem]',
        )}
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

        {renderBody(wideScreen)}

        {job ? <PhoneActionBar actions={actions} /> : null}
      </SheetContent>
      {dismissDialog}
    </Sheet>
  )
}

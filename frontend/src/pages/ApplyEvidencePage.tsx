import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FileQuestion } from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { Page } from '@/components/PageHeader'
import { SectionHeader } from '@/components/SectionHeader'
import { ConfirmDialog } from '@/components/admin/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getSubmission, submissionScreenshotUrl, vetoPick, type ApplyPick, type Submission } from '@/lib/api'
import { errorMessage } from '@/lib/utils'

const OUTCOME: Record<string, { label: string; tone: 'success' | 'warning' | 'destructive' | 'secondary' }> = {
  applied: { label: 'Applied, confirmation seen', tone: 'success' },
  unverified: { label: 'Sent, no confirmation seen', tone: 'warning' },
  dry_run: { label: 'Practice run, nothing sent', tone: 'secondary' },
  needs_answer: { label: 'Skipped: needs your answer', tone: 'warning' },
  captcha_timeout: { label: 'Skipped: check not solved in time', tone: 'warning' },
  expired: { label: 'Posting closed', tone: 'secondary' },
  running: { label: 'In progress', tone: 'secondary' },
}

const SOURCE: Record<string, string> = {
  answer_bank: 'Your saved answer',
  profile: 'Your profile',
  resume: 'Your profile',
  resume_ai: 'Written from your resume',
  ai: 'Written from your resume',
  materials: 'Your documents',
  file: 'Your documents',
  secret: 'Hidden',
}

const SHOTS: [string, string][] = [
  ['filled', 'Form filled in'],
  ['review', 'Before sending'],
  ['confirmation', 'After sending'],
]

function PlannedPick({ pick, onVetoed }: { pick: ApplyPick; onVetoed: () => void }) {
  const [open, setOpen] = useState(false)
  const when = new Date(pick.apply_after).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-muted px-4 py-3">
      <p className="min-w-0 flex-1 text-body text-foreground">
        Planned for <span className="tabular-nums">{when}</span>.
      </p>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Don’t apply
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Skip this application?"
        description="jobwright will not apply to this job automatically."
        confirmLabel="Skip it"
        onConfirm={async () => {
          try {
            await vetoPick(pick.id)
            toast.success('Skipped')
            onVetoed()
          } catch (e) {
            toast.error(errorMessage(e))
          }
        }}
      />
    </div>
  )
}

/** /apply/submissions/:submissionId: what was filled in, the screenshots, and the result. */
export function ApplyEvidencePage() {
  const { submissionId = '' } = useParams<{ submissionId: string }>()
  const [sub, setSub] = useState<Submission | null>(null)
  const [missing, setMissing] = useState(false)

  const load = useCallback(() => {
    getSubmission(submissionId)
      .then(setSub)
      .catch(() => setMissing(true))
  }, [submissionId])

  useEffect(load, [load])

  if (missing) {
    return (
      <Page title="Application">
        <EmptyState icon={FileQuestion} title="Not found" description="This record is for another profile or was removed." />
      </Page>
    )
  }
  if (!sub) {
    return (
      <Page title="Application">
        <Skeleton className="h-64 w-full" />
      </Page>
    )
  }

  const outcome = OUTCOME[sub.outcome] ?? { label: sub.outcome, tone: 'destructive' as const }
  const planned = (sub.picks || []).filter((p) => p.status === 'planned')

  return (
    <Page
      title={sub.title || 'Application'}
      description={[sub.company, new Date(sub.started_at).toLocaleString()].filter(Boolean).join(' · ')}
      width="wide"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={outcome.tone}>{outcome.label}</Badge>
        {sub.job_id ? (
          <Button variant="link" className="h-auto p-0" asChild>
            <Link to={`/jobs/${sub.job_id}`}>Open the job</Link>
          </Button>
        ) : null}
      </div>
      {sub.verification_evidence ? (
        <p className="mt-2 text-caption text-muted-foreground">Check: {sub.verification_evidence}</p>
      ) : null}
      {sub.error && sub.outcome !== 'applied' ? (
        <p className="mt-2 text-caption text-muted-foreground">{sub.error}</p>
      ) : null}
      {planned.map((p) => (
        <div key={p.id} className="mt-4">
          <PlannedPick pick={p} onVetoed={load} />
        </div>
      ))}

      {sub.needs.filter((n) => n.kind === 'answer').length ? (
        <>
          <SectionHeader title="Questions only you can answer" description="Reply in WhatsApp or save them in Settings → About you." />
          <ul className="list-disc space-y-1 pl-5 text-body text-foreground">
            {sub.needs
              .filter((n) => n.kind === 'answer')
              .map((n) => (
                <li key={n.detail}>{n.question || n.detail}</li>
              ))}
          </ul>
        </>
      ) : null}

      <SectionHeader title="What was filled in" />
      {sub.fields.length ? (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {sub.fields.map((f, i) => (
            <li key={`${f.label}-${i}`} className="grid gap-1 px-4 py-3 md:grid-cols-[2fr_3fr_1fr] md:gap-4">
              <span className="text-label text-foreground">{f.label}</span>
              <span className="text-body break-words text-muted-foreground">{f.value}</span>
              <span className="text-caption text-subtle-foreground md:text-right">{SOURCE[f.source] ?? f.source}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-muted-foreground">Nothing was filled in.</p>
      )}

      <SectionHeader title="Screenshots" />
      <div className="grid gap-4 md:grid-cols-3">
        {SHOTS.filter(([k]) => sub.screenshots[k]).map(([k, label]) => (
          <figure key={k}>
            <a href={submissionScreenshotUrl(sub.id, k)} target="_blank" rel="noreferrer">
              <img
                src={submissionScreenshotUrl(sub.id, k)}
                alt={label}
                className="w-full rounded-lg border border-border"
                loading="lazy"
              />
            </a>
            <figcaption className="mt-1.5 text-caption text-muted-foreground">{label}</figcaption>
          </figure>
        ))}
      </div>
    </Page>
  )
}

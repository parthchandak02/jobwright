import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Gauge, Lightbulb, Loader2, RefreshCw, SlidersHorizontal, ThumbsUp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { Page } from '@/components/PageHeader'
import { RunProgressDialog } from '@/components/RunProgressDialog'
import { SectionHeader } from '@/components/SectionHeader'
import { ConfirmDialog } from '@/components/admin/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getCriteria,
  getQuality,
  patchCutoff,
  startEval,
  startRescore,
  type EvalMetrics,
  type MatchCriteria,
  type QualitySummary,
  type RunHandle,
} from '@/lib/api'
import { useMe } from '@/lib/me'
import { useRunStream } from '@/lib/useRunStream'
import { cn, errorMessage } from '@/lib/utils'

const RATINGS_FOR_CHECK = 20

const pct = (x: number | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`)

function inTen(x: number): string {
  const n = Math.round(x * 10)
  if (n >= 10) return 'almost every time'
  if (n <= 0) return 'rarely'
  return `about ${n} in 10 times`
}

function ofTen(x: number): string {
  const n = Math.round(x * 10)
  if (n >= 10) return 'almost all'
  if (n <= 0) return 'few'
  return `about ${n} in 10`
}

function Tile({ value, label, sub }: { value: ReactNode; label: string; sub?: string }) {
  return (
    <div className="surface min-w-0 rounded-lg px-3 py-3 md:px-5 md:py-4">
      <p className="text-title text-foreground tabular-nums md:text-display">{value}</p>
      <p className="mt-1 text-caption text-foreground">{label}</p>
      {sub ? <p className="text-caption text-muted-foreground">{sub}</p> : null}
    </div>
  )
}

function Progress({ value, max, label }: { value: number; max: number; label: string }) {
  const ratio = Math.min(1, value / max)
  return (
    <div className="space-y-1.5">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.min(value, max)}
        aria-label={label}
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-(--dur-3)" style={{ width: `${ratio * 100}%` }} />
      </div>
      <p className="text-caption text-muted-foreground tabular-nums">
        {Math.min(value, max)} of {max} ratings
      </p>
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-8" aria-busy>
      <div className="grid grid-cols-3 gap-3 md:gap-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 rounded-lg md:h-28" />
        ))}
      </div>
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>
  )
}

type CriteriaState = { criteria: MatchCriteria; derived: boolean } | null

function Recommendation({
  rec,
  current,
  canApply,
  applying,
  onApply,
  onOpenRules,
}: {
  rec: NonNullable<QualitySummary['recommended_threshold']>
  current: number
  canApply: boolean
  applying: boolean
  onApply: () => void
  onOpenRules: () => void
}) {
  if (rec.threshold === current) {
    return (
      <p className="flex items-start gap-2 text-body text-muted-foreground">
        <ThumbsUp className="mt-1 size-4 shrink-0 text-success" aria-hidden />
        Your cutoff ({current}+) is the one we'd recommend{rec.meets_bar ? '' : ' for now. More ratings will sharpen it'}.
      </p>
    )
  }
  const lower = rec.threshold < current
  return (
    <div className="surface flex flex-col gap-4 rounded-lg px-4 py-4 sm:flex-row sm:items-center md:px-5">
      <Lightbulb className="hidden size-5 shrink-0 text-primary sm:block" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-subheading text-foreground">Try sending jobs scored {rec.threshold}+</p>
        <p className="mt-1 text-body text-muted-foreground">
          You use {current}+ now. At {rec.threshold}+ you'd get {lower ? 'more jobs' : 'fewer jobs'}, and{' '}
          {ofTen(rec.precision)} would {lower ? 'still ' : ''}be a fit.
          {rec.meets_bar ? '' : ' This is our best guess so far; more ratings will make it better.'}
        </p>
        {!canApply ? (
          <p className="mt-2 text-caption text-muted-foreground">Change it any time in Profile → Match rules.</p>
        ) : null}
      </div>
      {canApply ? (
        <Button onClick={onApply} disabled={applying} className="shrink-0 max-sm:w-full">
          {applying ? <Loader2 className="animate-spin" /> : null}
          Use {rec.threshold}+
        </Button>
      ) : (
        <Button variant="secondary" onClick={onOpenRules} className="shrink-0 max-sm:w-full">
          <SlidersHorizontal /> Open Match rules
        </Button>
      )}
    </div>
  )
}

function MetricRow({ label, m, base }: { label: string; m?: EvalMetrics; base?: EvalMetrics }) {
  return (
    <tr>
      <td className="py-2.5 pr-4 pl-4 md:pl-5">{label}</td>
      <td className="py-2.5 pr-4 text-right">{pct(m?.precision)}</td>
      <td className="py-2.5 pr-4 text-right">{pct(m?.recall)}</td>
      <td className="py-2.5 pr-4 text-right text-muted-foreground md:pr-5">
        {pct(base?.precision)} / {pct(base?.recall)}
      </td>
    </tr>
  )
}

function purposeLabel(purpose: string): string {
  if (purpose === 'score' || purpose === 'score:t1') return 'Scoring jobs'
  if (purpose.startsWith('score:')) return 'Scoring jobs (second opinion)'
  if (purpose === 'criteria') return 'Drafting match rules'
  if (purpose === 'onboarding') return 'Setup draft'
  return 'Other (resumes, letters)'
}

function AdminTools({
  q,
  busy,
  onRun,
}: {
  q: QualitySummary
  busy: boolean
  onRun: (kind: 'eval' | 'rescore') => void
}) {
  const ev = q.latest_eval
  const usage = new Map<string, { tokens: number; cost: number | null; raw: string[] }>()
  for (const u of q.usage_30d) {
    const key = purposeLabel(u.purpose)
    const row = usage.get(key) ?? { tokens: 0, cost: null, raw: [] }
    row.tokens += u.prompt_tokens + u.completion_tokens
    if (u.cost_usd != null) row.cost = (row.cost ?? 0) + u.cost_usd
    row.raw.push(u.purpose)
    usage.set(key, row)
  }
  const totalTokens = [...usage.values()].reduce((n, r) => n + r.tokens, 0)
  const totalCost = [...usage.values()].reduce<number | null>((n, r) => (r.cost == null ? n : (n ?? 0) + r.cost), null)
  const th = 'pb-2.5 pt-3 pr-4 text-right font-normal'

  return (
    <section aria-labelledby="admin-tools">
      <SectionHeader
        id="admin-tools"
        title="Admin tools"
        description="Only admins see this. Both actions make AI calls for this profile."
      />
      <div className="space-y-6">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => onRun('eval')} disabled={busy}>
            <Gauge /> Run accuracy check
          </Button>
          <Button variant="secondary" onClick={() => onRun('rescore')} disabled={busy}>
            <RefreshCw /> Rescore open jobs
          </Button>
        </div>

        {ev ? (
          <div className="space-y-2">
            <h3 className="text-subheading">Last accuracy check</h3>
            <p className="text-caption text-muted-foreground tabular-nums">
              {new Date(ev.at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })} ·{' '}
              {String(ev.config?.n ?? '?')} jobs ({String(ev.config?.positives ?? '?')} wanted) · scorer{' '}
              {ev.prompt_version}
              {ev.errors ? ` · ${ev.errors} errors` : ''}
            </p>
            <div className="surface overflow-x-auto rounded-lg">
              <table className="w-full text-body tabular-nums">
                <thead className="text-caption text-muted-foreground">
                  <tr className="border-b">
                    <th className="pt-3 pr-4 pb-2.5 pl-4 text-left font-normal md:pl-5">Cutoff</th>
                    <th className={th}>Precision</th>
                    <th className={th}>Recall</th>
                    <th className={cn(th, 'md:pr-5')} title="Previous scorer, precision / recall">Before</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  <MetricRow label="7+ (ratings)" m={ev.metrics_explicit?.['7']} base={ev.baseline_explicit?.['7']} />
                  <MetricRow label="7+ (incl. closed)" m={ev.metrics?.['7']} base={ev.baseline?.['7']} />
                  <MetricRow label="6+ (ratings)" m={ev.metrics_explicit?.['6']} base={ev.baseline_explicit?.['6']} />
                </tbody>
              </table>
            </div>
            <p className="text-caption text-muted-foreground">
              Precision: of the jobs it would send, how many were wanted. Recall: of the wanted jobs, how many it would
              send.
            </p>
          </div>
        ) : null}

        <div className="space-y-2">
          <h3 className="text-subheading">AI usage, last 30 days</h3>
          {usage.size ? (
            <div className="surface overflow-hidden rounded-lg">
              <table className="w-full text-body tabular-nums">
                <thead className="text-caption text-muted-foreground">
                  <tr className="border-b">
                    <th className="pt-3 pr-4 pb-2.5 pl-4 text-left font-normal md:pl-5">Used for</th>
                    <th className={th}>Tokens</th>
                    <th className={cn(th, 'md:pr-5')}>Est. cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {[...usage.entries()].map(([label, r]) => (
                    <tr key={label} title={r.raw.join(', ')}>
                      <td className="py-2.5 pr-4 pl-4 md:pl-5">{label}</td>
                      <td className="py-2.5 pr-4 text-right">{r.tokens.toLocaleString()}</td>
                      <td className="py-2.5 pr-4 text-right md:pr-5">{r.cost == null ? '—' : `$${r.cost.toFixed(2)}`}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t font-medium">
                    <td className="py-2.5 pr-4 pl-4 md:pl-5">Total</td>
                    <td className="py-2.5 pr-4 text-right">{totalTokens.toLocaleString()}</td>
                    <td className="py-2.5 pr-4 text-right md:pr-5">{totalCost == null ? '—' : `$${totalCost.toFixed(2)}`}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <p className="text-caption text-muted-foreground">No AI calls in the last 30 days.</p>
          )}
        </div>
      </div>
    </section>
  )
}

/** How well matching works for this profile, and how ratings improve it. */
export function QualityPage() {
  const { me } = useMe()
  const navigate = useNavigate()
  const isAdmin = !!me?.is_admin
  const [q, setQ] = useState<QualitySummary | null>(null)
  const [loadError, setLoadError] = useState('')
  const [criteria, setCriteria] = useState<CriteriaState>(null)
  const [handle, setHandle] = useState<RunHandle | null>(null)
  const [runTitle, setRunTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [applying, setApplying] = useState(false)
  const [confirm, setConfirm] = useState<'eval' | 'rescore' | null>(null)

  const load = useCallback(() => {
    setLoadError('')
    void getQuality()
      .then(setQ)
      .catch((e) => setLoadError(errorMessage(e)))
    void getCriteria()
      .then(setCriteria)
      .catch(() => setCriteria(null))
  }, [])

  useEffect(load, [load])

  async function run(kind: 'eval' | 'rescore') {
    setBusy(true)
    try {
      const h = kind === 'eval' ? await startEval() : await startRescore()
      setRunTitle(kind === 'eval' ? 'Checking accuracy against your ratings' : 'Rescoring open jobs')
      setHandle(h)
    } catch (e) {
      toast.error(errorMessage(e))
      throw e
    } finally {
      setBusy(false)
    }
  }

  const stream = useRunStream(handle, load)
  const ev = q?.latest_eval
  const rec = q?.recommended_threshold
  const current = criteria?.criteria.notify_threshold ?? rec?.current ?? 7
  const canApply = !!criteria

  async function applyCutoff(n: number) {
    if (!canApply || !criteria) return
    setApplying(true)
    try {
      await patchCutoff(n)
      toast.success(`Done. Your daily list now sends jobs scored ${n}+.`)
      load()
    } catch (e) {
      toast.error(`Couldn't change the cutoff: ${errorMessage(e)}`)
    } finally {
      setApplying(false)
    }
  }

  const m = ev ? (ev.metrics_explicit?.[String(current)] ?? ev.metrics?.[String(current)]) : undefined
  const sent = q?.notified_30d ?? 0
  const needMore = Math.max(0, RATINGS_FOR_CHECK - (q?.labels_total ?? 0))

  return (
    <Page
      title="How well we match you"
      description="Your ratings teach jobwright what fits you."
      width="wide"
      bodyClassName="space-y-section"
      actions={
        <Button size="icon-sm" variant="ghost" onClick={load} aria-label="Refresh">
          <RefreshCw />
        </Button>
      }
    >
      {loadError && !q ? (
        <div className="surface rounded-lg">
          <EmptyState
            icon={Gauge}
            title="Couldn't load your match quality"
            description={loadError}
            action={
              <Button variant="secondary" onClick={load}>
                <RefreshCw /> Try again
              </Button>
            }
          />
        </div>
      ) : !q ? (
        <PageSkeleton />
      ) : (
        <>
          <section aria-label="Last 30 days">
            <div className="grid grid-cols-3 gap-3 md:gap-4">
              <Tile value={sent} label="jobs sent" sub="last 30 days" />
              <Tile
                value={sent ? pct(q.notified_advanced_30d / sent) : '—'}
                label="moved forward"
                sub={sent ? `${q.notified_advanced_30d} of ${sent}` : 'nothing sent yet'}
              />
              <Tile value={q.labels_total} label="ratings" sub={`${q.labels_30d} this month`} />
            </div>
          </section>

          <section aria-labelledby="ratings-heading">
            <SectionHeader
              id="ratings-heading"
              title="Your ratings"
              description="Tap the thumbs up or “Not for me” on any job. Each rating is kept and used as an example when similar jobs are scored."
            />
            {needMore > 0 ? (
              <div className="surface space-y-3 rounded-lg px-4 py-4 md:px-5">
                <p className="text-body text-foreground">
                  Rate {needMore} more job{needMore === 1 ? '' : 's'} so we can check how accurate your matches are.
                </p>
                <Progress value={q.labels_total} max={RATINGS_FOR_CHECK} label="Ratings toward the first accuracy check" />
              </div>
            ) : (
              <p className="text-body text-muted-foreground">
                {q.labels_30d
                  ? `You rated ${q.labels_30d} job${q.labels_30d === 1 ? '' : 's'} this month. Rating a few each day keeps your list sharp.`
                  : 'No ratings this month. Rating a few jobs each day keeps your list sharp.'}
              </p>
            )}
          </section>

          <section aria-labelledby="accuracy-heading">
            <SectionHeader
              id="accuracy-heading"
              title="Match accuracy"
              description="How often the jobs we send are ones you'd want, based on your ratings."
            />
            {ev && m && m.predicted_pos > 0 ? (
              <div className="space-y-5">
                <p className="text-subheading font-normal text-foreground">
                  When we send you a job scored {current}+, it's one you'd want{' '}
                  <span className="font-semibold">{inTen(m.precision)}</span>.
                  <span className="text-muted-foreground">
                    {' '}
                    We find {ofTen(m.recall)} of the jobs you'd want.
                  </span>
                </p>
                {rec ? (
                  <Recommendation
                    rec={rec}
                    current={current}
                    canApply={canApply}
                    applying={applying}
                    onApply={() => void applyCutoff(rec.threshold)}
                    onOpenRules={() => navigate('/profile?tab=rules')}
                  />
                ) : null}
              </div>
            ) : (
              <div className="surface rounded-lg">
                {needMore > 0 ? (
                  <EmptyState
                    icon={Gauge}
                    title={`We'll check accuracy after you rate ${RATINGS_FOR_CHECK} jobs`}
                    description="Then you'll see how often our picks are right, and a suggested cutoff for your daily list."
                  />
                ) : (
                  <EmptyState
                    icon={Gauge}
                    title="No accuracy check yet"
                    description={
                      isAdmin
                        ? 'You have enough ratings. Run an accuracy check below to see how often the picks are right.'
                        : 'You have enough ratings. The next accuracy check will show how often our picks are right.'
                    }
                  />
                )}
              </div>
            )}
          </section>

          {isAdmin ? <AdminTools q={q} busy={busy} onRun={setConfirm} /> : null}
        </>
      )}

      <ConfirmDialog
        open={confirm === 'eval'}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Run an accuracy check?"
        description="Replays the scorer on every rated or applied job for this profile. It makes one AI call per job and can take a few minutes. Nothing is sent to WhatsApp."
        confirmLabel="Run check"
        icon={<Gauge />}
        onConfirm={() => run('eval')}
      />
      <ConfirmDialog
        open={confirm === 'rescore'}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Rescore open jobs?"
        description="Scores every open job on this profile again and replaces the current scores (the old ones stay in history). It makes one AI call per job and can take several minutes."
        confirmLabel="Rescore"
        icon={<RefreshCw />}
        onConfirm={() => run('rescore')}
      />
      <RunProgressDialog
        open={!!handle}
        onClose={() => {
          setHandle(null)
          load()
        }}
        title={runTitle}
        description="Closing this window does not stop the run."
        stageLabels={{ run: 'Running' }}
        run={stream}
      />
    </Page>
  )
}

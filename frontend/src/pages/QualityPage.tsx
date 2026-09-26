import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Gauge, Loader2, RefreshCw, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { RunProgressDialog } from '@/components/RunProgressDialog'
import { Button } from '@/components/ui/button'
import { getQuality, startEval, startRescore, type EvalMetrics, type QualitySummary, type RunHandle } from '@/lib/api'
import { useRunStream } from '@/lib/useRunStream'
import { cn, errorMessage } from '@/lib/utils'

function Card({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn('glass space-y-3 rounded-xl p-4', className)}>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      {children}
    </section>
  )
}

function Big({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

const pct = (x: number | undefined) => (x == null ? '–' : `${Math.round(x * 100)}%`)

function MetricRow({ label, m, base }: { label: string; m?: EvalMetrics; base?: EvalMetrics }) {
  return (
    <tr className="border-t border-border/50">
      <td className="py-1.5 pr-3 text-xs text-muted-foreground">{label}</td>
      <td className="py-1.5 pr-3 text-sm font-medium tabular-nums">{pct(m?.precision)}</td>
      <td className="py-1.5 pr-3 text-sm tabular-nums">{pct(m?.recall)}</td>
      <td className="py-1.5 text-xs tabular-nums text-muted-foreground">
        {pct(base?.precision)} / {pct(base?.recall)}
      </td>
    </tr>
  )
}

/** How well matching works for this profile, and how ratings improve it. */
export function QualityPage() {
  const [q, setQ] = useState<QualitySummary | null>(null)
  const [handle, setHandle] = useState<RunHandle | null>(null)
  const [runTitle, setRunTitle] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    void getQuality()
      .then(setQ)
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  useEffect(load, [load])

  async function run(kind: 'eval' | 'rescore') {
    setBusy(true)
    try {
      const handle = kind === 'eval' ? await startEval() : await startRescore()
      setRunTitle(kind === 'eval' ? 'Checking accuracy against your ratings' : 'Rescoring open jobs')
      setHandle(handle)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const stream = useRunStream(handle, load)
  const ev = q?.latest_eval
  const tokens = (q?.usage_30d || []).reduce((n, u) => n + u.prompt_tokens + u.completion_tokens, 0)
  const cost = (q?.usage_30d || []).reduce((n, u) => n + (u.cost_usd || 0), 0)

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className={cn(APP_SHELL_HEADER, 'sticky top-0 z-20')}>
        <Gauge className="size-4 text-muted-foreground" />
        <h1 className="text-xs font-bold uppercase tracking-wider">Match quality</h1>
        <Button size="icon-sm" variant="ghost" className="ml-auto" onClick={load} aria-label="Refresh">
          <RefreshCw />
        </Button>
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        {!q ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </p>
        ) : (
          <div className="mx-auto grid w-full max-w-5xl gap-4 md:grid-cols-2">
            <Card title="Your ratings teach the scorer" className="md:col-span-2">
              <p className="text-sm text-muted-foreground">
                Every time you tap <ThumbsUp className="inline size-3.5" /> or “Not for me” on a job, the rating is saved
                for good and used as an example when similar jobs are scored. The more you rate, the sharper your
                daily list gets.
              </p>
              <div className="flex flex-wrap gap-8">
                <Big value={q.labels_total} label="ratings so far" />
                <Big value={q.labels_30d} label="in the last 30 days" />
                <Big value={q.eval_set.relevant} label={`of ${q.eval_set.size} rated or applied jobs were a fit`} />
              </div>
            </Card>

            <Card title="Jobs sent to you (30 days)">
              <div className="flex flex-wrap gap-8">
                <Big value={q.notified_30d} label="sent on WhatsApp" />
                <Big
                  value={q.notified_30d ? pct(q.notified_advanced_30d / q.notified_30d) : '–'}
                  label="moved forward by you"
                />
              </div>
            </Card>

            <Card title="AI usage (30 days)">
              <div className="flex flex-wrap gap-8">
                <Big value={tokens.toLocaleString()} label="tokens" />
                {cost ? <Big value={`$${cost.toFixed(2)}`} label="estimated cost" /> : null}
              </div>
              <ul className="space-y-0.5 text-xs text-muted-foreground">
                {q.usage_30d.map((u) => (
                  <li key={u.purpose}>
                    {u.purpose}: {(u.prompt_tokens + u.completion_tokens).toLocaleString()}
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Accuracy check" className="md:col-span-2">
              <p className="text-sm text-muted-foreground">
                Replays the current scorer on jobs you rated or applied to. Precision is how many jobs it would send you
                that you actually wanted; recall is how many of those it would catch.
              </p>
              {ev ? (
                <>
                  <p className="text-xs text-muted-foreground">
                    Last run {new Date(ev.at).toLocaleString()} · {String(ev.config?.n ?? '?')} jobs (
                    {String(ev.config?.positives ?? '?')} wanted) · scorer {ev.prompt_version}
                  </p>
                  <table className="w-full max-w-lg text-left">
                    <thead>
                      <tr className="text-xs text-muted-foreground">
                        <th className="pb-1 font-medium">Sent at score</th>
                        <th className="pb-1 font-medium">Precision</th>
                        <th className="pb-1 font-medium">Recall</th>
                        <th className="pb-1 font-medium">Old scorer (P / R)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <MetricRow label="7+ (your ratings)" m={ev.metrics_explicit?.['7']} base={ev.baseline_explicit?.['7']} />
                      <MetricRow label="7+ (incl. closed jobs)" m={ev.metrics?.['7']} base={ev.baseline?.['7']} />
                      <MetricRow label="6+ (your ratings)" m={ev.metrics_explicit?.['6']} base={ev.baseline_explicit?.['6']} />
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="text-sm">No accuracy check yet.</p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => void run('eval')} disabled={busy}>
                  Run accuracy check
                </Button>
                <Button size="sm" variant="outline" onClick={() => void run('rescore')} disabled={busy}>
                  Rescore my open jobs
                </Button>
              </div>
            </Card>
          </div>
        )}
      </main>
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
    </div>
  )
}

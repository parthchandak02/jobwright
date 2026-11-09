import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Check, Copy, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ConfirmAction } from '@/components/profile/ConfirmAction'
import { SectionHeader } from '@/components/SectionHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getConnector,
  putApplyVia,
  revokeConnectedClaude,
  type ApplyVia,
  type ConnectedClaude,
  type ConnectorStatus,
} from '@/lib/api'
import {
  addMinutes,
  ANSWERS_PROMPT,
  CHROME_WEB_STORE_URL,
  clockTime,
  currentStep,
  DAILY_PROMPT,
  DAILY_TASK_BUFFER_MINUTES,
  durationWords,
  guideSteps,
  readGuideFlags,
  THINGS_TO_ASK,
  writeGuideFlag,
  type GuideFlags,
  type GuideStepId,
} from '@/lib/claudeGuide'
import { APPLY_VIA_OPTIONS, describeClient } from '@/lib/connector'
import { useMe } from '@/lib/me'
import { cn, errorMessage } from '@/lib/utils'

function CopyButton({ text, label, className, compact }: { text: string; label: string; className?: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="secondary"
      size="sm"
      aria-label={label}
      className={cn('shrink-0', className)}
      onClick={() => {
        void navigator.clipboard?.writeText(text)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? <Check /> : <Copy />}
      {/* compact: icon only on phones, so short prompts keep the row's width */}
      <span aria-live="polite" className={compact ? 'max-sm:sr-only' : undefined}>
        {copied ? 'Copied' : 'Copy'}
      </span>
    </Button>
  )
}

/** A copy-ready prompt: the words on a muted panel, Copy beside them (below on narrow screens). */
function PromptBox({ text, label }: { text: string; label: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-md bg-surface-muted p-3 sm:flex-row sm:items-start">
      <p className="min-w-0 flex-1 text-body text-foreground">{text}</p>
      <CopyButton text={text} label={label} className="self-start" />
    </div>
  )
}

const STEP_TITLE: Record<GuideStepId, string> = {
  connect: 'Connect your Claude',
  answers: 'Save your application answers',
  chrome: 'Turn on Claude in Chrome',
  daily: 'Apply every day',
}

type StepProps = {
  index: number
  total: number
  title: string
  done: boolean
  current: boolean
  open: boolean
  onToggle: () => void
  /** One line shown when the step is folded. */
  summary: ReactNode
  children: ReactNode
}

function GuideStep({ index, total, title, done, current, open, onToggle, summary, children }: StepProps) {
  const bodyId = `claude-step-${index}`
  const status = done ? 'done' : current ? 'up next' : 'not done yet'
  return (
    <li aria-current={current ? 'step' : undefined} className={cn('px-4 py-4 sm:px-5', current && 'py-5')}>
      <div className="flex items-start gap-3 sm:gap-4">
        <span
          aria-hidden
          className={cn(
            'mt-px flex size-6 shrink-0 items-center justify-center rounded-full text-caption font-semibold tabular-nums',
            done
              ? 'tone-tint [--tone:var(--success)]'
              : current
                ? 'bg-primary text-primary-foreground'
                : 'border border-border-strong text-muted-foreground',
          )}
        >
          {done ? <Check className="size-3.5" strokeWidth={3} /> : index}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={cn('text-subheading', done ? 'text-muted-foreground' : 'font-semibold text-foreground')}>
            <span className="sr-only">
              Step {index} of {total}, {status}:{' '}
            </span>
            {title}
          </h3>
          {!open ? <p className="mt-0.5 text-caption text-muted-foreground">{summary}</p> : null}
        </div>
        {!current || done ? (
          <Button
            variant="ghost"
            size="xs"
            aria-expanded={open}
            aria-controls={bodyId}
            onClick={onToggle}
            className="-mt-0.5 shrink-0 text-muted-foreground"
          >
            {open ? 'Hide' : done ? 'See steps' : 'Show'}
            <span className="sr-only"> for {title}</span>
          </Button>
        ) : null}
      </div>
      {open ? (
        // Phones use the full width; wider screens line the body up under the title.
        <div id={bodyId} className="mt-4 space-y-4 text-body text-muted-foreground sm:mt-3 sm:pl-10">
          {children}
        </div>
      ) : null}
    </li>
  )
}

/** Plain numbered sub-steps inside a guide step. */
function SubSteps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="space-y-2.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2.5">
          <span aria-hidden className="w-4 shrink-0 text-right text-caption leading-6 text-subtle-foreground tabular-nums">
            {i + 1}.
          </span>
          <div className="min-w-0 flex-1">{item}</div>
        </li>
      ))}
    </ol>
  )
}

function ManualCheck({ id, checked, onChange, children }: { id: string; checked: boolean; onChange: (on: boolean) => void; children: ReactNode }) {
  return (
    <label htmlFor={id} className="flex min-h-11 cursor-pointer items-center gap-3 text-label text-foreground">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      {children}
    </label>
  )
}

/** Today's rhythm: picks arrive, the skip window, then Claude applies. */
function DailyTimeline({ data }: { data: ConnectorStatus }) {
  const pick = data.daily_pick
  const picksAt = clockTime(pick.next_at)
  const applyAt = clockTime(pick.apply_at)
  const span = durationWords(pick.veto_minutes)
  const rows: [string, ReactNode][] = [
    [picksAt ?? 'Each morning', 'Your picks for the day arrive in your WhatsApp group.'],
    [
      applyAt ? `Until ${applyAt}` : `For ${span}`,
      <>
        Reply <q className="text-foreground">skip 1</q> or <q className="text-foreground">skip all</q> to stop any of them.
      </>,
    ],
    [applyAt ? `After ${applyAt}` : 'After that', 'Your Claude applies to the rest.'],
  ]
  return (
    <dl className="space-y-3 rounded-md bg-surface-muted px-4 py-3 sm:space-y-2">
      {rows.map(([when, what]) => (
        <div key={String(when)} className="sm:grid sm:grid-cols-[7.5rem_1fr] sm:gap-x-4">
          <dt className="text-label whitespace-nowrap text-foreground tabular-nums">{when}</dt>
          <dd className="text-body text-muted-foreground">{what}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Settings → Claude: a guided setup from connecting the person's own Claude to applying every day. */
export function ClaudeTab() {
  const navigate = useNavigate()
  const { me } = useMe()
  const userId = me?.active_user ?? null
  const [data, setData] = useState<ConnectorStatus | null>(null)
  const [flags, setFlags] = useState<GuideFlags>(() => readGuideFlags(userId))
  const [expanded, setExpanded] = useState<Partial<Record<GuideStepId, boolean>>>({})
  const [revoking, setRevoking] = useState<ConnectedClaude | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback((quiet: boolean) => {
    getConnector()
      .then(setData)
      .catch((e) => {
        if (!quiet) toast.error(errorMessage(e))
      })
  }, [])

  useEffect(() => {
    load(false)
    // Coming back from Claude (or the Applications tab in another window) updates the steps.
    const onFocus = () => document.visibilityState === 'visible' && load(true)
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
  }, [load])

  useEffect(() => setFlags(readGuideFlags(userId)), [userId])

  if (!data) {
    return (
      <div className="space-y-field" aria-busy aria-label="Loading Claude settings">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  async function chooseVia(next: ApplyVia) {
    if (!data || next === data.apply_via) return
    setSaving(true)
    try {
      setData(await putApplyVia(next))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  function setFlag(flag: keyof GuideFlags, on: boolean) {
    writeGuideFlag(userId, flag, on)
    setFlags((f) => ({ ...f, [flag]: on }))
    // Ticking a step folds it; the next one opens on its own.
    const id: GuideStepId = flag === 'chrome' ? 'chrome' : 'daily'
    setExpanded((e) => ({ ...e, [id]: on ? false : e[id] }))
  }

  const steps = guideSteps(data, flags)
  const current = currentStep(steps)
  const doneCount = steps.filter((s) => s.done).length
  const isOpen = (id: GuideStepId) => expanded[id] ?? id === current
  const toggle = (id: GuideStepId) => setExpanded((e) => ({ ...e, [id]: !isOpen(id) }))

  const options = APPLY_VIA_OPTIONS.filter((o) => o.value !== 'server' || data.can_choose_server || data.apply_via === 'server')
  const via = APPLY_VIA_OPTIONS.find((o) => o.value === data.apply_via)
  const pick = data.daily_pick
  const picksAt = clockTime(pick.next_at)
  const applyAt = clockTime(pick.apply_at)
  const taskAt = clockTime(addMinutes(pick.apply_at, DAILY_TASK_BUFFER_MINUTES))
  const everyDay = pick.days === 'weekdays' ? 'every weekday' : 'every day'
  const missing = data.missing_answers ?? 0
  const names = [...new Set(data.clients.map((c) => c.client_name))].join(', ')

  const stepBody: Record<GuideStepId, { summary: ReactNode; body: ReactNode }> = {
    connect: {
      summary: data.clients.length ? `Connected · ${names}` : 'Add jobwright to Claude. Takes about a minute.',
      body: (
        <>
          {!data.enabled ? (
            <p className="text-body text-foreground">
              <Badge variant="warning" className="mr-1.5">
                Not available yet
              </Badge>
              Connecting isn’t turned on for this jobwright yet. Ask your jobwright admin.
            </p>
          ) : null}
          <SubSteps
            items={[
              <>
                In Claude, open <span className="text-foreground">Settings</span>, then{' '}
                <span className="text-foreground">Connectors</span>, then{' '}
                <span className="text-foreground">Add custom connector</span>.
              </>,
              <>
                Name it <span className="text-foreground">jobwright</span> and paste this address:
                <div className="mt-2 flex flex-col gap-2 rounded-md bg-surface-muted p-2 pl-3 sm:flex-row sm:items-center">
                  <code className="min-w-0 flex-1 text-label [overflow-wrap:anywhere] text-foreground max-sm:text-caption">
                    {/* Wrap before the last "/" rather than mid-word on narrow screens. */}
                    {data.url.slice(0, data.url.lastIndexOf('/'))}
                    <wbr />
                    {data.url.slice(data.url.lastIndexOf('/'))}
                  </code>
                  <CopyButton text={data.url} label="Copy the connector address" className="self-start sm:self-auto" />
                </div>
              </>,
              <>
                Press <span className="text-foreground">Connect</span>. Sign in with the same email you use here, then
                press <span className="text-foreground">Allow</span>.
              </>,
            ]}
          />
          <p className="text-caption">
            Easiest on a computer at claude.ai. Once it’s added, it works in the Claude phone app too. This page updates
            when you come back.
          </p>
        </>
      ),
    },
    answers: {
      summary: missing ? `${missing} still missing` : 'All saved',
      body: (
        <>
          <p>
            Job forms ask things like whether you can work here. Claude only uses the answers you save, and never guesses.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {missing ? (
              <Badge variant="warning">{missing} still missing</Badge>
            ) : (
              <Badge variant="success">All saved</Badge>
            )}
            <Button variant="secondary" size="sm" onClick={() => navigate('/profile?tab=about#application-details')}>
              Open application details
            </Button>
          </div>
          <div className="space-y-2">
            <p>Or let your Claude ask you, one at a time:</p>
            <PromptBox text={ANSWERS_PROMPT} label="Copy the prompt for filling in your answers" />
          </div>
        </>
      ),
    },
    chrome: {
      summary: flags.chrome ? 'Done' : 'So Claude can fill in forms in your own browser.',
      body: (
        <>
          <SubSteps
            items={[
              <>
                Install{' '}
                <a
                  href={CHROME_WEB_STORE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-primary underline-offset-2 hover:underline"
                >
                  Claude in Chrome
                  <ExternalLink className="size-3.5" aria-hidden />
                  <span className="sr-only">(opens the Chrome Web Store)</span>
                </a>{' '}
                and sign in with your Claude account.
              </>,
              'In that Chrome, stay signed in to your email, so Claude can read the codes some sites send.',
              'Keep the computer on, with Chrome open, when Claude applies.',
            ]}
          />
          <ManualCheck id="claude-guide-chrome" checked={flags.chrome} onChange={(on) => setFlag('chrome', on)}>
            I’ve done this
          </ManualCheck>
        </>
      ),
    },
    daily: {
      summary:
        data.apply_via === 'server'
          ? 'jobwright applies for you, so there’s nothing to set up.'
          : flags.daily
            ? applyAt
              ? `Your Claude applies after ${applyAt}`
              : 'Set up'
            : 'Your Claude applies to your daily picks by itself.',
      body:
        data.apply_via === 'server' ? (
          <p>jobwright’s server applies for you, so you don’t need a scheduled task in Claude.</p>
        ) : data.apply_via === 'off' ? (
          <p>
            Applying is turned off for you. To use it, choose <span className="text-foreground">My Claude</span> under
            “Who sends applications” below.
          </p>
        ) : data.apply_paused ? (
          <p>Applying is paused for you right now. Ask your jobwright admin to turn it back on.</p>
        ) : !pick.scheduled ? (
          <>
            <p>Daily picks aren’t scheduled for you yet. Ask your jobwright admin to turn them on.</p>
            <div className="space-y-2">
              <p>Until then, you can ask Claude to apply whenever you like:</p>
              <PromptBox text={THINGS_TO_ASK[2]} label="Copy the prompt for applying to your top pick" />
            </div>
          </>
        ) : (
          <>
            <DailyTimeline data={data} />
            <div className="space-y-2">
              <p>
                <span className="text-foreground">Set it up once:</span> in Claude, create a scheduled task that runs{' '}
                {everyDay}
                {taskAt ? (
                  <>
                    {' '}
                    at <span className="text-foreground tabular-nums">{taskAt}</span>
                  </>
                ) : (
                  ' after your skip time ends'
                )}
                , with this prompt:
              </p>
              <PromptBox text={DAILY_PROMPT} label="Copy the daily apply prompt" />
            </div>
            <p className="text-caption">
              If a site asks for a code, a CAPTCHA or an answer you haven’t saved, Claude leaves that job for you and says so
              in its summary.
              {data.apply_enabled ? '' : ' For now Claude fills in each form and leaves Submit to you.'}
            </p>
            <ManualCheck id="claude-guide-daily" checked={flags.daily} onChange={(on) => setFlag('daily', on)}>
              I’ve created the scheduled task
            </ManualCheck>
          </>
        ),
    },
  }

  return (
    <div>
      <SectionHeader
        title="Use jobwright from your Claude"
        description={
          current
            ? 'Four steps, about five minutes. Then your own Claude can find, tailor and apply for you every day.'
            : picksAt && applyAt && data.apply_via === 'connector'
              ? `You’re all set. Picks arrive at ${picksAt}, and your Claude applies after ${applyAt}.`
              : 'You’re all set.'
        }
        actions={
          <span className="text-caption text-muted-foreground tabular-nums" aria-live="polite">
            {doneCount} of {steps.length} done
          </span>
        }
      />
      <ol aria-label="Setup steps" className="surface divide-y divide-border rounded-lg border">
        {steps.map((s, i) => (
          <GuideStep
            key={s.id}
            index={i + 1}
            total={steps.length}
            title={STEP_TITLE[s.id]}
            done={s.done}
            current={s.id === current}
            open={isOpen(s.id)}
            onToggle={() => toggle(s.id)}
            summary={stepBody[s.id].summary}
          >
            {stepBody[s.id].body}
          </GuideStep>
        ))}
      </ol>

      <SectionHeader title="Things to ask" description="Copy one, then paste it into a new chat in Claude." />
      <ul className="surface divide-y divide-border rounded-lg border">
        {THINGS_TO_ASK.map((p) => (
          <li key={p} className="flex items-center gap-3 py-2.5 pr-2.5 pl-4">
            <span className="min-w-0 flex-1 text-body text-foreground">{p}</span>
            <CopyButton text={p} label={`Copy: ${p}`} compact className="max-sm:w-11 max-sm:px-0" />
          </li>
        ))}
      </ul>

      <SectionHeader
        as="h3"
        title="Connected Claude apps"
        description="Each one can act only on this profile. Disconnecting ends its access right away."
      />
      {data.clients.length ? (
        <ul className="surface divide-y divide-border rounded-lg border">
          {data.clients.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 py-3 pr-2.5 pl-4">
              <div className="min-w-0 flex-1">
                <p className="text-label text-foreground">
                  {c.client_name} <span className="font-normal text-muted-foreground">({c.email})</span>
                </p>
                <p className="mt-0.5 text-caption text-muted-foreground">{describeClient(c)}</p>
              </div>
              <Button variant="destructive-ghost" size="sm" onClick={() => setRevoking(c)}>
                Disconnect
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-muted-foreground">No Claude is connected yet.</p>
      )}

      <SectionHeader as="h3" title="Who sends applications" description={via?.hint ?? ''} />
      <Segmented
        aria-label="Who sends applications"
        value={data.apply_via}
        disabled={saving}
        onValueChange={(v) => void chooseVia(v)}
        options={options.map((o) => ({
          value: o.value,
          label: o.label,
          disabled: o.value === 'server' && !data.can_choose_server,
        }))}
      />
      {data.apply_via === 'connector' ? (
        <p className="mt-3 text-caption text-muted-foreground">
          {data.apply_enabled
            ? 'Claude may press Submit on jobs that meet your minimum score. Everything else it fills, then you submit.'
            : 'Claude fills each form and stops on the review page; you check it and press Submit yourself.'}{' '}
          Your daily limit, saved answers and the “skip” replies to your picks still apply.
        </p>
      ) : null}

      <ConfirmAction
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title="Disconnect this Claude?"
        description={`${revoking?.client_name ?? 'Claude'} will lose access to jobwright right away. You can connect it again later.`}
        confirmLabel="Disconnect"
        destructive
        onConfirm={async () => {
          if (!revoking) return
          try {
            setData(await revokeConnectedClaude(revoking.id))
            toast.success('Disconnected')
          } catch (e) {
            toast.error(errorMessage(e))
            throw e
          }
        }}
      />
    </div>
  )
}

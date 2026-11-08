import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { FormField } from '@/components/FormField'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
import { useAutosave } from '@/components/profile/useAutosave'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getAnswers,
  getApplyStatus,
  putAnswers,
  type AnswerFieldSpec,
  type ApplicationAnswers,
  type ApplyStatus,
} from '@/lib/api'
import { errorMessage } from '@/lib/utils'

type Values = Record<string, string>

const NOT_SET = '__not_set__'

function statusLine(s: ApplyStatus): { text: string; tone: 'success' | 'warning' | 'secondary' } {
  if (s.kill_switch) return { text: 'Stopped for everyone by the operator', tone: 'warning' }
  if (s.apply_via === 'off') return { text: 'Off. Turn it on in Settings, Claude.', tone: 'secondary' }
  if (s.apply_via === 'connector') {
    if (s.apply_paused) return { text: `Paused: ${s.apply_paused_reason || 'paused'}`, tone: 'warning' }
    return {
      text: `Your own Claude applies (Settings, Claude): up to ${s.apply_daily_cap} a day, ${
        s.apply_enabled ? `submitting on its own for jobs scoring ${s.apply_min_score}+` : 'you press Submit'
      }.`,
      tone: 'success',
    }
  }
  if (!s.apply_enabled) return { text: 'Off. Ask the operator to turn on automatic applications.', tone: 'secondary' }
  if (s.apply_paused) return { text: `Paused: ${s.apply_paused_reason || 'paused'}`, tone: 'warning' }
  const when =
    s.apply_mode === 'veto'
      ? `posted in your WhatsApp group first, sent ${Math.round(s.apply_veto_minutes / 60)} h later unless you reply “skip”`
      : 'sent right after they are picked'
  return {
    text: `On: up to ${s.apply_daily_cap} a day for jobs scoring ${s.apply_min_score}+, ${when}.`,
    tone: 'success',
  }
}

function AnswerControl({
  spec,
  value,
  onChange,
}: {
  spec: AnswerFieldSpec
  value: string
  onChange: (v: string) => void
}) {
  if (spec.choices.length && spec.choices.length <= 3) {
    return (
      <Segmented
        aria-label={spec.label}
        value={value || NOT_SET}
        onValueChange={(v) => onChange(v === NOT_SET ? '' : v)}
        options={[
          ...spec.choices.map((c) => ({ value: c, label: c })),
          { value: NOT_SET, label: 'Not set' },
        ]}
      />
    )
  }
  return (
    <Input
      id={`answer-${spec.key}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={spec.attestation ? 'Write it exactly as it should be given' : 'Add your answer'}
    />
  )
}

/** Settings → Applications: the answers jobwright may give on application forms. */
export function ApplicationsTab() {
  const [data, setData] = useState<ApplicationAnswers | null>(null)
  const [status, setStatus] = useState<ApplyStatus | null>(null)
  const [values, setValues] = useState<Values>({})
  const dirty = useRef<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([getAnswers(), getApplyStatus()])
      .then(([a, s]) => {
        setData(a)
        setStatus(s)
        setValues(Object.fromEntries(Object.entries(a.answers).map(([k, e]) => [k, e.value])))
      })
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  const autosave = useAutosave(
    (next: Values) => {
      const changed: Record<string, string | null> = {}
      for (const key of dirty.current) changed[key] = next[key]?.trim() ? next[key] : null
      return putAnswers(changed)
    },
    {
      onSaved: (res) => {
        dirty.current.clear()
        setData(res)
      },
      onError: (e) => toast.error(errorMessage(e)),
    },
  )

  function patch(key: string, v: string) {
    const next = { ...values, [key]: v }
    dirty.current.add(key)
    setValues(next)
    autosave.schedule(next)
  }

  if (!data || !status) {
    return (
      <div className="space-y-field" aria-busy aria-label="Loading application answers">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-full" />
      </div>
    )
  }

  const line = statusLine(status)
  const attestations = data.fields.filter((f) => f.attestation)
  const common = data.fields.filter((f) => !f.attestation)
  const missing = new Set(data.missing)
  const customs = Object.values(data.custom)

  function field(spec: AnswerFieldSpec) {
    const isMissing = missing.has(spec.key) && !values[spec.key]?.trim()
    const entry = data!.answers[spec.key]
    return (
      <FormField
        key={spec.key}
        label={spec.label}
        htmlFor={`answer-${spec.key}`}
        optional={!spec.required}
        hint={spec.hint || (entry ? `Saved from ${entry.source}` : undefined)}
        labelAction={isMissing ? <Badge variant="warning">Needed</Badge> : undefined}
      >
        <AnswerControl spec={spec} value={values[spec.key] || ''} onChange={(v) => patch(spec.key, v)} />
      </FormField>
    )
  }

  return (
    <div>
      <SectionHeader
        title="Automatic applications"
        description="jobwright applies for you only with what you save here and your resume."
      />
      <p className="flex flex-wrap items-center gap-2 text-body text-muted-foreground">
        <Badge variant={line.tone}>{line.tone === 'success' ? 'On' : 'Off'}</Badge>
        {line.text}
      </p>

      <SectionHeader
        title="Application answers"
        description="Questions about work authorization, sponsorship, background, demographics, salary and start date are answered only from here. If one is missing, the job is skipped and you get the question in WhatsApp."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <div className="space-y-field">{attestations.map(field)}</div>

      <SectionHeader title="Contact and background" description="Facts forms often ask for." />
      <div className="space-y-field">{common.map(field)}</div>

      {customs.length ? (
        <>
          <SectionHeader title="Answers to specific questions" description="Saved from your WhatsApp replies." />
          <ul className="divide-y divide-border rounded-lg border border-border">
            {customs.map((c) => (
              <li key={c.question} className="px-4 py-3">
                <p className="text-label text-foreground">{c.question}</p>
                <p className="mt-0.5 text-body text-muted-foreground">{c.value}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  )
}

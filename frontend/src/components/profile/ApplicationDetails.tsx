import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { FormField } from '@/components/FormField'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
import { ClaudeQuestions } from '@/components/profile/ClaudeQuestions'
import { useAutosave } from '@/components/profile/useAutosave'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getAnswers,
  listPending,
  putAnswers,
  undoAnswer,
  type AnswerFieldSpec,
  type ApplicationAnswers,
  type PendingInput,
  type RecentAnswer,
} from '@/lib/api'
import { fieldsBySection, sourceLabel } from '@/lib/applicationDetails'
import { errorMessage } from '@/lib/utils'

type Values = Record<string, string>

const NOT_SET = '__not_set__'

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
        options={[...spec.choices.map((c) => ({ value: c, label: c })), { value: NOT_SET, label: 'Not set' }]}
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

function RecentStrip({ recent, onUndo }: { recent: RecentAnswer[]; onUndo: (r: RecentAnswer) => void }) {
  if (!recent.length) return null
  return (
    <section aria-labelledby="recent-by-claude" className="mb-6 rounded-lg border border-border bg-surface-muted/40">
      <h3 id="recent-by-claude" className="border-b border-border px-4 py-2 text-label text-foreground">
        Recently added by Claude
      </h3>
      <ul className="divide-y divide-border">
        {recent.map((r) => (
          <li key={r.key ?? r.question} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-caption text-muted-foreground">
                {r.label} · {sourceLabel(r.source)}
              </p>
              <p className="text-body text-foreground">
                {r.value}
                {r.previous_value ? (
                  <span className="text-caption text-muted-foreground"> (was {r.previous_value})</span>
                ) : null}
              </p>
            </div>
            <Button type="button" size="sm" variant="secondary" onClick={() => onUndo(r)}>
              Undo
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Settings → About you → Application details: every answer forms ask for, in one place. */
export function ApplicationDetails() {
  const [data, setData] = useState<ApplicationAnswers | null>(null)
  const [values, setValues] = useState<Values>({})
  const [pending, setPending] = useState<PendingInput[]>([])
  const dirty = useRef<Set<string>>(new Set())
  const location = useLocation()
  const loaded = data !== null

  // "Open application details" (Applications tab, WhatsApp link) lands here.
  useEffect(() => {
    if (loaded && location.hash === '#application-details' && new URLSearchParams(location.search).get('tab') === 'about') {
      requestAnimationFrame(() => document.getElementById('application-details')?.scrollIntoView())
    }
  }, [loaded, location.hash, location.search])

  function show(a: ApplicationAnswers) {
    setData(a)
    setValues(Object.fromEntries(Object.entries(a.answers).map(([k, e]) => [k, e.value])))
  }

  useEffect(() => {
    getAnswers()
      .then(show)
      .catch((e) => toast.error(errorMessage(e)))
    listPending('open')
      .then((r) => setPending(r.pending))
      .catch(() => setPending([]))
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

  function questionAnswered(id: string) {
    setPending((list) => list.filter((p) => p.id !== id))
    if (!dirty.current.size) getAnswers().then(show).catch(() => undefined)
  }

  async function undo(r: RecentAnswer) {
    try {
      show(await undoAnswer(r.key ? { key: r.key } : { question: r.question }))
      toast.success(r.previous_value ? `Put back “${r.previous_value}”.` : 'Removed.')
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  if (!data) {
    return (
      <div className="mt-section space-y-field" aria-busy aria-label="Loading application details">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-11 w-full" />
      </div>
    )
  }

  const missing = new Set(data.missing)
  const customs = Object.values(data.custom)

  function field(spec: AnswerFieldSpec) {
    const isMissing = missing.has(spec.key) && !values[spec.key]?.trim()
    const entry = data!.answers[spec.key]
    const label = entry ? entry.source_label || sourceLabel(entry.source) : undefined
    return (
      <FormField
        key={spec.key}
        label={spec.label}
        htmlFor={`answer-${spec.key}`}
        optional={!spec.required}
        hint={[spec.hint, label].filter(Boolean).join(' · ') || undefined}
        labelAction={isMissing ? <Badge variant="warning">Needed</Badge> : undefined}
      >
        <AnswerControl spec={spec} value={values[spec.key] || ''} onChange={(v) => patch(spec.key, v)} />
      </FormField>
    )
  }

  return (
    <section id="application-details" aria-labelledby="application-details-title" className="scroll-mt-4">
      <SectionHeader
        id="application-details-title"
        title="Application details"
        description="What application forms ask. Your Claude fills forms only from these and your resume; work eligibility, pay and diversity answers come only from here."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <ClaudeQuestions pending={pending} onAnswered={questionAnswered} />
      <RecentStrip recent={data.recent ?? []} onUndo={(r) => void undo(r)} />

      {fieldsBySection(data).map((s) => {
        const other = s.id === 'other'
        if (!s.fields.length && !(other && customs.length)) return null
        return (
          <div key={s.id}>
            <SectionHeader as="h3" title={s.title} />
            <div className="space-y-field">{s.fields.map(field)}</div>
            {other && customs.length ? (
              <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
                {customs.map((c) => (
                  <li key={c.question} className="px-4 py-3">
                    <p className="text-label text-foreground">{c.question}</p>
                    <p className="mt-0.5 text-body text-muted-foreground">{c.value}</p>
                    <p className="mt-0.5 text-caption text-subtle-foreground">
                      {c.source_label || sourceLabel(c.source)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      })}
    </section>
  )
}

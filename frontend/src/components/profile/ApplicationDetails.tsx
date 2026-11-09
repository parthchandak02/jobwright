import { useEffect, useRef, useState } from 'react'
import { FileText, MessageCircle } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { FieldHint } from '@/components/FieldHint'
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
import { fieldsBySection, isYesNo, shortLabel, sourceLabel } from '@/lib/applicationDetails'
import { cn, errorMessage } from '@/lib/utils'

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
      placeholder="Add your answer"
    />
  )
}

/** Where an answer came from, as an icon (typed by you shows nothing). The words are in the tooltip. */
function SourceMark({ source, label }: { source?: string | null; label?: string }) {
  const text = label || sourceLabel(source)
  const Icon = source === 'resume' ? FileText : source === 'told_claude' || source === 'connector' ? MessageCircle : null
  if (!Icon) return null
  return (
    <span title={text} className="inline-flex text-subtle-foreground">
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">{text}</span>
    </span>
  )
}

/** Yes / No as two small buttons; tapping the chosen one again clears it. */
function YesNo({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div role="group" aria-label={label} className="inline-flex shrink-0 rounded-md bg-surface-muted p-[3px]">
      {['Yes', 'No'].map((c) => {
        const on = value === c
        return (
          <button
            key={c}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? '' : c)}
            className={cn(
              'h-10 min-w-12 rounded-[calc(var(--radius)-4px)] px-3 text-label text-muted-foreground transition-colors duration-(--dur-1) hover:text-foreground md:h-8',
              on && 'bg-pill-active text-foreground shadow-e1',
            )}
          >
            {c}
          </button>
        )
      })}
    </div>
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
  const [openSections, setOpenSections] = useState<Set<string>>(() => new Set())
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

  function meta(spec: AnswerFieldSpec) {
    const isMissing = missing.has(spec.key) && !values[spec.key]?.trim()
    const entry = data!.answers[spec.key]
    const short = shortLabel(spec)
    // ⓘ only when there's a hint to give (with the question's full wording).
    const help = [short !== spec.label && spec.hint ? spec.label : null, spec.hint].filter(Boolean).join('. ')
    return { isMissing, entry, short, help }
  }

  /** Amber dot = still needed (the section title counts them). */
  function needed(isMissing: boolean) {
    return isMissing ? (
      <span title="Needed" className="inline-flex size-2 shrink-0 rounded-full bg-warning">
        <span className="sr-only">Needed</span>
      </span>
    ) : null
  }

  function field(spec: AnswerFieldSpec) {
    const { isMissing, entry, short, help } = meta(spec)
    return (
      <FormField
        key={spec.key}
        label={
          <span className="inline-flex items-center gap-1.5">
            {needed(isMissing)}
            {short}
            {entry ? <SourceMark source={entry.source} label={entry.source_label} /> : null}
          </span>
        }
        htmlFor={`answer-${spec.key}`}
        optional={!spec.required}
        help={help || undefined}
      >
        <AnswerControl spec={spec} value={values[spec.key] || ''} onChange={(v) => patch(spec.key, v)} />
      </FormField>
    )
  }

  function yesNoRow(spec: AnswerFieldSpec) {
    const { isMissing, entry, short, help } = meta(spec)
    return (
      <li key={spec.key} className="flex min-h-14 items-center gap-3 px-4 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          {needed(isMissing)}
          <span className="text-label text-foreground">{short}</span>
          {help ? <FieldHint text={help} /> : null}
          {entry ? <SourceMark source={entry.source} label={entry.source_label} /> : null}
        </div>
        <YesNo label={short} value={values[spec.key] || ''} onChange={(v) => patch(spec.key, v)} />
      </li>
    )
  }

  return (
    <section id="application-details" aria-labelledby="application-details-title" className="mt-section scroll-mt-4">
      <SectionHeader
        id="application-details-title"
        title="Application details"
        help="What application forms ask. Your Claude fills forms only from these and your resume; work eligibility, pay and diversity answers come only from here. A page icon means the answer came from your resume, a speech bubble that you told Claude. An amber dot marks an answer still needed. Tap a chosen Yes or No again to clear it."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <ClaudeQuestions pending={pending} onAnswered={questionAnswered} />
      <RecentStrip recent={data.recent ?? []} onUndo={(r) => void undo(r)} />

      {fieldsBySection(data).map((s) => {
        const other = s.id === 'other'
        if (!s.fields.length && !(other && customs.length)) return null
        return (
          <div key={s.id} className="mt-section">
            <SectionHeader
              as="h3"
              title={s.title}
              actions={(() => {
                const n = s.fields.filter((f) => missing.has(f.key) && !values[f.key]?.trim()).length
                return n ? <Badge variant="warning">{n} needed</Badge> : null
              })()}
            />
            {s.fields.some(isYesNo) ? (
              <ul className="mb-field divide-y divide-border rounded-lg border border-border bg-surface">
                {s.fields.filter(isYesNo).map(yesNoRow)}
              </ul>
            ) : null}
            {(() => {
              const text = s.fields.filter((f) => !isYesNo(f))
              // Progressive disclosure: empty optional fields wait behind "More" until wanted.
              const tucked = text.filter((f) => !f.required && !values[f.key]?.trim() && !data!.answers[f.key])
              const open = openSections.has(s.id) || tucked.length < 2
              const shown = open ? text : text.filter((f) => !tucked.includes(f))
              return (
                <>
                  <div className="space-y-field">{shown.map(field)}</div>
                  {!open ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="mt-2 -ml-2 text-muted-foreground"
                      onClick={() => setOpenSections((o) => new Set(o).add(s.id))}
                    >
                      More ({tucked.length}): {tucked.map((f) => shortLabel(f)).join(', ')}
                    </Button>
                  ) : null}
                </>
              )
            })()}
            {other && customs.length ? (
              <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
                {customs.map((c) => (
                  <li key={c.question} className="px-4 py-3">
                    <p className="flex items-center gap-1.5 text-label text-foreground">{c.question}</p>
                    <p className="mt-0.5 text-body text-muted-foreground">{c.value}</p>
                    <SourceMark source={c.source} label={c.source_label} />
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

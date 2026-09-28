import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { MoreHorizontal, Plus, Trash2, X } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { Dealbreaker, MatchCriteria } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  value: MatchCriteria
  onChange: (next: MatchCriteria) => void
  compact?: boolean
}

const INLINE_FIELD =
  'border-transparent bg-transparent px-2 hover:border-border hover:bg-surface focus-visible:border-primary focus-visible:bg-surface'

const INLINE_TEXTAREA = { minHeight: 'calc(1lh + 0.75rem + 2px)' }

const THRESHOLDS: { value: number; label: string }[] = [
  { value: 5, label: '5 and up · more jobs, looser fit' },
  { value: 6, label: '6 and up · a few more jobs' },
  { value: 7, label: '7 and up · recommended' },
  { value: 8, label: '8 and up · fewer, closer fits' },
  { value: 9, label: '9 and up · only the closest fits' },
]

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 32) || 'rule'
}

function Group({ title, description, compact, children }: { title: string; description?: string; compact?: boolean; children: ReactNode }) {
  if (compact) return <div className="space-y-field">{children}</div>
  return (
    <section className="mt-section first:mt-8">
      <h3 className="text-subheading text-foreground">{title}</h3>
      {description ? <p className="mt-1 text-caption text-muted-foreground">{description}</p> : null}
      <div className="mt-4 space-y-field">{children}</div>
    </section>
  )
}

/** Edit the rules the scorer uses: what fits, what is a hard no, where, what level. */
export function CriteriaEditor({ value, onChange, compact }: Props) {
  const patch = (p: Partial<MatchCriteria>) => onChange({ ...value, ...p })
  const threshold = THRESHOLDS.some((t) => t.value === value.notify_threshold) ? value.notify_threshold : 7

  return (
    <div className={compact ? 'space-y-field' : undefined}>
      <Group compact={compact} title="What fits" description="The scorer reads these first for every job.">
        <FormField label="What you’re looking for" hint="A sentence or two, in your own words.">
          <Textarea
            value={value.summary}
            rows={3}
            onChange={(e) => patch({ summary: e.target.value })}
            placeholder="Describe the roles you want"
          />
        </FormField>

        <FormField label="Good-fit roles" hint="Kinds of roles that should score high.">
          <ChipInput
            values={value.must_haves}
            onChange={(must_haves) => patch({ must_haves })}
            placeholder="Add a kind of role"
            addLabel="Add a good-fit role"
          />
        </FormField>

        <FormField label="Seniority" hint="The level that fits your experience.">
          <Textarea
            value={value.seniority}
            rows={1}
            onChange={(e) => patch({ seniority: e.target.value })}
            placeholder="Describe the level you want"
          />
        </FormField>

        {!compact ? (
          <FormField label="Pluses" optional hint="Things that make a job better, but aren’t required.">
            <PhraseList
              values={value.nice_to_haves}
              onChange={(nice_to_haves) => patch({ nice_to_haves })}
              placeholder="Add a plus"
              itemLabel="plus"
            />
          </FormField>
        ) : null}
      </Group>

      <Group
        compact={compact}
        title="Dealbreakers"
        description="If a job’s main work matches one of these, it scores 3 or lower and is never sent to you. Passing mentions don’t count."
      >
        <DealbreakerList
          value={value.dealbreakers}
          onChange={(dealbreakers) => patch({ dealbreakers })}
          showLabel={compact}
        />
      </Group>

      <Group compact={compact} title="Location" description="Where you can work. Jobs elsewhere score lower.">
        <FormField label="Places that work">
          <ChipInput
            values={value.locations_ok}
            onChange={(locations_ok) => patch({ locations_ok })}
            placeholder="Add a place"
            addLabel="Add a place that works"
          />
        </FormField>
        <FormField label="Places that don’t" optional>
          <ChipInput
            values={value.locations_not_ok}
            onChange={(locations_not_ok) => patch({ locations_not_ok })}
            placeholder="Add a place to avoid"
            addLabel="Add a place that doesn’t work"
            tone="--destructive"
          />
        </FormField>
      </Group>

      <Group compact={compact} title="Pay and daily list">
        <div className="grid gap-field sm:grid-cols-2">
          <FormField label="Pay floor" htmlFor="criteria-min-salary" optional hint="Per year. Only used when a posting lists pay.">
            <div className="relative">
              <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-body text-muted-foreground" aria-hidden>
                $
              </span>
              <Input
                id="criteria-min-salary"
                inputMode="numeric"
                value={value.min_salary != null ? value.min_salary.toLocaleString('en-US') : ''}
                onChange={(e) => {
                  const digits = e.target.value.replace(/\D/g, '')
                  patch({ min_salary: digits ? Number(digits) : null })
                }}
                placeholder="No minimum"
                className="pl-7 tabular-nums"
              />
            </div>
          </FormField>
          <FormField label="Send me jobs scored" htmlFor="criteria-threshold" hint="Your daily list only includes jobs at or above this score.">
            <Select value={String(threshold)} onValueChange={(v) => patch({ notify_threshold: Number(v) })}>
              <SelectTrigger id="criteria-threshold" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {THRESHOLDS.map((t) => (
                  <SelectItem key={t.value} value={String(t.value)}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
        </div>
      </Group>
    </div>
  )
}

function RowMenu({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" size="icon-sm" variant="ghost" className="text-muted-foreground" aria-label={`Options for ${label}`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem variant="destructive" onSelect={onRemove}>
          <Trash2 />
          Remove
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function DealbreakerList({
  value,
  onChange,
  showLabel,
}: {
  value: Dealbreaker[]
  onChange: (next: Dealbreaker[]) => void
  showLabel?: boolean
}) {
  const [focusIndex, setFocusIndex] = useState<number | null>(null)
  const refs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (focusIndex == null) return
    refs.current[focusIndex]?.focus()
    setFocusIndex(null)
  }, [focusIndex])

  function setDeal(i: number, p: Partial<Dealbreaker>) {
    onChange(value.map((d, idx) => (idx === i ? { ...d, ...p } : d)))
  }

  return (
    <div className="space-y-3">
      {showLabel ? (
        <div>
          <p className="text-label text-foreground">Dealbreakers</p>
          <p className="mt-1 text-caption text-muted-foreground">Jobs whose main work matches one of these are never sent to you.</p>
        </div>
      ) : null}
      {value.length ? (
        <ul className="divide-y divide-border rounded-lg border bg-surface">
          {value.map((d, i) => (
            <li key={`${d.id}-${i}`} className="space-y-0.5 px-2 py-2 md:px-2.5">
              <div className="flex items-center gap-1">
                <Input
                  ref={(el) => {
                    refs.current[i] = el
                  }}
                  value={d.label}
                  aria-label="Dealbreaker name"
                  onChange={(e) => setDeal(i, { label: e.target.value, id: d.id || slugify(e.target.value) })}
                  placeholder="Name this dealbreaker"
                  className={cn(INLINE_FIELD, 'h-10 flex-1 text-label md:h-9')}
                />
                <RowMenu
                  label={d.label || 'dealbreaker'}
                  onRemove={() => onChange(value.filter((_, idx) => idx !== i))}
                />
              </div>
              <Textarea
                value={d.description}
                rows={1}
                aria-label={`When is a job a clear no${d.label ? ` (${d.label})` : ''}`}
                onChange={(e) => setDeal(i, { description: e.target.value })}
                placeholder="Describe when a job is a clear no"
                style={INLINE_TEXTAREA}
                className={cn(INLINE_FIELD, 'py-1.5 text-muted-foreground focus-visible:text-foreground')}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-lg bg-surface-muted px-4 py-3 text-caption text-muted-foreground">
          No dealbreakers yet. Add the kinds of work you never want to see.
        </p>
      )}
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={() => {
          onChange([...value, { id: `rule_${value.length + 1}`, label: '', description: '' }])
          setFocusIndex(value.length)
        }}
      >
        <Plus /> Add a dealbreaker
      </Button>
    </div>
  )
}

function PhraseList({
  values,
  onChange,
  placeholder,
  itemLabel,
  id,
  'aria-describedby': describedBy,
}: {
  values: string[]
  onChange: (next: string[]) => void
  placeholder: string
  itemLabel: string
  id?: string
  'aria-describedby'?: string
}) {
  const [draft, setDraft] = useState('')

  function add() {
    const v = draft.trim()
    if (v && !values.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...values, v])
    setDraft('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  return (
    <div className="space-y-2">
      {values.length ? (
        <ul className="divide-y divide-border rounded-lg border bg-surface">
          {values.map((v, i) => (
            <li key={i} className="flex items-start gap-1 py-1.5 pr-1.5 pl-2">
              <Textarea
                value={v}
                rows={1}
                aria-label={`${itemLabel} ${i + 1}`}
                onChange={(e) => onChange(values.map((x, idx) => (idx === i ? e.target.value : x)))}
                onBlur={() => {
                  if (!v.trim()) onChange(values.filter((_, idx) => idx !== i))
                }}
                style={INLINE_TEXTAREA}
                className={cn(INLINE_FIELD, 'flex-1 py-1.5')}
              />
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                className="mt-0.5 text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${itemLabel} ${i + 1}`}
                onClick={() => onChange(values.filter((_, idx) => idx !== i))}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="relative">
        <Plus
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground"
          aria-hidden
        />
        <Input
          id={id}
          aria-describedby={describedBy}
          value={draft}
          placeholder={placeholder}
          aria-label={placeholder}
          enterKeyHint="done"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={add}
          className="pl-9"
        />
      </div>
    </div>
  )
}

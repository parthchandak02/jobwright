import { useState, type KeyboardEvent } from 'react'
import { ArrowRightLeft, ChevronDown, Plus, X } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { cn } from '@/lib/utils'

export type QueryEntry = { query: string; tier: number }

type Tier = 'daily' | 'weekly'

type Props = {
  queries: QueryEntry[]
  onChange: (next: QueryEntry[]) => void
  className?: string
  /** `chips`: two chip groups. `list`: one row per title with a Daily/Weekly switch. `auto`: list above 12 titles. */
  mode?: 'auto' | 'chips' | 'list'
  id?: string
  'aria-describedby'?: string
}

const LIST_THRESHOLD = 12
const LIST_COLLAPSE = 8

const TIER_OPTIONS: { value: Tier; label: string }[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
]

function tierOf(entry: QueryEntry): Tier {
  return (entry.tier || 1) <= 1 ? 'daily' : 'weekly'
}

function tierNumber(tier: Tier): number {
  return tier === 'daily' ? 1 : 2
}

function normalize(queries: QueryEntry[]): QueryEntry[] {
  return queries.map((q) => ({ query: q.query, tier: tierNumber(tierOf(q)) }))
}

function addQueries(queries: QueryEntry[], raws: string[], tier: Tier): QueryEntry[] {
  const next = [...queries]
  for (const raw of raws) {
    const query = raw.trim()
    if (query && !next.some((q) => q.query.toLowerCase() === query.toLowerCase())) {
      next.push({ query, tier: tierNumber(tier) })
    }
  }
  return next
}

export function QueryChipInput({ queries, onChange, className, mode = 'auto', id, 'aria-describedby': describedBy }: Props) {
  const asList = mode === 'list' || (mode === 'auto' && queries.length > LIST_THRESHOLD)
  const emit = (next: QueryEntry[]) => onChange(normalize(next))
  return asList ? (
    <KeywordList queries={queries} onChange={emit} className={className} id={id} describedBy={describedBy} />
  ) : (
    <KeywordChips queries={queries} onChange={emit} className={className} id={id} describedBy={describedBy} />
  )
}

type InnerProps = {
  queries: QueryEntry[]
  onChange: (next: QueryEntry[]) => void
  className?: string
  id?: string
  describedBy?: string
}

function KeywordChips({ queries, onChange, className, id, describedBy }: InnerProps) {
  const groups: { tier: Tier; title: string; placeholder: string }[] = [
    { tier: 'daily', title: 'Every morning', placeholder: 'Add a job title' },
    { tier: 'weekly', title: 'Once a week', placeholder: 'Add a job title to search weekly' },
  ]

  function setGroup(tier: Tier, values: string[]) {
    const wanted = new Set(values.map((v) => v.toLowerCase()))
    const kept = queries.filter((q) => tierOf(q) !== tier || wanted.has(q.query.toLowerCase()))
    onChange(addQueries(kept, values, tier))
  }

  function move(query: string, to: Tier) {
    onChange(queries.map((q) => (q.query === query ? { ...q, tier: tierNumber(to) } : q)))
  }

  return (
    <div className={cn('space-y-4', className)}>
      {groups.map((g, i) => {
        const values = queries.filter((q) => tierOf(q) === g.tier).map((q) => q.query)
        const other: Tier = g.tier === 'daily' ? 'weekly' : 'daily'
        return (
          <div key={g.tier} className="space-y-2">
            <p className="text-caption font-medium text-muted-foreground">{g.title}</p>
            <ChipInput
              id={i === 0 ? id : undefined}
              aria-describedby={describedBy}
              values={values}
              onChange={(next) => setGroup(g.tier, next)}
              placeholder={g.placeholder}
              addLabel={`Add a job title (${g.title.toLowerCase()})`}
              renderActions={(value) => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      aria-label={`Options for ${value}`}
                      className="relative -mr-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors duration-(--dur-1) after:absolute after:-inset-2 hover:bg-foreground/10 hover:text-foreground focus-visible:outline-offset-0 data-[state=open]:bg-foreground/10"
                    >
                      <ChevronDown className="size-3" aria-hidden />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem onSelect={() => move(value, other)}>
                      <ArrowRightLeft />
                      {other === 'weekly' ? 'Search once a week instead' : 'Search every morning instead'}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            />
          </div>
        )
      })}
    </div>
  )
}

function KeywordList({ queries, onChange, className, id, describedBy }: InnerProps) {
  const [expanded, setExpanded] = useState(false)
  const [draft, setDraft] = useState('')
  const collapsed = !expanded && queries.length > LIST_COLLAPSE
  const shown = collapsed ? queries.slice(0, LIST_COLLAPSE) : queries

  function add() {
    const next = addQueries(queries, draft.split(/\n/), 'daily')
    if (next.length !== queries.length) onChange(next)
    setDraft('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      <ul className="divide-y divide-border overflow-hidden rounded-lg border bg-surface">
        {shown.map((entry, index) => (
          <li key={`${entry.query}-${index}`} className="flex min-h-12 items-center gap-2 py-1.5 pr-1.5 pl-3.5 md:min-h-11 md:gap-3">
            <span className="min-w-0 flex-1 text-body break-words text-foreground">{entry.query}</span>
            <Segmented
              size="sm"
              aria-label={`How often to search ${entry.query}`}
              value={tierOf(entry)}
              options={TIER_OPTIONS}
              onValueChange={(tier) =>
                onChange(queries.map((q, i) => (i === index ? { ...q, tier: tierNumber(tier) } : q)))
              }
            />
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              className="text-muted-foreground hover:text-foreground"
              aria-label={`Remove ${entry.query}`}
              onClick={() => onChange(queries.filter((_, i) => i !== index))}
            >
              <X />
            </Button>
          </li>
        ))}
        {queries.length > LIST_COLLAPSE ? (
          <li>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setExpanded((v) => !v)}
              className="flex h-11 w-full items-center gap-1.5 px-3.5 text-label text-primary transition-colors duration-(--dur-1) hover:bg-surface-muted"
            >
              <ChevronDown className={cn('size-4 transition-transform duration-(--dur-2)', expanded && 'rotate-180')} aria-hidden />
              {expanded ? 'Show fewer' : `Show all ${queries.length} titles`}
            </button>
          </li>
        ) : null}
      </ul>
      <div className="relative">
        <Plus
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground"
          aria-hidden
        />
        <Input
          id={id}
          aria-describedby={describedBy}
          type="text"
          value={draft}
          placeholder="Add a job title"
          aria-label="Add a job title"
          enterKeyHint="done"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          className="pl-9"
        />
      </div>
    </div>
  )
}

import { useCallback, useState, type KeyboardEvent } from 'react'
import { Chip } from '@/components/Chip'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type QueryEntry = { query: string; tier: number }

type Props = {
  queries: QueryEntry[]
  onChange: (next: QueryEntry[]) => void
  className?: string
}

function normalizeQuery(raw: string): string {
  return raw.trim()
}

function isDuplicate(queries: QueryEntry[], candidate: string): boolean {
  const lower = candidate.toLowerCase()
  return queries.some((q) => q.query.toLowerCase() === lower)
}

function isDaily(tier: number | undefined): boolean {
  return (tier || 1) <= 1
}

function emit(daily: QueryEntry[], weekly: QueryEntry[]): QueryEntry[] {
  return [
    ...daily.map((q) => ({ query: q.query, tier: 1 })),
    ...weekly.map((q) => ({ query: q.query, tier: 2 })),
  ]
}

type BucketProps = {
  label: string
  hint: string
  entries: QueryEntry[]
  tone: string
  moveLabel: string
  moveTitle: string
  placeholder: string
  onRemove: (index: number) => void
  onMove: (index: number) => void
  onAdd: (raw: string) => void
}

function QueryBucket({
  label,
  hint,
  entries,
  tone,
  moveLabel,
  moveTitle,
  placeholder,
  onRemove,
  onMove,
  onAdd,
}: BucketProps) {
  const [draft, setDraft] = useState('')

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    onAdd(draft)
    setDraft('')
  }

  return (
    <div className="space-y-1.5">
      <div>
        <p className="text-xs font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      {entries.length > 0 && (
        <div className="job-card-chips">
          {entries.map((entry, index) => (
            <Chip
              key={`${entry.query}-${index}`}
              tone={tone}
              onRemove={() => onRemove(index)}
              removeLabel={entry.query}
            >
              <span className="flex min-w-0 items-center gap-1">
                <span className="truncate">{entry.query}</span>
                <button
                  type="button"
                  className="shrink-0 rounded-sm border border-current/30 bg-current/10 px-1 py-px text-[10px] font-semibold leading-none text-current/80 transition-colors hover:bg-current/20 hover:text-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                  title={moveTitle}
                  aria-label={`${moveTitle} ${entry.query}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onMove(index)
                  }}
                >
                  {moveLabel}
                </button>
              </span>
            </Chip>
          ))}
        </div>
      )}
      <Input
        type="text"
        value={draft}
        placeholder={placeholder}
        aria-label={label}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
      />
    </div>
  )
}

export function QueryChipInput({ queries, onChange, className }: Props) {
  const daily = queries.filter((q) => isDaily(q.tier))
  const weekly = queries.filter((q) => !isDaily(q.tier))

  const addTo = useCallback(
    (bucket: 'daily' | 'weekly', raw: string) => {
      const query = normalizeQuery(raw)
      if (!query || isDuplicate(queries, query)) return
      const nextDaily = bucket === 'daily' ? [...daily, { query, tier: 1 }] : daily
      const nextWeekly = bucket === 'weekly' ? [...weekly, { query, tier: 2 }] : weekly
      onChange(emit(nextDaily, nextWeekly))
    },
    [daily, onChange, queries, weekly],
  )

  const removeFrom = useCallback(
    (bucket: 'daily' | 'weekly', index: number) => {
      const nextDaily = bucket === 'daily' ? daily.filter((_, i) => i !== index) : daily
      const nextWeekly = bucket === 'weekly' ? weekly.filter((_, i) => i !== index) : weekly
      onChange(emit(nextDaily, nextWeekly))
    },
    [daily, onChange, weekly],
  )

  const moveToWeekly = useCallback(
    (index: number) => {
      const item = daily[index]
      if (!item) return
      onChange(emit(daily.filter((_, i) => i !== index), [...weekly, item]))
    },
    [daily, onChange, weekly],
  )

  const moveToDaily = useCallback(
    (index: number) => {
      const item = weekly[index]
      if (!item) return
      onChange(emit([...daily, item], weekly.filter((_, i) => i !== index)))
    },
    [daily, onChange, weekly],
  )

  return (
    <div className={cn('space-y-4', className)}>
      <QueryBucket
        label="Daily"
        hint="Every Auto Search and the morning brief."
        entries={daily}
        tone="--query-daily"
        moveLabel="Weekly"
        moveTitle="Move to weekly"
        placeholder="social impact program manager"
        onRemove={(index) => removeFrom('daily', index)}
        onMove={moveToWeekly}
        onAdd={(raw) => addTo('daily', raw)}
      />
      <QueryBucket
        label="Weekly"
        hint="Extra keywords on the weekly deep crawl only."
        entries={weekly}
        tone="--query-weekly"
        moveLabel="Daily"
        moveTitle="Move to daily"
        placeholder="foundation program officer"
        onRemove={(index) => removeFrom('weekly', index)}
        onMove={moveToDaily}
        onAdd={(raw) => addTo('weekly', raw)}
      />
    </div>
  )
}

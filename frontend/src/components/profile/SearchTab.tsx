import { useId, useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { BOARDS, BoardToggles, DEFAULT_BOARDS } from '@/components/BoardToggles'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { LocationChipInput } from '@/components/LocationChipInput'
import { QueryChipInput } from '@/components/QueryChipInput'
import { SaveStatus } from '@/components/SaveStatus'
import { SectionHeader } from '@/components/SectionHeader'
import { useAutosave } from '@/components/profile/useAutosave'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiFetch, type SettingsSearches } from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

const DEFAULT_HOURS_OLD = 72
const DEFAULT_RESULTS_PER_SITE = 100

export function searchesPayload(s: SettingsSearches) {
  return {
    queries: s.queries
      .map((q) => ({ query: q.query.trim(), tier: (q.tier || 1) >= 2 ? 2 : 1 }))
      .filter((q) => q.query),
    locations: s.locations
      .map((l) => {
        const location = l.location.trim()
        return { location, remote: location.toLowerCase() === 'remote' }
      })
      .filter((l) => l.location),
    boards: (s.boards || []).map((b) => b.trim()).filter(Boolean),
    exclude_titles: (s.exclude_titles || []).map((t) => t.trim()).filter(Boolean),
    min_salary: s.min_salary,
    hours_old: s.hours_old,
    results_per_site: s.results_per_site,
  }
}

function saveSearches(s: SettingsSearches) {
  return apiFetch('/settings/searches', { method: 'PUT', body: JSON.stringify(searchesPayload(s)) })
}

function toNumber(raw: string): number | null {
  const digits = raw.replace(/\D/g, '')
  return digits ? Number(digits) : null
}

function boardNames(ids: readonly string[]): string {
  const names = ids.map((id) => BOARDS.find((b) => b.id === id)?.label ?? id)
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

type Props = {
  searches: SettingsSearches
  onChange: (next: SettingsSearches) => void
}

export function SearchTab({ searches, onChange }: Props) {
  const autosave = useAutosave(saveSearches, { onError: (e) => toast.error(errorMessage(e)) })
  const [advanced, setAdvanced] = useState(false)
  const advancedId = useId()

  function patch(values: Partial<SettingsSearches>) {
    const next = { ...searches, ...values }
    onChange(next)
    autosave.schedule(next)
  }

  const boards = searches.boards || []
  const usingDefaultBoards = boards.length === 0
  const hours = searches.hours_old ?? DEFAULT_HOURS_OLD
  const perSite = searches.results_per_site ?? DEFAULT_RESULTS_PER_SITE
  const advancedSummary = [
    searches.min_salary ? `Pay from $${searches.min_salary.toLocaleString('en-US')}` : 'No pay minimum',
    `posted in the last ${hours} hours`,
    `${perSite} results per board`,
  ].join(' · ')

  return (
    <div>
      <SectionHeader
        title="What to search for"
        description="We look for these on job boards every morning. Changes save automatically."
        actions={<SaveStatus state={autosave.state} savedAt={autosave.savedAt} onRetry={autosave.retry} />}
      />
      <div className="space-y-field">
        <FormField
          label="Job titles"
          hint="Daily titles are searched every morning. Weekly titles get a deeper search once a week."
        >
          <QueryChipInput queries={searches.queries} onChange={(queries) => patch({ queries })} />
        </FormField>
        <FormField label="Where" hint="Cities to search. Add Remote to include remote jobs.">
          <LocationChipInput locations={searches.locations} onChange={(locations) => patch({ locations })} />
        </FormField>
      </div>

      <SectionHeader title="Skip these jobs" description="Jobs that match are dropped before we score them." />
      <FormField label="Titles containing" hint="Any job whose title includes one of these words or phrases is skipped.">
        <ChipInput
          values={searches.exclude_titles || []}
          onChange={(exclude_titles) => patch({ exclude_titles })}
          placeholder="Add a word or phrase"
          addLabel="Add a title to skip"
          tone="--destructive"
          collapseAfter={12}
        />
      </FormField>

      <SectionHeader title="Job boards" description="The sites we search." />
      <BoardToggles value={boards} onChange={(next) => patch({ boards: next })} aria-describedby={`${advancedId}-boards`} />
      <p id={`${advancedId}-boards`} className="mt-2.5 flex flex-wrap items-center gap-x-2 text-caption text-muted-foreground">
        {usingDefaultBoards ? (
          <>Using the recommended boards: {boardNames(DEFAULT_BOARDS)}.</>
        ) : (
          <>
            <span>
              Searching {boards.length} of {BOARDS.length} boards.
            </span>
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-caption"
              onClick={() => patch({ boards: [] })}
            >
              Use recommended boards
            </Button>
          </>
        )}
      </p>

      <div className="mt-section rounded-lg border bg-surface">
        <button
          type="button"
          aria-expanded={advanced}
          aria-controls={advancedId}
          onClick={() => setAdvanced((v) => !v)}
          className="flex w-full items-start gap-3 rounded-lg px-4 py-3.5 text-left transition-colors duration-(--dur-1) hover:bg-surface-muted/60 focus-visible:outline-offset-0"
        >
          <ChevronRight
            className={cn('mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-2)', advanced && 'rotate-90')}
            aria-hidden
          />
          <span className="min-w-0 flex-1">
            <span className="block text-label text-foreground">Advanced</span>
            {!advanced ? <span className="mt-0.5 block text-caption text-muted-foreground">{advancedSummary}</span> : null}
          </span>
        </button>
        {advanced ? (
          <div id={advancedId} className="grid gap-field border-t px-4 pt-4 pb-5 sm:grid-cols-3 sm:gap-4">
            <NumberField
              id="search-min-salary"
              label="Skip pay under"
              prefix="$"
              value={searches.min_salary}
              placeholder="No minimum"
              hint="Per year. Jobs that don’t list pay are kept."
              onChange={(min_salary) => patch({ min_salary })}
              format
            />
            <NumberField
              id="search-hours-old"
              label="Posted in the last"
              suffix="hours"
              value={searches.hours_old}
              placeholder={`Default: ${DEFAULT_HOURS_OLD}`}
              hint="Older postings are skipped."
              onChange={(hours_old) => patch({ hours_old })}
            />
            <NumberField
              id="search-results-per-site"
              label="Results per board"
              value={searches.results_per_site}
              placeholder={`Default: ${DEFAULT_RESULTS_PER_SITE}`}
              hint="For each title and place."
              onChange={(results_per_site) => patch({ results_per_site })}
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}

function NumberField({
  id,
  label,
  value,
  placeholder,
  hint,
  prefix,
  suffix,
  format,
  onChange,
}: {
  id: string
  label: ReactNode
  value: number | null
  placeholder: string
  hint: string
  prefix?: string
  suffix?: string
  format?: boolean
  onChange: (next: number | null) => void
}) {
  return (
    <FormField label={label} htmlFor={id} hint={hint}>
      <div className="relative">
        {prefix ? (
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-body text-muted-foreground" aria-hidden>
            {prefix}
          </span>
        ) : null}
        <Input
          id={id}
          inputMode="numeric"
          value={value == null ? '' : format ? value.toLocaleString('en-US') : String(value)}
          placeholder={placeholder}
          onChange={(e) => onChange(toNumber(e.target.value))}
          className={cn('tabular-nums', prefix && 'pl-7', suffix && 'pr-16')}
        />
        {suffix ? (
          <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-caption text-muted-foreground" aria-hidden>
            {suffix}
          </span>
        ) : null}
      </div>
    </FormField>
  )
}

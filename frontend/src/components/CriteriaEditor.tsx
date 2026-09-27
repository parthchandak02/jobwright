import { Plus, Trash2 } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { Dealbreaker, MatchCriteria } from '@/lib/api'

type Props = {
  value: MatchCriteria
  onChange: (next: MatchCriteria) => void
  compact?: boolean
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 32) || 'rule'
}

/** Edit the rules the scorer uses: what fits, what is a hard no, where, what level. */
export function CriteriaEditor({ value, onChange, compact }: Props) {
  const patch = (p: Partial<MatchCriteria>) => onChange({ ...value, ...p })

  function setDeal(i: number, p: Partial<Dealbreaker>) {
    const next = value.dealbreakers.map((d, idx) => (idx === i ? { ...d, ...p } : d))
    patch({ dealbreakers: next })
  }

  return (
    <div className="space-y-5">
      <FormField label="What you’re looking for" hint="Plain words. The scorer reads this first for every job.">
        <Textarea
          value={value.summary}
          rows={compact ? 3 : 4}
          onChange={(e) => patch({ summary: e.target.value })}
          placeholder="e.g. Program roles at education nonprofits and foundations, manager to director level…"
        />
      </FormField>

      <FormField label="Good-fit role types" hint="Kinds of roles that should score high.">
        <ChipInput
          values={value.must_haves}
          onChange={(must_haves) => patch({ must_haves })}
          placeholder="Foundation program officer, CSR program manager…"
          addLabel="Add role type"
          tone="--stage-prepare"
        />
      </FormField>

      <div className="space-y-2">
        <FormField
          label="Dealbreakers"
          hint="A job whose MAIN work matches one of these is capped at 3 and never sent to you. Passing mentions don't count."
        >
          <div className="space-y-2">
            {value.dealbreakers.map((d, i) => (
              <div key={`${d.id}-${i}`} className="grid gap-2 rounded-lg border border-border/60 p-2 sm:grid-cols-[12rem_1fr_auto]">
                <Input
                  value={d.label}
                  aria-label="Dealbreaker name"
                  onChange={(e) => setDeal(i, { label: e.target.value, id: d.id || slugify(e.target.value) })}
                  placeholder="Short name"
                  className="h-8"
                />
                <Input
                  value={d.description}
                  aria-label="Dealbreaker description"
                  onChange={(e) => setDeal(i, { description: e.target.value })}
                  placeholder="When is a job a clear no?"
                  className="h-8"
                />
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Remove ${d.label || 'dealbreaker'}`}
                  onClick={() => patch({ dealbreakers: value.dealbreakers.filter((_, idx) => idx !== i) })}
                >
                  <Trash2 />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                patch({
                  dealbreakers: [...value.dealbreakers, { id: `rule_${value.dealbreakers.length + 1}`, label: '', description: '' }],
                })
              }
            >
              <Plus /> Add dealbreaker
            </Button>
          </div>
        </FormField>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="Locations that work">
          <ChipInput
            values={value.locations_ok}
            onChange={(locations_ok) => patch({ locations_ok })}
            placeholder="Bay Area, Remote in the US…"
            addLabel="Add location"
          />
        </FormField>
        <FormField label="Locations that don’t">
          <ChipInput
            values={value.locations_not_ok}
            onChange={(locations_not_ok) => patch({ locations_not_ok })}
            placeholder="Onsite elsewhere, outside the US…"
            addLabel="Add location"
            tone="--destructive"
          />
        </FormField>
      </div>

      <FormField label="Seniority" hint="What level fits your experience.">
        <Textarea
          value={value.seniority}
          rows={2}
          onChange={(e) => patch({ seniority: e.target.value })}
          placeholder="e.g. Manager to director; not VP or C-suite at large organizations."
        />
      </FormField>

      {!compact ? (
        <FormField label="Pluses" hint="Things that make a good job better, but aren't required.">
          <ChipInput
            values={value.nice_to_haves}
            onChange={(nice_to_haves) => patch({ nice_to_haves })}
            placeholder="Education mission, hybrid…"
            addLabel="Add plus"
          />
        </FormField>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Pay floor (USD / year)" hint="Only applies when a posting lists pay.">
          <Input
            inputMode="numeric"
            value={value.min_salary ?? ''}
            onChange={(e) => patch({ min_salary: e.target.value ? Number(e.target.value.replace(/\D/g, '')) : null })}
            className="h-8"
          />
        </FormField>
        <FormField label="Send me jobs scored at least" hint="Your daily WhatsApp list only includes jobs at or above this score.">
          <select
            value={value.notify_threshold}
            onChange={(e) => patch({ notify_threshold: Number(e.target.value) })}
            className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {[5, 6, 7, 8, 9].map((n) => (
              <option key={n} value={n}>
                {n} {n === 7 ? '(default)' : n >= 8 ? '(fewer, stricter)' : '(more, looser)'}
              </option>
            ))}
          </select>
        </FormField>
      </div>
    </div>
  )
}

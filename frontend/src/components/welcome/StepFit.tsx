import { ArrowLeft, Check, Loader2, MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { SectionHeader } from '@/components/SectionHeader'
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
import type { Dealbreaker, MatchCriteria, OnboardingDraft } from '@/lib/api'
import { Disclosure, MutedList } from './parts'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  draft: OnboardingDraft
  onDraft: (d: OnboardingDraft) => void
  busy: boolean
  onBack: () => void
  onContinue: () => void
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 32) || 'rule'
}

const CUTOFFS: { value: number; label: string }[] = [
  { value: 5, label: '5 or higher: more jobs, looser fit' },
  { value: 6, label: '6 or higher' },
  { value: 7, label: '7 or higher: recommended' },
  { value: 8, label: '8 or higher' },
  { value: 9, label: '9 or higher: fewest jobs, strongest fit' },
]

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

function DealbreakerRow({
  rule,
  onChange,
  onRemove,
}: {
  rule: Dealbreaker
  onChange: (p: Partial<Dealbreaker>) => void
  onRemove: () => void
}) {
  const name = rule.label || 'this dealbreaker'
  return (
    <li className="p-3 md:p-4">
      <div className="flex items-center gap-1">
        <Input
          value={rule.label}
          aria-label="Dealbreaker name"
          placeholder="Name this dealbreaker"
          onChange={(e) => onChange({ label: e.target.value, id: rule.id || slugify(e.target.value) })}
          className="-ml-2 h-10 border-transparent bg-transparent px-2 font-medium hover:border-border-strong md:h-9"
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" size="icon-sm" variant="ghost" aria-label={`More for ${name}`}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem variant="destructive" onSelect={onRemove}>
              <Trash2 /> Remove
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <Textarea
        rows={1}
        value={rule.description}
        aria-label={`When ${name} rules a job out`}
        placeholder="Describe when a job is a clear no"
        onChange={(e) => onChange({ description: e.target.value })}
        className="mt-1.5"
      />
    </li>
  )
}

export function StepFit({ draft, onDraft, busy, onBack, onContinue }: Props) {
  const c = draft.criteria
  const patch = (p: Partial<MatchCriteria>) => onDraft({ ...draft, criteria: { ...c, ...p } })
  const setDeal = (i: number, p: Partial<Dealbreaker>) =>
    patch({ dealbreakers: c.dealbreakers.map((d, idx) => (idx === i ? { ...d, ...p } : d)) })
  const avoid = draft.profile.job_preferences.avoid_roles

  const moreSummary = [
    `${c.notify_threshold}+ only`,
    c.min_salary ? `${usd.format(c.min_salary)} floor` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <WelcomeStep
      title="How we judge fit"
      description="Every new job is scored from 1 to 10 against these. Only strong matches reach your daily list."
      back={
        <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={busy}>
          <ArrowLeft /> Back
        </Button>
      }
      actions={
        <Button type="button" size="sm" onClick={onContinue} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <Check />}
          Save and continue
        </Button>
      }
    >
      <SectionHeader title="What fits you" />
      <div className="space-y-field">
        <FormField label="In your own words" hint="We read this first for every job.">
          <Textarea
            rows={3}
            value={c.summary}
            onChange={(e) => patch({ summary: e.target.value })}
            placeholder="Describe the roles, level and kind of organization you want"
          />
        </FormField>
        <FormField label="Good-fit role types" hint="Kinds of roles that should score high.">
          <ChipInput
            values={c.must_haves}
            onChange={(must_haves) => patch({ must_haves })}
            placeholder="Add a role type"
            collapseAfter={8}
          />
        </FormField>
      </div>

      <SectionHeader
        title="What rules a job out"
        description="If a job’s main work matches a dealbreaker, it scores 3 or less and is never sent to you. Passing mentions don’t count."
      />
      <div className="space-y-field">
        <div>
          {c.dealbreakers.length ? (
            <MutedList>
              {c.dealbreakers.map((d, i) => (
                <DealbreakerRow
                  key={`${d.id}-${i}`}
                  rule={d}
                  onChange={(p) => setDeal(i, p)}
                  onRemove={() => patch({ dealbreakers: c.dealbreakers.filter((_, idx) => idx !== i) })}
                />
              ))}
            </MutedList>
          ) : (
            <p className="text-caption text-muted-foreground">No dealbreakers yet.</p>
          )}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="mt-3"
            onClick={() =>
              patch({
                dealbreakers: [...c.dealbreakers, { id: `rule_${c.dealbreakers.length + 1}`, label: '', description: '' }],
              })
            }
          >
            <Plus /> Add a dealbreaker
          </Button>
        </div>
        <FormField label="Roles you don’t want" hint="Kinds of work you’d rather not do.">
          <ChipInput
            values={avoid}
            onChange={(avoid_roles) =>
              onDraft({
                ...draft,
                profile: { ...draft.profile, job_preferences: { ...draft.profile.job_preferences, avoid_roles } },
              })
            }
            placeholder="Add a role type"
            tone="--destructive"
            collapseAfter={8}
          />
        </FormField>
      </div>

      <div className="mt-section border-t pt-4">
        <Disclosure title="Location, level and pay" summary={moreSummary}>
          <div className="space-y-field">
            <FormField label="Locations that work">
              <ChipInput
                values={c.locations_ok}
                onChange={(locations_ok) => patch({ locations_ok })}
                placeholder="Add a location"
              />
            </FormField>
            <FormField label="Locations that don’t">
              <ChipInput
                values={c.locations_not_ok}
                onChange={(locations_not_ok) => patch({ locations_not_ok })}
                placeholder="Add a location"
                tone="--destructive"
              />
            </FormField>
            <FormField label="Level" hint="What level fits your experience.">
              <Textarea
                rows={2}
                value={c.seniority}
                onChange={(e) => patch({ seniority: e.target.value })}
                placeholder="Describe the levels you’d consider"
              />
            </FormField>
            <FormField label="Lowest yearly pay (USD)" optional hint="Only used when a job lists its pay.">
              <Input
                inputMode="numeric"
                value={c.min_salary ?? ''}
                placeholder="Enter an amount"
                onChange={(e) => {
                  const digits = e.target.value.replace(/\D/g, '')
                  patch({ min_salary: digits ? Number(digits) : null })
                }}
                className="md:max-w-60"
              />
            </FormField>
            <FormField label="Send me jobs scored" hint="Your daily list only includes jobs at or above this score.">
              <Select value={String(c.notify_threshold)} onValueChange={(v) => patch({ notify_threshold: Number(v) })}>
                <SelectTrigger className="md:max-w-80">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CUTOFFS.map((o) => (
                    <SelectItem key={o.value} value={String(o.value)}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
          </div>
        </Disclosure>
      </div>
    </WelcomeStep>
  )
}

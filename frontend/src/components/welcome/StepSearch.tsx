import { ArrowLeft, ArrowRight, ChevronDown } from 'lucide-react'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'
import type { LocationEntry, OnboardingDraft, QueryEntry } from '@/lib/api'
import { Disclosure } from './parts'
import { WelcomeStep } from './WelcomeShell'

type Props = {
  draft: OnboardingDraft
  onDraft: (d: OnboardingDraft) => void
  onBack: () => void
  onContinue: () => void
}

const isDaily = (q: QueryEntry) => (q.tier || 1) <= 1

function MoveMenu({ label, action, onMove }: { label: string; action: string; onMove: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="relative -mr-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors duration-(--dur-1) after:absolute after:-inset-2 hover:bg-foreground/10 hover:text-foreground focus-visible:outline-offset-0"
        aria-label={`Options for ${label}`}
      >
        <ChevronDown className="size-3" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem onSelect={onMove}>{action}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function StepSearch({ draft, onDraft, onBack, onContinue }: Props) {
  const queries = draft.searches.queries
  const daily = queries.filter(isDaily).map((q) => q.query)
  const weekly = queries.filter((q) => !isDaily(q)).map((q) => q.query)

  const setQueries = (d: string[], w: string[]) =>
    onDraft({
      ...draft,
      searches: {
        ...draft.searches,
        queries: [...d.map((query) => ({ query, tier: 1 })), ...w.map((query) => ({ query, tier: 2 }))],
      },
    })

  const addUnique = (list: string[], other: string[]) => {
    const seen = new Set(other.map((v) => v.toLowerCase()))
    return list.filter((v) => !seen.has(v.toLowerCase()))
  }

  const setLocations = (names: string[]) =>
    onDraft({
      ...draft,
      searches: {
        ...draft.searches,
        locations: names.map(
          (location): LocationEntry =>
            draft.searches.locations.find((l) => l.location === location) ?? {
              location,
              remote: location.trim().toLowerCase() === 'remote',
            },
        ),
      },
    })

  const role = draft.profile.experience.target_role || ''

  return (
    <WelcomeStep
      title="Here’s what we’ll search for"
      description="We drafted this from your resume. Change anything that’s off; you can edit it later too."
      back={
        <Button type="button" size="sm" variant="ghost" onClick={onBack}>
          <ArrowLeft /> Back
        </Button>
      }
      actions={
        <Button type="button" size="sm" disabled={!queries.length} onClick={onContinue}>
          Continue <ArrowRight />
        </Button>
      }
    >
      <div className="space-y-field">
        <FormField label="The job you’re after" hint="One or two sentences, in your own words.">
          <Textarea
            rows={2}
            value={role}
            placeholder="Describe the role and kind of organization"
            onChange={(e) =>
              onDraft({
                ...draft,
                profile: { ...draft.profile, experience: { ...draft.profile.experience, target_role: e.target.value } },
              })
            }
          />
        </FormField>

        <FormField
          label="Job titles to search every morning"
          hint={
            daily.length || weekly.length
              ? 'Press Enter after each one. Use the arrow on a title to search it weekly instead.'
              : 'Add at least one job title. Press Enter after each one.'
          }
          error={!queries.length ? 'Add at least one job title to continue.' : undefined}
        >
          <ChipInput
            values={daily}
            onChange={(d) => setQueries(d, addUnique(weekly, d))}
            placeholder="Add a job title"
            collapseAfter={12}
            renderActions={(value, i) => (
              <MoveMenu
                label={value}
                action="Search weekly instead"
                onMove={() => setQueries(daily.filter((_, idx) => idx !== i), [...weekly, value])}
              />
            )}
          />
        </FormField>

        <Disclosure
          title="Weekly searches"
          summary={weekly.length ? `${weekly.length} ${weekly.length === 1 ? 'title' : 'titles'}` : 'None yet'}
          defaultOpen={false}
        >
          <FormField
            label="Job titles to search once a week"
            hint="A deeper search once a week. Good for rarer or broader titles."
          >
            <ChipInput
              values={weekly}
              onChange={(w) => setQueries(addUnique(daily, w), w)}
              placeholder="Add a job title"
              renderActions={(value, i) => (
                <MoveMenu
                  label={value}
                  action="Search every morning instead"
                  onMove={() => setQueries([...daily, value], weekly.filter((_, idx) => idx !== i))}
                />
              )}
            />
          </FormField>
        </Disclosure>

        <FormField label="Where to look" hint="Add “Remote” to include remote jobs.">
          <ChipInput
            values={draft.searches.locations.map((l) => l.location)}
            onChange={setLocations}
            placeholder="Add a city, region or “Remote”"
          />
        </FormField>
      </div>
    </WelcomeStep>
  )
}

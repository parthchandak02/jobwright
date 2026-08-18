import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { FormField } from '@/components/FormField'
import { SectionLabel } from '@/components/SectionLabel'
import { UserSwitcher } from '@/components/UserSwitcher'
import {
  apiFetch,
  Profile,
  QueryEntry,
  SettingsData,
  SettingsProfile,
  SettingsSearches,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  profile: Profile | null
  onBack: () => void
  onProfileChanged: () => void
}

const PANEL = 'space-y-4 rounded-lg border border-border/60 bg-muted/10 p-4'

/** Textarea that edits a string[] as one item per line. Empties trimmed on save. */
function LinesField({
  label,
  htmlFor,
  value,
  onChange,
  placeholder,
  rows = 4,
}: {
  label: string
  htmlFor: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  rows?: number
}) {
  return (
    <FormField label={label} htmlFor={htmlFor}>
      <Textarea
        id={htmlFor}
        rows={rows}
        value={(value || []).join('\n')}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value.split('\n'))}
      />
      <p className="text-xs text-muted-foreground">One per line.</p>
    </FormField>
  )
}

export function ProfilePage({ profile, onBack, onProfileChanged }: Props) {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await apiFetch<SettingsData>('/settings'))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function patchProfile<K extends keyof SettingsProfile>(
    section: K,
    values: Partial<SettingsProfile[K]>,
  ) {
    setData((d) =>
      d
        ? { ...d, profile: { ...d.profile, [section]: { ...d.profile[section], ...values } } }
        : d,
    )
  }

  function patchSearches(values: Partial<SettingsSearches>) {
    setData((d) => (d ? { ...d, searches: { ...d.searches, ...values } } : d))
  }

  async function save(section: string, path: string, body: unknown) {
    setSaving(section)
    try {
      await apiFetch(path, { method: 'PUT', body: JSON.stringify(body) })
      toast.success('Saved. Applies on the next run.')
      onProfileChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(null)
    }
  }

  function saveProfile() {
    if (!data) return
    const p = data.profile
    const prefs = p.job_preferences || {}
    void save('profile', '/settings/profile', {
      personal: p.personal,
      compensation: p.compensation,
      experience: p.experience,
      job_preferences: {
        ...prefs,
        ideal_roles: (prefs.ideal_roles || []).map((s) => s.trim()).filter(Boolean),
        avoid_roles: (prefs.avoid_roles || []).map((s) => s.trim()).filter(Boolean),
      },
    })
  }

  function saveSearches() {
    if (!data) return
    const s = data.searches
    void save('searches', '/settings/searches', {
      queries: s.queries
        .map((q) => ({ query: q.query.trim(), tier: q.tier || 1 }))
        .filter((q) => q.query),
      locations: s.locations
        .map((l) => ({ location: l.location.trim(), remote: !!l.remote }))
        .filter((l) => l.location),
      boards: (s.boards || []).map((b) => b.trim()).filter(Boolean),
      exclude_titles: (s.exclude_titles || []).map((t) => t.trim()).filter(Boolean),
      min_salary: s.min_salary,
      hours_old: s.hours_old,
      results_per_site: s.results_per_site,
    })
  }

  function saveResume() {
    if (!data) return
    void save('resume', '/settings/resume', { text: data.resume })
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className={cn('sticky top-0 z-20', APP_SHELL_HEADER)}>
        <Button type="button" size="icon-sm" variant="ghost" onClick={onBack} aria-label="Back to board">
          <ArrowLeft />
        </Button>
        <h1 className="min-w-0 flex-1 text-base font-semibold tracking-tight">Profile</h1>
        <div className="w-40">
          <UserSwitcher profile={profile} onChanged={onProfileChanged} />
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-4">
        {loading || !data ? (
          <p className="text-sm text-muted-foreground">Loading profile…</p>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            <p className="text-sm text-muted-foreground">
              Edits drive tomorrow&apos;s job discovery and scoring.
            </p>
            {/* Identity + fit guidance -> profile.json */}
            <section className={PANEL}>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel>About you</SectionLabel>
                <Button size="sm" onClick={saveProfile} disabled={saving === 'profile'}>
                  <Save /> Save
                </Button>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FormField label="Full name" htmlFor="full_name">
                  <Input
                    id="full_name"
                    value={data.profile.personal.full_name || ''}
                    onChange={(e) => patchProfile('personal', { full_name: e.target.value })}
                  />
                </FormField>
                <FormField label="Email" htmlFor="email">
                  <Input
                    id="email"
                    value={data.profile.personal.email || ''}
                    onChange={(e) => patchProfile('personal', { email: e.target.value })}
                  />
                </FormField>
                <FormField label="Phone" htmlFor="phone">
                  <Input
                    id="phone"
                    value={data.profile.personal.phone || ''}
                    onChange={(e) => patchProfile('personal', { phone: e.target.value })}
                  />
                </FormField>
                <FormField label="LinkedIn URL" htmlFor="linkedin_url">
                  <Input
                    id="linkedin_url"
                    value={data.profile.personal.linkedin_url || ''}
                    onChange={(e) => patchProfile('personal', { linkedin_url: e.target.value })}
                  />
                </FormField>
                <FormField label="City" htmlFor="city">
                  <Input
                    id="city"
                    value={data.profile.personal.city || ''}
                    onChange={(e) => patchProfile('personal', { city: e.target.value })}
                  />
                </FormField>
                <FormField label="State / Province" htmlFor="province_state">
                  <Input
                    id="province_state"
                    value={data.profile.personal.province_state || ''}
                    onChange={(e) =>
                      patchProfile('personal', { province_state: e.target.value })
                    }
                  />
                </FormField>
              </div>

              <FormField label="Target role" htmlFor="target_role">
                <Textarea
                  id="target_role"
                  rows={2}
                  value={data.profile.experience.target_role || ''}
                  onChange={(e) => patchProfile('experience', { target_role: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">
                  Used by the scorer to judge fit.
                </p>
              </FormField>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FormField label="Years of experience" htmlFor="yoe">
                  <Input
                    id="yoe"
                    value={data.profile.experience.years_of_experience_total || ''}
                    onChange={(e) =>
                      patchProfile('experience', { years_of_experience_total: e.target.value })
                    }
                  />
                </FormField>
                <FormField label="Education" htmlFor="education_level">
                  <Input
                    id="education_level"
                    value={data.profile.experience.education_level || ''}
                    onChange={(e) =>
                      patchProfile('experience', { education_level: e.target.value })
                    }
                  />
                </FormField>
                <FormField label="Current title" htmlFor="current_job_title">
                  <Input
                    id="current_job_title"
                    value={data.profile.experience.current_job_title || ''}
                    onChange={(e) =>
                      patchProfile('experience', { current_job_title: e.target.value })
                    }
                  />
                </FormField>
                <FormField label="Current company" htmlFor="current_company">
                  <Input
                    id="current_company"
                    value={data.profile.experience.current_company || ''}
                    onChange={(e) =>
                      patchProfile('experience', { current_company: e.target.value })
                    }
                  />
                </FormField>
              </div>

              <FormField label="What you're seeking" htmlFor="seek">
                <Textarea
                  id="seek"
                  rows={2}
                  value={data.profile.job_preferences.seek || ''}
                  onChange={(e) => patchProfile('job_preferences', { seek: e.target.value })}
                />
              </FormField>
              <FormField label="Company types" htmlFor="company_types">
                <Textarea
                  id="company_types"
                  rows={2}
                  value={data.profile.job_preferences.company_types || ''}
                  onChange={(e) =>
                    patchProfile('job_preferences', { company_types: e.target.value })
                  }
                />
              </FormField>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <LinesField
                  label="Ideal roles"
                  htmlFor="ideal_roles"
                  value={data.profile.job_preferences.ideal_roles || []}
                  onChange={(v) => patchProfile('job_preferences', { ideal_roles: v })}
                  placeholder="Chief of Staff"
                />
                <LinesField
                  label="Roles to avoid"
                  htmlFor="avoid_roles"
                  value={data.profile.job_preferences.avoid_roles || []}
                  onChange={(v) => patchProfile('job_preferences', { avoid_roles: v })}
                  placeholder="Software engineer"
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <FormField label="Salary min (USD)" htmlFor="salary_min">
                  <Input
                    id="salary_min"
                    value={data.profile.compensation.salary_range_min || ''}
                    onChange={(e) =>
                      patchProfile('compensation', { salary_range_min: e.target.value })
                    }
                  />
                </FormField>
                <FormField label="Salary target (USD)" htmlFor="salary_expectation">
                  <Input
                    id="salary_expectation"
                    value={data.profile.compensation.salary_expectation || ''}
                    onChange={(e) =>
                      patchProfile('compensation', { salary_expectation: e.target.value })
                    }
                  />
                </FormField>
                <FormField label="Salary max (USD)" htmlFor="salary_max">
                  <Input
                    id="salary_max"
                    value={data.profile.compensation.salary_range_max || ''}
                    onChange={(e) =>
                      patchProfile('compensation', { salary_range_max: e.target.value })
                    }
                  />
                </FormField>
              </div>
            </section>

            {/* Search criteria -> searches.yaml */}
            <section className={PANEL}>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel>Search criteria</SectionLabel>
                <Button size="sm" onClick={saveSearches} disabled={saving === 'searches'}>
                  <Save /> Save
                </Button>
              </div>

              <FormField label="Search queries">
                <div className="space-y-2">
                  {data.searches.queries.map((q, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        value={q.query}
                        placeholder="chief of staff"
                        onChange={(e) => {
                          const next = [...data.searches.queries]
                          next[i] = { ...next[i], query: e.target.value }
                          patchSearches({ queries: next })
                        }}
                      />
                      <Select
                        value={String(q.tier || 1)}
                        onValueChange={(v) => {
                          const next = [...data.searches.queries]
                          next[i] = { ...next[i], tier: Number(v) }
                          patchSearches({ queries: next })
                        }}
                      >
                        <SelectTrigger className="w-24 shrink-0">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">Tier 1</SelectItem>
                          <SelectItem value="2">Tier 2</SelectItem>
                          <SelectItem value="3">Tier 3</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        aria-label="Remove query"
                        onClick={() =>
                          patchSearches({
                            queries: data.searches.queries.filter((_, j) => j !== i),
                          })
                        }
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
                      patchSearches({
                        queries: [...data.searches.queries, { query: '', tier: 1 } as QueryEntry],
                      })
                    }
                  >
                    <Plus /> Add query
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Tier 1 runs daily; tiers 2-3 run on the weekly deep crawl.
                  </p>
                </div>
              </FormField>

              <FormField label="Locations">
                <div className="space-y-2">
                  {data.searches.locations.map((l, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        value={l.location}
                        placeholder="San Francisco, CA"
                        onChange={(e) => {
                          const next = [...data.searches.locations]
                          next[i] = { ...next[i], location: e.target.value }
                          patchSearches({ locations: next })
                        }}
                      />
                      <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={!!l.remote}
                          onChange={(e) => {
                            const next = [...data.searches.locations]
                            next[i] = { ...next[i], remote: e.target.checked }
                            patchSearches({ locations: next })
                          }}
                        />
                        Remote
                      </label>
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        aria-label="Remove location"
                        onClick={() =>
                          patchSearches({
                            locations: data.searches.locations.filter((_, j) => j !== i),
                          })
                        }
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
                      patchSearches({
                        locations: [
                          ...data.searches.locations,
                          { location: '', remote: false },
                        ],
                      })
                    }
                  >
                    <Plus /> Add location
                  </Button>
                </div>
              </FormField>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <LinesField
                  label="Job boards"
                  htmlFor="boards"
                  value={data.searches.boards || []}
                  onChange={(v) => patchSearches({ boards: v })}
                  placeholder="indeed"
                  rows={3}
                />
                <LinesField
                  label="Exclude titles"
                  htmlFor="exclude_titles"
                  value={data.searches.exclude_titles || []}
                  onChange={(v) => patchSearches({ exclude_titles: v })}
                  placeholder="software engineer"
                  rows={3}
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <FormField label="Min salary (USD)" htmlFor="min_salary">
                  <Input
                    id="min_salary"
                    inputMode="numeric"
                    value={data.searches.min_salary ?? ''}
                    onChange={(e) =>
                      patchSearches({
                        min_salary: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </FormField>
                <FormField label="Freshness (hours)" htmlFor="hours_old">
                  <Input
                    id="hours_old"
                    inputMode="numeric"
                    value={data.searches.hours_old ?? ''}
                    onChange={(e) =>
                      patchSearches({
                        hours_old: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </FormField>
                <FormField label="Results per site" htmlFor="results_per_site">
                  <Input
                    id="results_per_site"
                    inputMode="numeric"
                    value={data.searches.results_per_site ?? ''}
                    onChange={(e) =>
                      patchSearches({
                        results_per_site: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </FormField>
              </div>
            </section>

            {/* Base resume -> resume/base.txt */}
            <section className={PANEL}>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel>Base resume</SectionLabel>
                <Button size="sm" onClick={saveResume} disabled={saving === 'resume'}>
                  <Save /> Save
                </Button>
              </div>
              <Textarea
                aria-label="Base resume text"
                rows={16}
                className="font-mono text-xs"
                value={data.resume}
                onChange={(e) => setData((d) => (d ? { ...d, resume: e.target.value } : d))}
              />
              <p className="text-xs text-muted-foreground">
                Plain text used to score fit and tailor each application.
              </p>
            </section>
          </div>
        )}
      </main>
    </div>
  )
}

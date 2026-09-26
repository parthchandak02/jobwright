import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Loader2, Save, Send, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { BoardToggles } from '@/components/BoardToggles'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { ChipInput } from '@/components/ChipInput'
import { CriteriaEditor } from '@/components/CriteriaEditor'
import { FormField } from '@/components/FormField'
import { LocationChipInput } from '@/components/LocationChipInput'
import { ProfileMaterials } from '@/components/ProfileMaterials'
import { ProfileSwitcher } from '@/components/ProfileSwitcher'
import { QueryChipInput } from '@/components/QueryChipInput'
import { SectionLabel } from '@/components/SectionLabel'
import { WhatsAppChatPicker } from '@/components/WhatsAppChatPicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  apiFetch,
  apiUpload,
  getCriteria,
  notifyWhatsApp,
  Profile,
  saveCriteria,
  SettingsData,
  SettingsSearches,
  suggestCriteria,
  updateProfile,
  type MatchCriteria,
} from '@/lib/api'
import { invalidateReasons } from '@/lib/reasons'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  profile: Profile | null
  onBack: () => void
  onProfileChanged: () => void
}

const SECTION = 'space-y-3 border-b border-border/50 pb-6 last:border-b-0 last:pb-0'
const SEARCH_SAVE_MS = 500

function searchesPayload(s: SettingsSearches) {
  return {
    queries: s.queries
      .map((q) => ({
        query: q.query.trim(),
        tier: (q.tier || 1) >= 2 ? 2 : 1,
      }))
      .filter((q) => q.query),
    locations: s.locations
      .map((l) => {
        const location = l.location.trim()
        return {
          location,
          remote: location.toLowerCase() === 'remote',
        }
      })
      .filter((l) => l.location),
    boards: (s.boards || []).map((b) => b.trim()).filter(Boolean),
    exclude_titles: (s.exclude_titles || []).map((t) => t.trim()).filter(Boolean),
    min_salary: s.min_salary,
    hours_old: s.hours_old,
    results_per_site: s.results_per_site,
  }
}

function cronToTime(cron: string | undefined): string {
  const parts = (cron || '0 7 * * *').trim().split(/\s+/)
  if (parts.length !== 5 || !/^\d+$/.test(parts[0]) || !/^\d+$/.test(parts[1])) return '07:00'
  return `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`
}

function RulesTab() {
  const [criteria, setCriteria] = useState<MatchCriteria | null>(null)
  const [derived, setDerived] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<null | 'save' | 'suggest'>(null)

  useEffect(() => {
    void getCriteria()
      .then((r) => {
        setCriteria(r.criteria)
        setDerived(r.derived)
      })
      .catch((e) => toast.error(errorMessage(e)))
  }, [])

  async function save() {
    if (!criteria) return
    setBusy('save')
    try {
      const r = await saveCriteria(criteria)
      setCriteria(r.criteria)
      setDerived(false)
      setDirty(false)
      invalidateReasons()
      toast.success('Saved. New jobs are scored with these rules; use Match quality → Rescore to re-check open jobs.')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  async function suggest() {
    setBusy('suggest')
    try {
      const r = await suggestCriteria()
      setCriteria(r.criteria)
      setDirty(true)
      toast.success(
        r.based_on_ratings
          ? `Drafted from your resume and ${r.based_on_ratings} ratings. Review, then save.`
          : 'Drafted from your resume. Review, then save.',
      )
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  if (!criteria) return <p className="text-sm text-muted-foreground">Loading…</p>
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionLabel hint="Every new job is judged against these rules plus your past ratings.">
          How jobs are scored
        </SectionLabel>
        <div className="flex gap-2">
          <Button size="sm" variant="ai" onClick={() => void suggest()} disabled={!!busy}>
            {busy === 'suggest' ? <Loader2 className="animate-spin" /> : <Sparkles />} Suggest from my ratings
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={!!busy || (!dirty && !derived)}>
            {busy === 'save' ? <Loader2 className="animate-spin" /> : <Save />} Save rules
          </Button>
        </div>
      </div>
      {derived ? (
        <p className="rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          These rules are filled in from your profile. Edit and save them, or let us suggest better ones from the jobs
          you’ve rated.
        </p>
      ) : null}
      <CriteriaEditor
        value={criteria}
        onChange={(next) => {
          setCriteria(next)
          setDirty(true)
        }}
      />
    </div>
  )
}

function WhatsAppTab({ profile, onSaved }: { profile: Profile | null; onSaved: () => void }) {
  const [target, setTarget] = useState(profile?.whatsapp_target || '')
  const [time, setTime] = useState(cronToTime(profile?.schedule))
  const [busy, setBusy] = useState<null | 'save' | 'send'>(null)

  useEffect(() => {
    setTarget(profile?.whatsapp_target || '')
    setTime(cronToTime(profile?.schedule))
  }, [profile?.whatsapp_target, profile?.schedule])

  async function save() {
    const [h, m] = time.split(':').map(Number)
    setBusy('save')
    try {
      const res = await updateProfile({ schedule: `${m} ${h} * * *`, whatsapp_target: target })
      if (res.cron_synced) toast.success('Saved. Your daily list is scheduled.')
      else toast.info(`Saved, but the daily schedule could not be updated: ${res.cron_error || 'unknown error'}`)
      onSaved()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  async function sendNow() {
    setBusy('send')
    try {
      const res = await notifyWhatsApp()
      if (res.skipped) toast.info(res.reason || 'Nothing new to send')
      else toast.success(`Sent ${res.sent} jobs to WhatsApp`)
      onSaved()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="max-w-2xl space-y-5">
      <SectionLabel hint="Once a day: search, score, then one WhatsApp message with your best new matches.">
        Daily WhatsApp list
      </SectionLabel>
      <FormField label="Send it to">
        <WhatsAppChatPicker value={target} onChange={setTarget} />
      </FormField>
      <FormField label={`Time${profile?.timezone ? ` (${profile.timezone})` : ''}`}>
        <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="w-40" />
      </FormField>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void save()} disabled={!!busy || !target}>
          {busy === 'save' ? <Loader2 className="animate-spin" /> : <Save />} Save
        </Button>
        <Button size="sm" variant="outline" onClick={() => void sendNow()} disabled={!!busy}>
          {busy === 'send' ? <Loader2 className="animate-spin" /> : <Send />} Send today’s list now
        </Button>
      </div>
    </div>
  )
}

const ABOUT_FIELDS: { key: string; label: string; placeholder?: string }[] = [
  { key: 'full_name', label: 'Full name' },
  { key: 'email', label: 'Email', placeholder: 'you@example.com' },
  { key: 'phone', label: 'Phone (with country code)', placeholder: '+1 415 555 0100' },
  { key: 'city', label: 'City' },
  { key: 'province_state', label: 'State' },
  { key: 'linkedin_url', label: 'LinkedIn URL' },
]

function AboutTab({ data, onSaved }: { data: SettingsData; onSaved: () => void }) {
  const [personal, setPersonal] = useState<Record<string, string>>(data.profile.personal || {})
  const [target, setTarget] = useState<string>(data.profile.experience?.target_role || '')
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try {
      await apiFetch('/settings/profile', {
        method: 'PUT',
        body: JSON.stringify({ personal, experience: { target_role: target } }),
      })
      toast.success('Saved')
      onSaved()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <SectionLabel hint="Used to find your WhatsApp chats and when writing materials.">About you</SectionLabel>
      <div className="grid gap-3 sm:grid-cols-2">
        {ABOUT_FIELDS.map((f) => (
          <FormField key={f.key} label={f.label}>
            <Input
              value={personal[f.key] || ''}
              placeholder={f.placeholder}
              onChange={(e) => setPersonal({ ...personal, [f.key]: e.target.value })}
              className="h-8"
            />
          </FormField>
        ))}
      </div>
      <FormField label="Target role" hint="One or two sentences on the roles you want.">
        <textarea
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </FormField>
      <Button size="sm" onClick={() => void save()} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Save />} Save
      </Button>
    </div>
  )
}

const PROFILE_TABS = ['search', 'rules', 'documents', 'whatsapp', 'about'] as const

export function ProfilePage({ profile, onBack, onProfileChanged }: Props) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const tabParam = params.get('tab')
  const tab = (PROFILE_TABS as readonly string[]).includes(tabParam || '') ? (tabParam as string) : 'search'
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [searchSaveState, setSearchSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const resumeFileRef = useRef<HTMLInputElement>(null)
  const coverFileRef = useRef<HTMLInputElement>(null)
  const skipSearchAutosave = useRef(true)
  const pendingSearches = useRef<SettingsSearches | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    skipSearchAutosave.current = true
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

  const persistSearches = useCallback(async (searches: SettingsSearches) => {
    setSaving('search')
    setSearchSaveState('saving')
    try {
      await apiFetch('/settings/searches', {
        method: 'PUT',
        body: JSON.stringify(searchesPayload(searches)),
      })
      setSearchSaveState('saved')
    } catch (e) {
      setSearchSaveState('idle')
      toast.error(errorMessage(e))
    } finally {
      setSaving((cur) => (cur === 'search' ? null : cur))
    }
  }, [])

  useEffect(() => {
    if (!data) return
    if (skipSearchAutosave.current) {
      skipSearchAutosave.current = false
      return
    }
    pendingSearches.current = data.searches
    setSearchSaveState('saving')
    const timer = window.setTimeout(() => {
      const next = pendingSearches.current
      pendingSearches.current = null
      if (next) void persistSearches(next)
    }, SEARCH_SAVE_MS)
    return () => window.clearTimeout(timer)
  }, [data?.searches, persistSearches])

  useEffect(() => {
    return () => {
      const leftover = pendingSearches.current
      if (!leftover) return
      pendingSearches.current = null
      void apiFetch('/settings/searches', {
        method: 'PUT',
        body: JSON.stringify(searchesPayload(leftover)),
      }).catch(() => undefined)
    }
  }, [])

  function patchSearches(values: Partial<SettingsSearches>) {
    setData((d) => (d ? { ...d, searches: { ...d.searches, ...values } } : d))
  }

  function uploadResumePdf(file: File | undefined) {
    if (!file) return
    setSaving('resume')
    void apiUpload('/settings/resume.pdf', file)
      .then(async () => {
        toast.success('Resume PDF saved.')
        await load()
        onProfileChanged()
      })
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => setSaving(null))
  }

  async function uploadCoverPdfs(files: FileList | File[] | undefined) {
    if (!files || files.length === 0) return
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) {
      toast.error('Upload PDF files.')
      return
    }
    setSaving('cover')
    try {
      for (const file of pdfs) {
        await apiUpload('/settings/cover-letters', file)
      }
      toast.success(
        pdfs.length === 1
          ? 'Cover letter PDF saved. Used on the next tailor.'
          : `${pdfs.length} cover letter PDFs saved. Used on the next tailor.`,
      )
      await load()
      onProfileChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(null)
    }
  }

  function removeCoverPdf(id: string) {
    setSaving('cover')
    void apiFetch(`/settings/cover-letters/${encodeURIComponent(id)}`, { method: 'DELETE' })
      .then(async () => {
        toast.success('Cover letter removed.')
        await load()
        onProfileChanged()
      })
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => setSaving(null))
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header
        className={cn(
          APP_SHELL_HEADER,
          'sticky top-0 z-20 grid grid-cols-[auto_1fr_auto] items-center',
        )}
      >
        <Button type="button" size="icon-sm" variant="ghost" onClick={onBack} aria-label="Back to board">
          <ArrowLeft />
        </Button>
        <h1 className="justify-self-center text-xs font-bold uppercase tracking-wider">
          {profile?.name || 'Profile'}
        </h1>
        <div className="justify-self-end">
          <ProfileSwitcher className="h-8 w-40" />
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        {loading || !data ? (
          <p className="text-sm text-muted-foreground">Loading profile…</p>
        ) : (
          <Tabs
            value={tab}
            onValueChange={(v) => navigate(`/profile?tab=${v}`, { replace: true })}
            className="mx-auto w-full max-w-6xl gap-5"
          >
            <TabsList className="max-w-full justify-start overflow-x-auto">
              <TabsTrigger value="search">Search</TabsTrigger>
              <TabsTrigger value="rules">Match rules</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
              <TabsTrigger value="about">About you</TabsTrigger>
            </TabsList>
            <TabsContent value="rules">
              <RulesTab />
            </TabsContent>
            <TabsContent value="whatsapp">
              <WhatsAppTab profile={profile} onSaved={onProfileChanged} />
            </TabsContent>
            <TabsContent value="about">
              <AboutTab data={data} onSaved={onProfileChanged} />
            </TabsContent>
            <TabsContent value="search" className="space-y-6">
            <section className={SECTION}>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel hint="Changes save as you edit. Next Auto Search uses the latest keywords and boards.">
                  Auto Search
                </SectionLabel>
                <p className="text-xs text-muted-foreground" aria-live="polite">
                  {searchSaveState === 'saving'
                    ? 'Saving…'
                    : searchSaveState === 'saved'
                      ? 'Saved'
                      : ''}
                </p>
              </div>

              <FormField
                label="Find jobs like this"
                hint="Daily keywords run on every Auto Search. Weekly keywords run on the deep crawl only. There is no third tier."
              >
                <QueryChipInput
                  queries={data.searches.queries}
                  onChange={(queries) => patchSearches({ queries })}
                />
              </FormField>

              <FormField
                label="Block titles"
                hint="If a job title contains one of these phrases, it is dropped before scoring."
              >
                <ChipInput
                  values={data.searches.exclude_titles || []}
                  onChange={(exclude_titles) => patchSearches({ exclude_titles })}
                  placeholder="software engineer, intern, account executive"
                  addLabel="Add blocked title"
                  tone="--destructive"
                />
              </FormField>

              <FormField
                label="Where to look"
                hint="Cities Auto Search queries. Add a chip named Remote for nationwide remote jobs."
              >
                <LocationChipInput
                  locations={data.searches.locations}
                  onChange={(locations) => patchSearches({ locations })}
                />
              </FormField>

              <FormField
                label="Job boards"
                hint="Sites Auto Search scrapes."
              >
                <BoardToggles
                  value={data.searches.boards || []}
                  onChange={(boards) => patchSearches({ boards })}
                />
              </FormField>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:items-start">
                <FormField
                  label="Drop below (USD)"
                  htmlFor="min_salary"
                  hint="If a posting lists pay below this, Auto Search drops it. Unknown salary is kept."
                >
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
                <FormField
                  label="Posted within (hours)"
                  htmlFor="hours_old"
                  hint="Auto Search only keeps jobs posted within this many hours."
                >
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
                <FormField
                  label="Results per site"
                  htmlFor="results_per_site"
                  hint="Max listings per board for each keyword and location pair."
                >
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

            </TabsContent>
            <TabsContent value="documents" className="space-y-6">
            <section className={SECTION}>
              <SectionLabel hint="Resume is used for scoring and tailoring. Cover letter PDFs are amalgamated when Auto Search writes materials. Auto Search does not search from these files.">
                Resume and cover letters
              </SectionLabel>
              <input
                ref={resumeFileRef}
                type="file"
                accept="application/pdf"
                className="sr-only"
                onChange={(e) => {
                  uploadResumePdf(e.target.files?.[0])
                  e.target.value = ''
                }}
              />
              <input
                ref={coverFileRef}
                type="file"
                accept="application/pdf"
                multiple
                className="sr-only"
                onChange={(e) => {
                  void uploadCoverPdfs(e.target.files ?? undefined)
                  e.target.value = ''
                }}
              />
              <ProfileMaterials
                resume={{
                  pdfUrl: data.has_resume_pdf
                    ? `/api/settings/resume.pdf?t=${data.resume_pdf_mtime ?? 0}`
                    : null,
                  markdown: data.resume_markdown,
                  replacing: saving === 'resume',
                  onReplace: () => resumeFileRef.current?.click(),
                }}
                examples={data.cover_letter_examples || []}
                uploading={saving === 'cover'}
                onAddCovers={() => coverFileRef.current?.click()}
                onRemoveCover={removeCoverPdf}
              />
            </section>
            </TabsContent>
          </Tabs>
        )}
      </main>
    </div>
  )
}

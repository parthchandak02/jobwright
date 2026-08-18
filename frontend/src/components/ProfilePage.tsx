import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Save } from 'lucide-react'
import { toast } from 'sonner'
import { BoardToggles } from '@/components/BoardToggles'
import { APP_SHELL_HEADER } from '@/components/BrandLogo'
import { ChipInput } from '@/components/ChipInput'
import { FormField } from '@/components/FormField'
import { LocationChipInput } from '@/components/LocationChipInput'
import { ProfileMaterials } from '@/components/ProfileMaterials'
import { QueryChipInput } from '@/components/QueryChipInput'
import { SectionLabel } from '@/components/SectionLabel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { UserSwitcher } from '@/components/UserSwitcher'
import {
  apiFetch,
  apiUpload,
  Profile,
  SettingsData,
  SettingsSearches,
} from '@/lib/api'
import { cn, errorMessage } from '@/lib/utils'

type Props = {
  profile: Profile | null
  onBack: () => void
  onProfileChanged: () => void
}

const SECTION = 'space-y-3 border-b border-border/50 pb-6 last:border-b-0 last:pb-0'

export function ProfilePage({ profile, onBack, onProfileChanged }: Props) {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const resumeFileRef = useRef<HTMLInputElement>(null)
  const coverFileRef = useRef<HTMLInputElement>(null)

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

  function patchSearches(values: Partial<SettingsSearches>) {
    setData((d) => (d ? { ...d, searches: { ...d.searches, ...values } } : d))
  }

  function searchesPayload() {
    if (!data) return null
    const s = data.searches
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

  async function saveSearch() {
    const body = searchesPayload()
    if (!body) return
    setSaving('search')
    try {
      await apiFetch('/settings/searches', { method: 'PUT', body: JSON.stringify(body) })
      toast.success('Saved. Next Auto Search will use these keywords and boards.')
      onProfileChanged()
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSaving(null)
    }
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
        <h1 className="justify-self-center text-xs font-bold uppercase tracking-wider">Profile</h1>
        <div className="justify-self-end">
          <UserSwitcher profile={profile} onChanged={onProfileChanged} />
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        {loading || !data ? (
          <p className="text-sm text-muted-foreground">Loading profile…</p>
        ) : (
          <div className="mx-auto w-full max-w-6xl space-y-6">
            <section className={SECTION}>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel hint="Each keyword chip is typed into the selected job boards. This is the list that finds new jobs.">
                  Auto Search
                </SectionLabel>
                <Button size="sm" onClick={() => void saveSearch()} disabled={saving === 'search'}>
                  <Save /> Save
                </Button>
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
          </div>
        )}
      </main>
    </div>
  )
}

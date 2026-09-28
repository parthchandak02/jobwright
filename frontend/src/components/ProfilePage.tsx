import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Page } from '@/components/PageHeader'
import { ProfileSwitcher } from '@/components/ProfileSwitcher'
import { AboutTab } from '@/components/profile/AboutTab'
import { DailyListTab } from '@/components/profile/DailyListTab'
import { DocumentsTab } from '@/components/profile/DocumentsTab'
import { RulesTab } from '@/components/profile/RulesTab'
import { SearchTab } from '@/components/profile/SearchTab'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { apiFetch, type Profile, type SettingsData } from '@/lib/api'
import { useMe } from '@/lib/me'
import { errorMessage } from '@/lib/utils'

type Props = {
  profile: Profile | null
  onBack: () => void
  onProfileChanged: () => void
}

const PROFILE_TABS = [
  { value: 'search', label: 'Search' },
  { value: 'rules', label: 'Match rules' },
  { value: 'documents', label: 'Documents' },
  { value: 'whatsapp', label: 'Daily list' },
  { value: 'about', label: 'About you' },
] as const

const PANEL = 'data-[state=inactive]:hidden'

function SettingsSkeleton() {
  return (
    <div className="space-y-field" aria-busy aria-label="Loading settings">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-4 w-80 max-w-full" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="space-y-2 pt-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-11 w-full" />
        </div>
      ))}
    </div>
  )
}

export function ProfilePage({ profile, onProfileChanged }: Props) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { me } = useMe()
  const tabParam = params.get('tab')
  const tab = PROFILE_TABS.some((t) => t.value === tabParam) ? (tabParam as string) : 'search'
  const [data, setData] = useState<SettingsData | null>(null)

  const fetchSettings = useCallback(() => apiFetch<SettingsData>('/settings'), [])

  useEffect(() => {
    fetchSettings()
      .then(setData)
      .catch((e) => toast.error(errorMessage(e)))
  }, [fetchSettings])

  const reloadDocuments = useCallback(async () => {
    try {
      const next = await fetchSettings()
      setData((d) =>
        d
          ? {
              ...d,
              resume_markdown: next.resume_markdown,
              has_resume_pdf: next.has_resume_pdf,
              resume_pdf_mtime: next.resume_pdf_mtime,
              cover_letter_examples: next.cover_letter_examples,
            }
          : next,
      )
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }, [fetchSettings])

  const setTab = (v: string) => navigate(`/profile?tab=${v}`, { replace: true })
  const canSwitch = (me?.profiles.length ?? 0) > 1

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 min-w-0 flex-1 flex-col gap-0">
      <Page
        title="Settings"
        description="What we search for, how we judge fit, and your daily list."
        actions={
          canSwitch ? (
            <label className="flex items-center gap-2 text-caption text-muted-foreground">
              Viewing
              <ProfileSwitcher className="w-48" />
            </label>
          ) : undefined
        }
        mobileActions={canSwitch ? <ProfileSwitcher className="h-9 w-36" /> : null}
        headerExtra={
          <TabsList variant="underline" aria-label="Settings sections">
            {PROFILE_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        }
      >
        {!data || !profile ? (
          <SettingsSkeleton />
        ) : (
          <>
            <TabsContent value="search" forceMount tabIndex={-1} className={PANEL}>
              <SearchTab
                searches={data.searches}
                onChange={(searches) => setData((d) => (d ? { ...d, searches } : d))}
              />
            </TabsContent>
            <TabsContent value="rules" forceMount tabIndex={-1} className={PANEL}>
              <RulesTab />
            </TabsContent>
            <TabsContent value="documents" forceMount tabIndex={-1} className={PANEL}>
              <DocumentsTab data={data} reload={reloadDocuments} onProfileChanged={onProfileChanged} />
            </TabsContent>
            <TabsContent value="whatsapp" forceMount tabIndex={-1} className={PANEL}>
              <DailyListTab key={profile.user_id} profile={profile} onSaved={onProfileChanged} />
            </TabsContent>
            <TabsContent value="about" forceMount tabIndex={-1} className={PANEL}>
              <AboutTab profile={data.profile} onSaved={onProfileChanged} onOpenRules={() => setTab('rules')} />
            </TabsContent>
          </>
        )}
      </Page>
    </Tabs>
  )
}
